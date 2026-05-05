"""Per-stage unit tests with hand-written mocks (no live API).

Stages 1 and 4 patch ``src.llm.structured_completion`` to return canned
pydantic instances. Stage 2 patches ``acelab.AsyncAcelab`` so its async
resource methods return canned responses built from ``acelab.models``.
Stage 3 patches ``src.llm.tool_calling_loop`` and drives the registered
tool handlers directly with synthetic args to verify provenance tracking.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from acelab.models import (
    CertificationSearchResponse,
    CertificationSearchResult,
    CompanySearchResponse,
    CompanySearchResult,
    ProductSearchResult,
    SearchResponse,
    TaxonomyMatchResult,
    TaxonomySearchResponse,
    TaxonomySearchResult,
)
from src.schemas import (
    CriteriaSpec,
    GroundedContext,
    ProductHit,
    QueryMatch,
    Recommendation,
)
from src.stages.ground import (
    BRAND_THRESHOLD,
    CERT_THRESHOLD,
    TAXONOMY_THRESHOLD,
    ground,
)
from src.stages.rank import _RankedOutput, _missing_baseline_caveats, rank
from src.stages.understand import _Extracted, understand


# ---------------------------------------------------------------------------
# Canned-response builders
# ---------------------------------------------------------------------------


def _cert(name: str, score: float) -> CertificationSearchResponse:
    return CertificationSearchResponse(
        results=[
            CertificationSearchResult(
                id="c", name=name, similarity_score=score,
                issuing_body_names=["Test Body"], description="canned",
            )
        ],
        query=name, total_results=1, top_k=1,
    )


def _tax(label: str, mf: str, score: float, *, matched: bool = True) -> TaxonomySearchResponse:
    cand = TaxonomySearchResult(
        id="t", name=label, display_name=label,
        similarity_score=score, masterformat_code=mf,
    )
    m = TaxonomyMatchResult(
        match_status="MATCHED" if matched else "UNMATCHED",
        matched_taxonomy=cand if matched else None,
        top_candidates=[cand],
    )
    return TaxonomySearchResponse(old_taxonomy=m, new_taxonomy=m, query_input={})


def _company(name: str, score: float) -> CompanySearchResponse:
    return CompanySearchResponse(
        results=[
            CompanySearchResult(
                id="co", name=name, website="https://example.com",
                status_name="Live on Acelab", similarity_score=score,
            )
        ],
        query=name, total_results=1, top_k=1,
    )


def _products(*triples: tuple[str, str, float]) -> SearchResponse:
    return SearchResponse(
        results=[
            ProductSearchResult(
                product_id=pid, manufacturer_product_name=name,
                supplier_name=f"Supplier {pid}", market_status="Live on Acelab",
                similarity_score=score,
            )
            for pid, name, score in triples
        ],
        query="canned", total_results=len(triples), top_k=len(triples),
    )


class _FakeResource:
    def __init__(self) -> None:
        self._responses: dict[str, Any] = {}

    def register(self, key: str, resp: Any) -> None:
        self._responses[key] = resp

    async def search(self, *args: Any, **kwargs: Any) -> Any:
        key = args[0] if args else kwargs.get("product_category_scraped", "")
        return self._responses[key]


class _FakeAcelab:
    """Drop-in for ``acelab.AsyncAcelab`` (used as ``async with``)."""

    def __init__(self, *_a: Any, **_kw: Any) -> None:
        self.certifications = _FakeResource()
        self.taxonomy = _FakeResource()
        self.companies = _FakeResource()
        self._product_responses: dict[str, SearchResponse] = {}

    def register_product(self, query: str, resp: SearchResponse) -> None:
        self._product_responses[query] = resp

    async def search(self, query: str, *, limit: int = 10) -> SearchResponse:
        return self._product_responses[query]

    async def __aenter__(self) -> "_FakeAcelab":
        return self

    async def __aexit__(self, *_exc: Any) -> None:
        return None


def _setenv(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ACELAB_API_KEY", "test")
    monkeypatch.setenv("ACELAB_BASE_URL", "https://example.com")


# ---------------------------------------------------------------------------
# Stage 1 — UNDERSTAND
# ---------------------------------------------------------------------------


async def test_understand_returns_criteriaspec_with_raw_brief() -> None:
    extracted = _Extracted(
        space_type="hospital corridor",
        traffic_level="high",
        budget_tier="mid_range",
        performance_constraints=["infection control"],
        certifications_required=["LEED Silver"],
        aesthetic_qualities=["calming"],
        material_categories=["flooring"],
    )
    with patch(
        "src.stages.understand.structured_completion",
        new=AsyncMock(return_value=extracted),
    ):
        spec = await understand("test brief")

    assert spec.raw_brief == "test brief"
    assert spec.space_type == "hospital corridor"
    assert spec.material_categories == ["flooring"]
    assert spec.certifications_required == ["LEED Silver"]


# ---------------------------------------------------------------------------
# Stage 2 — GROUND
# ---------------------------------------------------------------------------


async def test_ground_drops_certifications_below_threshold(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _setenv(monkeypatch)
    fake = _FakeAcelab()
    fake.certifications.register("LEED Silver", _cert("LEED Possible Points", 0.83))
    fake.certifications.register("infection control", _cert("HACCP", 0.70))  # below

    with patch("src.stages.ground.AsyncAcelab", return_value=fake):
        grounded = await ground(CriteriaSpec(
            raw_brief="b",
            certifications_required=["LEED Silver"],
            performance_constraints=["infection control"],
        ))

    assert len(grounded.certifications) == 1
    assert grounded.certifications[0].requested == "LEED Silver"
    assert grounded.certifications[0].score >= CERT_THRESHOLD


async def test_ground_drops_taxonomy_below_threshold(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _setenv(monkeypatch)
    fake = _FakeAcelab()
    fake.taxonomy.register("flooring", _tax("Resilient Flooring", "09 65 16", 0.85))
    fake.taxonomy.register(
        "ambiguous", _tax("Whatever", "00 00 00", TAXONOMY_THRESHOLD - 0.1, matched=False)
    )

    with patch("src.stages.ground.AsyncAcelab", return_value=fake):
        grounded = await ground(CriteriaSpec(
            raw_brief="b",
            material_categories=["flooring", "ambiguous"],
        ))

    assert len(grounded.taxonomies) == 1
    assert grounded.taxonomies[0].category == "flooring"
    assert grounded.taxonomies[0].masterformat_code == "09 65 16"


async def test_ground_brand_sanity_check_rejects_name_mismatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Below-threshold + no name overlap => dropped. Verified-by-name => kept."""
    _setenv(monkeypatch)
    fake = _FakeAcelab()
    # Below BRAND_THRESHOLD AND "Interface" not in the returned name.
    fake.companies.register(
        "Interface", _company("Object Carpet", BRAND_THRESHOLD - 0.05)
    )
    fake.companies.register("Mannington", _company("Mannington Commercial", 0.92))

    with patch("src.stages.ground.AsyncAcelab", return_value=fake):
        grounded = await ground(CriteriaSpec(
            raw_brief="b",
            branded_preferences=["Interface", "Mannington"],
        ))

    requested = {b.requested for b in grounded.brands}
    assert requested == {"Mannington"}
    assert grounded.brands[0].verified is True


