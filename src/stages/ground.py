"""Stage 2 — GROUND.

Deterministic parallel fan-out (no LLM): canonicalize the criteria the user
mentioned by looking them up in Acelab's reference endpoints. Cert phrases
become specific cert names with descriptions; categories become MasterFormat
codes; brand names become verified company records.

The output of this stage is what gives Stage 3 the canonical vocabulary to
issue good product searches, and what Stage 4 cites in ``why_it_fits``.
"""

from __future__ import annotations

import asyncio
import os

from acelab import AsyncAcelab

from src.schemas import (
    BrandResolution,
    CertificationResolution,
    CriteriaSpec,
    GroundedContext,
    TaxonomyResolution,
)

# Empirical thresholds from probe data (see examples/probe.py).
# Cert search has the noisiest top-1 — embedding confuses related-but-different
# standards (e.g. "infection control" → HACCP @0.70, when the user wants UL 2282
# Resistance to Microbial Growth). 0.75 is the gentle cutoff that keeps the clean
# matches (LEED @0.83, UL 2884 PVC Free @0.87) and drops obvious noise. Anything
# resolved here is a HINT for Stage 3's queries — Stages 3/4 still cite the
# user's original `requested` phrase as the source of truth.
CERT_THRESHOLD = 0.75
TAXONOMY_THRESHOLD = 0.70
BRAND_THRESHOLD = 0.75


async def ground(criteria: CriteriaSpec) -> GroundedContext:
    """Run all reference-endpoint lookups in parallel and assemble the result."""
    api_key = os.environ["ACELAB_API_KEY"]
    base_url = os.environ["ACELAB_BASE_URL"]

    async with AsyncAcelab(api_key=api_key, base_url=base_url) as client:
        cert_phrases = [
            *criteria.certifications_required,
            # Performance constraints often have a corresponding certification
            # (e.g. "infection control" → UL 2282). Look these up too; the
            # threshold drops anything that doesn't actually match.
            *criteria.performance_constraints,
        ]

        cert_tasks = [_resolve_certification(client, p) for p in cert_phrases]
        tax_tasks = [
            _resolve_taxonomy(client, c, criteria.raw_brief)
            for c in criteria.material_categories
        ]
        brand_tasks = [_resolve_brand(client, b) for b in criteria.branded_preferences]

        cert_results, tax_results, brand_results = await asyncio.gather(
            asyncio.gather(*cert_tasks) if cert_tasks else _empty(),
            asyncio.gather(*tax_tasks) if tax_tasks else _empty(),
            asyncio.gather(*brand_tasks) if brand_tasks else _empty(),
        )

    return GroundedContext(
        certifications=[r for r in cert_results if r is not None],
        taxonomies=[r for r in tax_results if r is not None],
        brands=[r for r in brand_results if r is not None],
    )


async def _empty() -> list:
    return []


async def _resolve_certification(
    client: AsyncAcelab, phrase: str
) -> CertificationResolution | None:
    try:
        res = await client.certifications.search(phrase, limit=1)
    except Exception:
        return None
    if not res.results:
        return None
    top = res.results[0]
    if top.similarity_score < CERT_THRESHOLD or not top.name:
        return None
    return CertificationResolution(
        requested=phrase,
        canonical_name=top.name,
        issuer=top.issuing_body_names,
        description=top.description,
        score=top.similarity_score,
    )


async def _resolve_taxonomy(
    client: AsyncAcelab, category: str, brief: str
) -> TaxonomyResolution | None:
    try:
        res = await client.taxonomy.search(
            product_category_scraped=category,
            product_description=brief,
        )
    except Exception:
        return None
    new = res.new_taxonomy
    matched = new.matched_taxonomy
    candidate = matched or (new.top_candidates[0] if new.top_candidates else None)
    if candidate is None or candidate.similarity_score < TAXONOMY_THRESHOLD:
        return None
    return TaxonomyResolution(
        category=category,
        canonical_label=candidate.display_name or candidate.name,
        masterformat_code=candidate.masterformat_code,
        score=candidate.similarity_score,
        matched=new.match_status == "MATCHED",
    )


async def _resolve_brand(
    client: AsyncAcelab, brand: str
) -> BrandResolution | None:
    try:
        res = await client.companies.search(brand, limit=1)
    except Exception:
        return None
    if not res.results:
        return None
    top = res.results[0]
    # Sanity check: companies.search by brand-name returns confused results
    # when the brand name overlaps common words (e.g. "Interface" → "Object Carpet").
    # Require the canonical result to mention the queried brand.
    verified = bool(top.name) and brand.lower() in (top.name or "").lower()
    if top.similarity_score < BRAND_THRESHOLD and not verified:
        return None
    return BrandResolution(
        requested=brand,
        canonical_name=top.name,
        website=top.website,
        status=top.status_name,
        score=top.similarity_score,
        verified=verified,
    )
