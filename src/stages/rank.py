"""Stage 4 — RANK & EXPLAIN.

Take the deduplicated product hits from Stage 3 and produce ranked
recommendations with grounded ``why_it_fits`` text. The Stage 4 prompt is the
single most important hallucination guard in the pipeline: the LLM may cite
which axes a product matched (data we have) but is forbidden from claiming
certifications, materials, or specs (data we don't have).

A baseline ``caveats`` list is auto-derived from the CriteriaSpec so an
architect always sees what they must verify off-platform, regardless of what
the LLM produces.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from src.llm import default_rank_model, structured_completion
from src.schemas import (
    CriteriaSpec,
    GroundedContext,
    ProductHit,
    Recommendation,
    Report,
)

# Pre-filter the candidate pool sent to the ranker. 20 is enough to give the
# LLM real choice while keeping prompt + completion small (Stage 4 is the
# slowest single LLM call in the pipeline; latency scales roughly linearly
# with input + output tokens).
TOP_PRODUCTS_TO_CONSIDER = 20
DEFAULT_TOP_N = 8

# Dedupe per-product matches before sending to the ranker. Many products are
# hit by multiple near-duplicate queries; the LLM only needs the distinct
# (axis, score) signal, not every individual query string.
MAX_MATCHES_PER_PRODUCT = 4


class _RankedOutput(BaseModel):
    """LLM produces the ranked list; we wrap it into a Report afterward."""

    recommendations: list[Recommendation] = Field(
        ...,
        description=f"Top {DEFAULT_TOP_N} ranked recommendations.",
    )


SYSTEM_PROMPT_TEMPLATE = """You are a senior architectural materials specialist producing the final ranked recommendations from a pre-filtered candidate pool.

THE INPUT CONTAINS, AND ONLY CONTAINS:
- The architect's CriteriaSpec (their structured intent).
- A GroundedContext (canonical certs, MasterFormat codes, verified vendors, the catalog's view of the user's constraints).
- A pool of candidate products, each with PROVENANCE: which decomposed queries surfaced the product, the axis label of each query, and the similarity score.

THE INPUT DOES NOT CONTAIN PRODUCT-LEVEL ATTRIBUTES. The Acelab API returns no per-product certifications, materials, ratings, dimensions, sustainability data, slip ratings, or composition info.

THEREFORE, `why_it_fits` MUST cite ONLY:
- Which axes of the CriteriaSpec the product matched (from the QueryMatch axis labels).
- The similarity scores of those matches.
- The supplier name and `market_status` (e.g. "Live on Acelab" indicates the supplier is currently published in the catalog).
- Canonical MasterFormat code or taxonomy label from GroundedContext when applicable.

`why_it_fits` MUST NOT:
- Claim the product is "certified" / "rated" / "compliant" with any standard. The API never returned that. Even if the product NAME suggests it (e.g. "BioSpec" sounds like it might be antimicrobial), do not assert it. The architect verifies on the manufacturer spec sheet.
- Invent material composition, specs, dimensions, performance ratings, or sustainability attributes.
- Use marketing language ("premium", "industry-leading"). Stick to facts the input supports.

ALLOWED PHRASING EXAMPLES:
- "Surfaced for 'category: flooring' (0.81) and 'performance: infection control' (0.76). Supplier Mannington Commercial is Live on Acelab."
- "Highest match for the calming aesthetic axis (0.83). Categorized under MasterFormat 09 65 00 Resilient Flooring per grounding."
- "Matches three axes: category: wall protection (0.80), category: ceiling (0.78), and synthesis: hospital corridor (0.75)."

