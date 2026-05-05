"""End-to-end loop tests + hallucination audit.

These run the full ``run_agent`` pipeline against live APIs, so they're slow
and burn LLM credits. Run only when explicitly requested:

    uv run pytest -m e2e

Skipped automatically when ``OPENROUTER_API_KEY`` or ``ACELAB_API_KEY`` are
not present in the environment.
"""

from __future__ import annotations

import asyncio
import os
import re

import pytest
from dotenv import load_dotenv

from src.agent import run_agent
from src.schemas import Report
from tests.validation_set import BRIEF_CASES, BriefCase, Expectations

load_dotenv()


def _skip_if_no_keys() -> None:
    missing = [
        k
        for k in ("OPENROUTER_API_KEY", "ACELAB_API_KEY", "ACELAB_BASE_URL")
        if not os.environ.get(k)
    ]
    if missing:
        pytest.skip(f"e2e test requires env vars: {', '.join(missing)}")


# Shared cache so the same brief is only run once even when both
# ``test_validation_case`` and ``test_no_fabricated_cert_claims`` parameterize
# over it. Halves API spend on a full run.
_REPORT_CACHE: dict[str, Report] = {}


def _run(brief: str) -> Report:
    if brief in _REPORT_CACHE:
        return _REPORT_CACHE[brief]
    report = asyncio.run(run_agent(brief))
    _REPORT_CACHE[brief] = report
    return report


# ---------------------------------------------------------------------------
# Test 1 — full validation set
# ---------------------------------------------------------------------------


@pytest.mark.e2e
@pytest.mark.parametrize("case", BRIEF_CASES, ids=[c.id for c in BRIEF_CASES])
def test_validation_case(case: BriefCase) -> None:
    _skip_if_no_keys()
    report = _run(case.brief)
    exp = case.expectations

    # Stage 1: extracted categories.
    cats_blob = " ".join(report.criteria.material_categories).lower()
    for needle in exp.must_extract_categories:
        assert needle.lower() in cats_blob, (
            f"[{case.id}] missing category substring "
            f"{needle!r} in {report.criteria.material_categories!r}"
        )

    # Stage 1: extracted aesthetics.
    aes_blob = " ".join(report.criteria.aesthetic_qualities).lower()
    for needle in exp.must_extract_aesthetics:
        assert needle.lower() in aes_blob, (
            f"[{case.id}] missing aesthetic substring "
            f"{needle!r} in {report.criteria.aesthetic_qualities!r}"
        )

    # Stage 2: cert resolutions (canonical OR requested name may match).
    cert_blob = " ".join(
        f"{c.requested} {c.canonical_name}" for c in report.grounded.certifications
    ).lower()
    for needle in exp.must_resolve_certifications:
        assert needle.lower() in cert_blob, (
            f"[{case.id}] expected cert substring {needle!r} in "
            f"resolutions {[c.canonical_name for c in report.grounded.certifications]!r}"
        )

    # Stage 4: enough recommendations.
    assert len(report.recommendations) >= exp.min_recommendations, (
        f"[{case.id}] only {len(report.recommendations)} recs, "
        f"expected >= {exp.min_recommendations}"
    )

    # Diversity in top 8.
    suppliers = {
        r.supplier for r in report.recommendations[:8] if r.supplier
    }
    assert len(suppliers) >= exp.min_distinct_suppliers, (
        f"[{case.id}] only {len(suppliers)} distinct suppliers in top 8 "
        f"({suppliers!r}), expected >= {exp.min_distinct_suppliers}"
    )

    # Caveats populated where required.
    if exp.must_populate_caveats:
        for r in report.recommendations:
            assert r.caveats, (
                f"[{case.id}] recommendation {r.product_name!r} has empty caveats"
            )


# ---------------------------------------------------------------------------
# Test 2 — hallucination audit
# ---------------------------------------------------------------------------


# Suspicious assertion-style cert claim: "<keyword> [linker]" preceded by a
# noun phrase. We capture ~80 chars before each match for traceability check.
_CERT_CLAIM_RE = re.compile(
    r"(?i)\b(certified|compliant|rated)\s+(?:to|for|under|with|by|as)?"
)


def _audit_recommendation(
    why: str, grounded_corroboration: list[str], forbidden: list[str]
) -> list[str]:
    """Return list of failure messages for one ``why_it_fits`` blob."""
    failures: list[str] = []
    low = why.lower()

    # 1. Forbidden phrases (case-insensitive substring).
    for phrase in forbidden:
        if phrase.lower() in low:
            failures.append(f"forbidden phrase {phrase!r} in why_it_fits")

    # 2. Regex for assertion-style cert claims. Each match must be
    # corroborated by a canonical or requested cert name appearing within
    # ~80 chars of the match.
    for m in _CERT_CLAIM_RE.finditer(why):
        start = max(0, m.start() - 80)
        end = min(len(why), m.end() + 20)
        span = why[start:end]
        span_low = span.lower()
        # If the span is purely a meta-statement (e.g. "the architect must
        # verify whether the product is certified..."), accept it. Heuristic:
        # require an actual cert from grounded to corroborate, OR the span
        # already includes hedging language.
        hedge = any(
            h in span_low
            for h in ("verify", "must confirm", "spec sheet", "not assert", "do not claim", "unverified")
        )
        if hedge:
            continue
        if not any(c.lower() in span_low for c in grounded_corroboration if c):
            failures.append(
                f"un-corroborated certification claim near "
                f"position {m.start()}: ...{span!r}..."
            )
    return failures


@pytest.mark.e2e
@pytest.mark.parametrize("case", BRIEF_CASES, ids=[c.id for c in BRIEF_CASES])
def test_no_fabricated_cert_claims(case: BriefCase) -> None:
    _skip_if_no_keys()
    report = _run(case.brief)

    corroboration = [
        c.canonical_name
        for c in report.grounded.certifications
        if c.canonical_name
    ] + [c.requested for c in report.grounded.certifications]

    all_failures: list[str] = []
    for r in report.recommendations:
        fails = _audit_recommendation(
            r.why_it_fits,
            corroboration,
            case.expectations.forbidden_phrases_in_why_it_fits,
        )
        if fails:
            all_failures.extend(
                f"[{case.id}] rec={r.product_name!r}: {f}" for f in fails
            )

    assert not all_failures, "\n".join(all_failures)


# ---------------------------------------------------------------------------
# Test 3 — diversity under terse input
# ---------------------------------------------------------------------------


@pytest.mark.e2e
def test_diversity_under_terse_input() -> None:
    _skip_if_no_keys()
    report = _run("hospital flooring")

    top8 = report.recommendations[:8]
    suppliers = {r.supplier for r in top8 if r.supplier}
    assert len(suppliers) >= 2, (
        f"expected >= 2 distinct suppliers in top 8, got {suppliers!r}"
    )

    flooring_axes = {"flooring", "resilient flooring", "sheet flooring"}
    matched_axes_blob = " ".join(
        ax.lower() for r in top8 for ax in r.matched_axes
    )
    assert any(needle in matched_axes_blob for needle in flooring_axes), (
        "expected at least one of flooring / resilient flooring / sheet "
        f"flooring in matched_axes; got: {matched_axes_blob!r}"
    )
