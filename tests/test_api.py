"""FastAPI endpoint tests with mocked stages and reference endpoints.

Stage logic is already covered in test_stages.py; this file is about the
HTTP contract: response shapes, request validation, SSE framing, and the
typo-validation endpoint's confidence tiering.

Live-API tests (no mocks) belong in test_e2e.py behind ``-m e2e``.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient

from acelab.models import (
    CertificationSearchResponse,
    CertificationSearchResult,
    CompanySearchResponse,
    CompanySearchResult,
)
from src.api import app
from src.schemas import (
    CriteriaSpec,
    GroundedContext,
    ProductHit,
    QueryMatch,
    Recommendation,
    Report,
    SearchProgress,
    SuggestedAdditions,
)


# ---------------------------------------------------------------------------
# Env stub (the api.py validate endpoint reads ACELAB_API_KEY/BASE_URL even
# when AsyncAcelab is patched, since the patch is on the client class only).
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _setenv(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ACELAB_API_KEY", "test-key")
    monkeypatch.setenv("ACELAB_BASE_URL", "https://test.example.com")


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


def test_health(client: TestClient) -> None:
    res = client.get("/api/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}


# ---------------------------------------------------------------------------
# /api/understand
# ---------------------------------------------------------------------------


def test_understand_endpoint(client: TestClient) -> None:
    fake_spec = CriteriaSpec(
        raw_brief="hospital flooring",
        space_type="hospital",
        material_categories=["flooring"],
        certifications_required=["LEED Silver"],
        suggested_additions=SuggestedAdditions(
            certifications_required=["GREENGUARD Gold"],
            material_categories=["wall protection"],
        ),
    )
    with patch("src.api.understand", new=AsyncMock(return_value=fake_spec)):
        res = client.post(
            "/api/understand", json={"brief": "hospital flooring"}
        )
    assert res.status_code == 200
    body = res.json()
    assert body["space_type"] == "hospital"
    assert body["material_categories"] == ["flooring"]
    # New field surfaces through the API contract.
    assert body["suggested_additions"]["material_categories"] == ["wall protection"]
    assert body["suggested_additions"]["certifications_required"] == [
        "GREENGUARD Gold"
    ]


def test_understand_endpoint_rejects_empty_brief(client: TestClient) -> None:
    res = client.post("/api/understand", json={"brief": ""})
    assert res.status_code == 422  # pydantic min_length=1 validation


# ---------------------------------------------------------------------------
# /api/validate (the typo-check endpoint used by the Stage 1 custom-add input)
# ---------------------------------------------------------------------------


def _cert_response(name: str, score: float) -> CertificationSearchResponse:
    return CertificationSearchResponse(
        results=[
            CertificationSearchResult(
                id="c", name=name, similarity_score=score,
                issuing_body_names=["TestBody"], description=None,
            )
        ],
        query=name, total_results=1, top_k=1,
    )


def _company_response(name: str, score: float) -> CompanySearchResponse:
    return CompanySearchResponse(
        results=[
            CompanySearchResult(
                id="co", name=name, website="https://example.com",
                status_name="Published/Live on Acelab", similarity_score=score,
            )
        ],
        query=name, total_results=1, top_k=1,
    )


class _FakeClient:
    """Stub of AsyncAcelab that returns canned responses."""

    def __init__(self, cert_response: Any = None, company_response: Any = None):
        self._cert = cert_response
        self._company = company_response

    async def __aenter__(self) -> "_FakeClient":
        return self

    async def __aexit__(self, *_: Any) -> None:
        return None

    @property
    def certifications(self) -> Any:
        outer = self
        class _C:
            async def search(self, *_a: Any, **_kw: Any) -> Any:
                return outer._cert
        return _C()

    @property
    def companies(self) -> Any:
        outer = self
        class _C:
            async def search(self, *_a: Any, **_kw: Any) -> Any:
                return outer._company
        return _C()


def test_validate_endpoint_high_confidence(client: TestClient) -> None:
    fake = _FakeClient(cert_response=_cert_response("LEED Possible Points", 0.92))
    with patch("src.api.AsyncAcelab", return_value=fake):
        res = client.post(
            "/api/validate",
            json={"phrase": "LEED Silver", "kind": "certification"},
        )
    assert res.status_code == 200
    body = res.json()
    assert body["confidence"] == "high"
    assert body["canonical"] == "LEED Possible Points"
    assert body["score"] == pytest.approx(0.92, abs=1e-3)
    assert body["candidates"][0]["name"] == "LEED Possible Points"


def test_validate_endpoint_medium_confidence(client: TestClient) -> None:
    fake = _FakeClient(cert_response=_cert_response("LCARate Silver", 0.72))
    with patch("src.api.AsyncAcelab", return_value=fake):
        res = client.post(
            "/api/validate",
            json={"phrase": "LEEd silvar", "kind": "certification"},
        )
    body = res.json()
    assert body["confidence"] == "medium"
    # canonical is still set so the UI can offer "use match" with the soft warning
    assert body["canonical"] == "LCARate Silver"


def test_validate_endpoint_low_confidence(client: TestClient) -> None:
    fake = _FakeClient(cert_response=_cert_response("Standards", 0.50))
    with patch("src.api.AsyncAcelab", return_value=fake):
        res = client.post(
            "/api/validate",
            json={"phrase": "totally made up", "kind": "certification"},
        )
    body = res.json()
    assert body["confidence"] == "low"
    # canonical is None so the UI knows not to silently swap the user's input
    assert body["canonical"] is None


def test_validate_endpoint_brand(client: TestClient) -> None:
    fake = _FakeClient(company_response=_company_response("Mannington Mills", 0.90))
    with patch("src.api.AsyncAcelab", return_value=fake):
        res = client.post(
            "/api/validate",
            json={"phrase": "Mannington", "kind": "brand"},
        )
    body = res.json()
    assert body["confidence"] == "high"
    assert body["canonical"] == "Mannington Mills"


# ---------------------------------------------------------------------------
# /api/rank
# ---------------------------------------------------------------------------


def test_rank_endpoint_passes_top_n(client: TestClient) -> None:
    captured: dict[str, Any] = {}

    async def fake_rank(criteria: Any, grounded: Any, hits: Any, **kw: Any) -> Report:
        captured["top_n"] = kw.get("top_n")
        return Report(
            brief="test",
            criteria=criteria,
            grounded=grounded,
            recommendations=[],
            total_products_considered=len(hits),
        )

    payload = {
        "criteria": CriteriaSpec(raw_brief="test").model_dump(),
        "grounded": GroundedContext().model_dump(),
        "hits": [],
        "top_n": 5,
    }
    with patch("src.api.rank", new=fake_rank):
        res = client.post("/api/rank", json=payload)
    assert res.status_code == 200
    assert captured["top_n"] == 5


# ---------------------------------------------------------------------------
# /api/search SSE: progress events + terminal search_done payload
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_sse_emits_progress_and_done() -> None:
    """The streaming endpoint must surface every search_progress event and
    end with a terminal search_done event whose payload is the hit list."""

    async def fake_search(criteria: Any, grounded: Any, on_event: Any) -> list[ProductHit]:
        on_event(SearchProgress(angles_explored=3, products_found=2, last_query="q1"))
        on_event(SearchProgress(angles_explored=7, products_found=5, last_query="q2"))
        return [
            ProductHit(
                product_id="p1",
                product_name="Test Product",
                supplier="Test Supplier",
                matches=[
                    QueryMatch(query="q1", axis_label="category: flooring", score=0.81)
                ],
            )
        ]

    body = {
        "criteria": CriteriaSpec(raw_brief="test").model_dump(),
        "grounded": GroundedContext().model_dump(),
    }

    transport = ASGITransport(app=app)
    with patch("src.api.search", new=fake_search):
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            async with ac.stream("POST", "/api/search", json=body) as r:
                assert r.status_code == 200
                received: list[str] = []
                async for line in r.aiter_lines():
                    if line.startswith("data: "):
                        received.append(line[6:])

    # Two progress + one search_done at minimum.
    types = []
    import json as _json
    for raw in received:
        types.append(_json.loads(raw)["type"])
    assert "search_progress" in types
    assert types[-1] == "search_done"
    # search_done payload mirrors the ProductHit list.
    last = _json.loads(received[-1])
    assert last["hits"][0]["product_name"] == "Test Product"


# ---------------------------------------------------------------------------
# Recommendation schema sanity (the rank endpoint payload contract)
# ---------------------------------------------------------------------------


def test_recommendation_round_trips_through_api(client: TestClient) -> None:
    """Rank input must accept a fully-populated Recommendation; this catches
    schema drift between Python and the TypeScript types in web/src/lib/types.ts."""
    payload = {
        "criteria": CriteriaSpec(raw_brief="t").model_dump(),
        "grounded": GroundedContext().model_dump(),
        "hits": [
            ProductHit(
                product_id="p",
                product_name="P",
                matches=[QueryMatch(query="q", axis_label="category: x", score=0.7)],
            ).model_dump()
        ],
    }
    rec = Recommendation(
        rank=1,
        product_name="P",
        supplier="S",
        why_it_fits="Surfaced for category: x (0.70)",
        matched_axes=["category: x"],
        fit_score=0.7,
        caveats=["Verify on the manufacturer spec sheet."],
    )

    async def fake_rank(*_a: Any, **_kw: Any) -> Report:
        return Report(
            brief="t",
            criteria=CriteriaSpec(raw_brief="t"),
            grounded=GroundedContext(),
            recommendations=[rec],
            total_products_considered=1,
        )

    with patch("src.api.rank", new=fake_rank):
        res = client.post("/api/rank", json=payload)
    assert res.status_code == 200
    body = res.json()
    assert body["recommendations"][0]["fit_score"] == 0.7
    assert body["recommendations"][0]["matched_axes"] == ["category: x"]