FORBIDDEN PHRASING EXAMPLES (these would be hallucinations):
- "GREENGUARD Gold certified" (not in the input).
- "Antimicrobial coating" (speculation from the product name).
- "Meets ASTM E84 Class A" (never asserted by the API).
- "Low-VOC compliant" (even if the user asked for low-VOC, we don't know the product satisfies it).

RANKING (read this carefully):
- Return EXACTLY {top_n} recommendations. The candidate pool you receive has been pre-filtered to be reasonable choices, so under-returning means leaving good options on the table.
- The ONLY exception: if the candidate pool literally contains fewer than {top_n} distinct VIABLE products, return all the viable ones. A product is `viable` if it has at least one QueryMatch with similarity >= 0.65. The user payload tells you the candidate count and how many are viable; use those numbers to decide whether you're allowed to return fewer than {top_n}.
- Rank by: (a) breadth of axes matched (more orthogonal axes is better), (b) match scores, (c) coverage across material categories the user requested (don't return {top_n} flooring products if the user also asked for wall and ceiling).
- `fit_score` (0.0 to 1.0): your judgment of how well the product satisfies the brief, given the provenance available.
- `matched_axes`: the distinct axis labels from the QueryMatches for that product.

CAVEATS:
For each recommendation, include caveats listing what the architect must independently verify on the manufacturer spec sheet. Every certification or performance constraint the user asked for is a verification item, since the API didn't confirm them. Be specific (cite the criterion name).

Now rank."""


def _build_system_prompt(top_n: int) -> str:
    return SYSTEM_PROMPT_TEMPLATE.replace("{top_n}", str(top_n))


async def rank(
    criteria: CriteriaSpec,
    grounded: GroundedContext,
    hits: list[ProductHit],
    *,
    top_n: int = DEFAULT_TOP_N,
) -> Report:
    """Rank the product hits into a final Report."""
    candidates = sorted(hits, key=lambda h: h.best_score, reverse=True)[
        :TOP_PRODUCTS_TO_CONSIDER
    ]

    if not candidates:
        return Report(
            brief=criteria.raw_brief,
            criteria=criteria,
            grounded=grounded,
            recommendations=[],
            total_products_considered=0,
        )

    user_payload = _build_user_payload(criteria, grounded, candidates, top_n)

    output = await structured_completion(
        messages=[
            {"role": "system", "content": _build_system_prompt(top_n)},
            {"role": "user", "content": user_payload},
        ],
        response_model=_RankedOutput,
        model=default_rank_model(),
        temperature=0.2,
    )

    recommendations = output.recommendations[:top_n]
    # Defensive: ensure every user-stated cert/perf constraint appears somewhere
    # in the caveats list. If the LLM already covered a constraint by name we
    # skip adding the generic line for it, to avoid the kind of redundant pair
    # like ("Verify LEED Possible Points contribution...", "Verify 'LEED Silver'
    # on the manufacturer spec sheet.").
    for rec in recommendations:
        for cav in _missing_baseline_caveats(criteria, rec.caveats):
            rec.caveats.append(cav)

    return Report(
        brief=criteria.raw_brief,
        criteria=criteria,
        grounded=grounded,
        recommendations=recommendations,
        total_products_considered=len(hits),
    )


def _build_user_payload(
    criteria: CriteriaSpec,
    grounded: GroundedContext,
    candidates: list[ProductHit],
    top_n: int,
) -> str:
    viable_count = sum(
        1 for h in candidates if any(m.score >= 0.65 for m in h.matches)
    )
    candidate_blobs = []
    for h in candidates:
        # Keep at most MAX_MATCHES_PER_PRODUCT, deduped by axis_label and
        # sorted by score descending. The ranker doesn't need the full query
        # string for every match; the axis label is what's load-bearing.
        seen_axes: set[str] = set()
        compact: list[dict[str, Any]] = []
        for m in sorted(h.matches, key=lambda x: x.score, reverse=True):
            if m.axis_label in seen_axes:
                continue
            seen_axes.add(m.axis_label)
            compact.append(
                {"axis": m.axis_label, "score": round(m.score, 2)}
            )
            if len(compact) >= MAX_MATCHES_PER_PRODUCT:
                break
        candidate_blobs.append(
            {
                "name": h.product_name,
                "supplier": h.supplier,
                "status": h.market_status,
                "matches": compact,
            }
        )
    import json

    return (
        "CRITERIA:\n"
        + criteria.model_dump_json(indent=2)
        + "\n\nGROUNDED:\n"
        + grounded.model_dump_json(indent=2)
        + f"\n\nCANDIDATE_POOL_STATS:\n"
        f"  total_candidates={len(candidates)}\n"
        f"  viable_count={viable_count}  (have at least one match score >= 0.65)\n"
        f"  required_recommendation_count={top_n}\n"
        f"  permitted_to_return_fewer={'YES' if viable_count < top_n else 'NO'}"
        + "\n\nCANDIDATES (deduplicated, top "
        + str(len(candidates))
        + " by best similarity score):\n"
        + json.dumps(candidate_blobs, indent=2)
    )


def _missing_baseline_caveats(
    criteria: CriteriaSpec, existing: list[str]
) -> list[str]:
    """Return baseline caveats whose criterion phrase isn't already mentioned."""
    blob = " ".join(c.lower() for c in existing)
    items: list[str] = []
    for cert in criteria.certifications_required:
        if cert.lower() not in blob:
            items.append(f"Verify '{cert}' on the manufacturer spec sheet.")
    for perf in criteria.performance_constraints:
        if perf.lower() not in blob:
            items.append(f"Verify '{perf}' is met per the manufacturer spec sheet.")
    if not existing and not items:
        items.append(
            "Acelab catalog data does not include product attribute detail. "
            "Verify all functional and certification requirements on each "
            "manufacturer's spec sheet before specifying."
        )
    return items