# ---------------------------------------------------------------------------
# Stage 3 — SEARCH (drive tool handlers, not the LLM loop)
# ---------------------------------------------------------------------------


async def test_search_handlers_accumulate_provenance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Replace ``tool_calling_loop`` with a stub that invokes the registered
    ``search_products`` handler twice with synthetic args. Verify dedupe by
    product_id and ``QueryMatch`` accumulation across queries."""
    _setenv(monkeypatch)
    fake = _FakeAcelab()
    fake.register_product(
        "resilient flooring",
        _products(("p1", "BioSpec Sheet Vinyl", 0.81), ("p2", "Calm Quartz", 0.78)),
    )
    fake.register_product(
        "calming healthcare flooring",
        _products(("p1", "BioSpec Sheet Vinyl", 0.76), ("p3", "Hygenique Tile", 0.74)),
    )

    async def driving_loop(messages, tools, **kwargs):  # type: ignore[no-untyped-def]
        handlers = {t.name: t.handler for t in tools}
        await handlers["search_products"](
            query="resilient flooring",
            axis_label="category: flooring",
            limit=5,
        )
        await handlers["search_products"](
            query="calming healthcare flooring",
            axis_label="synthesis: high-traffic healthcare",
            limit=5,
        )
        return ("", [])

    from src.stages.search import search

    with (
        patch("src.stages.search.AsyncAcelab", return_value=fake),
        patch("src.stages.search.tool_calling_loop", new=driving_loop),
    ):
        hits = await search(
            CriteriaSpec(raw_brief="b", material_categories=["flooring"]),
            GroundedContext(),
        )

    by_id = {h.product_id: h for h in hits}
    assert set(by_id) == {"p1", "p2", "p3"}
    p1 = by_id["p1"]
    assert len(p1.matches) == 2  # provenance accumulates
    assert {m.axis_label for m in p1.matches} == {
        "category: flooring",
        "synthesis: high-traffic healthcare",
    }
    assert p1.best_score == pytest.approx(0.81)


# ---------------------------------------------------------------------------
# Stage 4 — RANK
# ---------------------------------------------------------------------------


async def test_rank_appends_baseline_caveats_skipping_already_mentioned() -> None:
    criteria = CriteriaSpec(
        raw_brief="b",
        certifications_required=["LEED Silver", "low VOC"],
        performance_constraints=["slip resistance"],
        material_categories=["flooring"],
    )
    hit = ProductHit(
        product_id="p1", product_name="Sheet Vinyl", supplier="Acme",
        matches=[QueryMatch(query="flooring", axis_label="category: flooring", score=0.8)],
    )
    rec = Recommendation(
        rank=1, product_name="Sheet Vinyl", supplier="Acme",
        why_it_fits="Surfaced for category: flooring (0.80).",
        matched_axes=["category: flooring"], fit_score=0.7,
        caveats=["Verify 'LEED Silver' contribution on the manufacturer spec sheet."],
    )

    with patch(
        "src.stages.rank.structured_completion",
        new=AsyncMock(return_value=_RankedOutput(recommendations=[rec])),
    ):
        report = await rank(criteria, GroundedContext(), [hit])

    cavs = report.recommendations[0].caveats
    blob = " ".join(cavs).lower()
    # Already-covered cert isn't duplicated.
    assert sum("leed silver" in c.lower() for c in cavs) == 1
    # Other unmentioned constraints get baseline lines.
    assert "low voc" in blob
    assert "slip resistance" in blob


def test_missing_baseline_caveats_skips_already_mentioned() -> None:
    criteria = CriteriaSpec(
        raw_brief="b",
        certifications_required=["LEED Silver", "FSC"],
        performance_constraints=["slip resistance"],
    )
    new = _missing_baseline_caveats(
        criteria,
        ["Verify LEED Silver contribution on the manufacturer spec sheet."],
    )
    blob = " ".join(new).lower()
    assert "leed silver" not in blob
    assert "fsc" in blob
    assert "slip resistance" in blob


def test_missing_baseline_caveats_emits_generic_when_nothing_specified() -> None:
    new = _missing_baseline_caveats(CriteriaSpec(raw_brief="b"), [])
    assert len(new) == 1
    assert "manufacturer" in new[0].lower()


async def test_rank_empty_hits_returns_empty_report() -> None:
    report = await rank(CriteriaSpec(raw_brief="b"), GroundedContext(), [])
    assert report.recommendations == []
    assert report.total_products_considered == 0
