"""Typed schemas for the recommendation agent.

These are the only data structures that flow between stages. The agent layer
never imports anything from the CLI / renderer; UI front-ends consume the same
types.
"""

from __future__ import annotations

from typing import Annotated, Callable, Literal

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Stage 1 — UNDERSTAND
# ---------------------------------------------------------------------------


class SuggestedAdditions(BaseModel):
    """Per-axis suggestions the user might also want to enable.

    Mirrors the multi-valued fields on ``CriteriaSpec``. The UI presents these
    as unchecked checkboxes alongside the agent-extracted (checked) values.
    """

    performance_constraints: list[str] = Field(default_factory=list)
    certifications_required: list[str] = Field(default_factory=list)
    aesthetic_qualities: list[str] = Field(default_factory=list)
    material_categories: list[str] = Field(default_factory=list)


class CriteriaSpec(BaseModel):
    """Structured interpretation of a free-text architect brief.

    Every list field is meaningful even when empty: an empty
    ``certifications_required`` is a real signal (no certs requested) that the
    grounding stage uses to skip cert canonicalization.
    """

    raw_brief: str
    space_type: str | None = Field(
        None, description="e.g. 'hospital corridor', 'residential kitchen'"
    )
    traffic_level: str | None = Field(
        None, description="'high', 'medium', 'low', or null if unspecified"
    )
    budget_tier: str | None = Field(
        None, description="'luxury', 'mid_range', 'budget', or null if unspecified"
    )
    performance_constraints: list[str] = Field(
        default_factory=list,
        description="Functional requirements, e.g. 'infection control', 'slip resistance'",
    )
    certifications_required: list[str] = Field(
        default_factory=list,
        description="Cert names or standards as written, e.g. 'LEED Silver', 'low VOC', "
        "'IIC > 50'. Preserve jargon verbatim — Stage 2 canonicalizes.",
    )
    aesthetic_qualities: list[str] = Field(
        default_factory=list,
        description="Style/mood descriptors, e.g. 'calming', 'biophilic', 'warm'",
    )
    material_categories: list[str] = Field(
        default_factory=list,
        description="Material/product categories, e.g. 'flooring', 'wall protection', "
        "'ceiling tile'",
    )
    branded_preferences: list[str] = Field(
        default_factory=list,
        description="Vendor names the brief explicitly mentions. Empty otherwise.",
    )
    suggested_additions: SuggestedAdditions = Field(
        default_factory=SuggestedAdditions,
        description=(
            "Optional adjacent items the architect might also want to add but "
            "did not state in the brief. Surfaced as unchecked options in the "
            "UI so users can opt in. Never auto-applied."
        ),
    )


# ---------------------------------------------------------------------------
# Stage 2 — GROUND
# ---------------------------------------------------------------------------


class CertificationResolution(BaseModel):
    requested: str
    canonical_name: str
    issuer: list[str] | None = None
    description: str | None = None
    score: float


class TaxonomyResolution(BaseModel):
    category: str
    canonical_label: str | None = None
    masterformat_code: str | None = None
    score: float
    matched: bool


class BrandResolution(BaseModel):
    requested: str
    canonical_name: str | None = None
    website: str | None = None
    status: str | None = None
    score: float
    verified: bool


class GroundedContext(BaseModel):
    certifications: list[CertificationResolution] = Field(default_factory=list)
    taxonomies: list[TaxonomyResolution] = Field(default_factory=list)
    brands: list[BrandResolution] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Stage 3 — SEARCH
# ---------------------------------------------------------------------------


class QueryMatch(BaseModel):
    """One query that surfaced a particular product, with provenance metadata."""

    query: str
    axis_label: str = Field(
        ...,
        description="Which CriteriaSpec axis this query derived from, "
        "e.g. 'performance: infection control', 'category: flooring'",
    )
    score: float


class ProductHit(BaseModel):
    """A unique product surfaced by Stage 3, with all queries that hit it."""

    product_id: str
    product_name: str
    supplier: str | None = None
    market_status: str | None = None
    matches: list[QueryMatch] = Field(default_factory=list)

    @property
    def best_score(self) -> float:
        return max((m.score for m in self.matches), default=0.0)


# ---------------------------------------------------------------------------
# Stage 4 — RANK
# ---------------------------------------------------------------------------


class Recommendation(BaseModel):
    rank: int
    product_name: str
    supplier: str | None = None
    why_it_fits: str = Field(
        ...,
        description="Grounded explanation citing matched axes/scores. MUST NOT "
        "claim certifications, materials, or specs not present in the input.",
    )
    matched_axes: list[str] = Field(
        ...,
        description="Explicit list of CriteriaSpec axes this product matched.",
    )
    fit_score: float = Field(..., ge=0.0, le=1.0)
    caveats: list[str] = Field(
        default_factory=list,
        description="What the architect must verify on the manufacturer spec sheet.",
    )


class Report(BaseModel):
    brief: str
    criteria: CriteriaSpec
    grounded: GroundedContext
    recommendations: list[Recommendation]
    total_products_considered: int


# ---------------------------------------------------------------------------
# Events (streamed to UI / CLI during agent run)
# ---------------------------------------------------------------------------


class CriteriaExtracted(BaseModel):
    type: Literal["criteria_extracted"] = "criteria_extracted"
    criteria: CriteriaSpec


class GroundingResolved(BaseModel):
    type: Literal["grounding_resolved"] = "grounding_resolved"
    grounded: GroundedContext


class SearchProgress(BaseModel):
    type: Literal["search_progress"] = "search_progress"
    angles_explored: int
    products_found: int
    last_query: str | None = None


class RankingStarted(BaseModel):
    type: Literal["ranking_started"] = "ranking_started"


class Done(BaseModel):
    type: Literal["done"] = "done"
    report: Report


AgentEvent = Annotated[
    CriteriaExtracted | GroundingResolved | SearchProgress | RankingStarted | Done,
    Field(discriminator="type"),
]

EventCallback = Callable[[AgentEvent], None]
