"""Validation set for the material recommendation agent.

Each ``BriefCase`` carries the input brief plus declarative ``Expectations``
the agent must satisfy. The set covers two orthogonal axes:

- **content variety** — what the brief is about (hospital, residential, office,
  studio, school cafeteria).
- **input-quality variety** — how well-formed the brief is (terse, vague,
  missing info, overly verbose RFP, jargon-dense).

The e2e test suite parameterizes over ``BRIEF_CASES`` and asserts every
``Expectations`` field for each case.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class Expectations(BaseModel):
    """Per-case expectations the agent's ``Report`` must satisfy.

    String-list fields use case-insensitive substring matching against the
    relevant field on ``CriteriaSpec`` / ``GroundedContext``.
    """

    must_extract_categories: list[str] = Field(
        default_factory=list,
        description="Substrings Stage 1 must place in `material_categories`.",
    )
    must_resolve_certifications: list[str] = Field(
        default_factory=list,
        description="Substrings the canonical or requested name must contain "
        "in `grounded.certifications`.",
    )
    must_extract_aesthetics: list[str] = Field(
        default_factory=list,
        description="Substrings Stage 1 must place in `aesthetic_qualities`.",
    )
    min_recommendations: int = 5
    min_distinct_suppliers: int = 3
    forbidden_phrases_in_why_it_fits: list[str] = Field(
        default_factory=list,
        description="Phrases that would imply a fabricated cert/spec claim "
        "for this specific brief. Case-insensitive.",
    )
    must_populate_caveats: bool = True


class BriefCase(BaseModel):
    """One validation example: a brief plus expectations it must satisfy."""

    id: str
    brief: str
    expectations: Expectations


# Realistic over-detailed RFP-style brief (~150 words). Burying the budget
# tier in prose is intentional — Stage 1 has to extract signal from noise.
_OVER_DETAILED_BRIEF = (
    "Project Sunrise — Phase II Tenant Improvement, Floors 3-5. We are "
    "issuing this RFI as part of the design development package for an "
    "approximately 42,000 sf adaptive-reuse renovation of an existing "
    "Class-B office building targeting LEED v4.1 Silver at minimum. The "
    "client is a mid-sized professional services firm relocating from a "
    "neighboring tower; their existing build-out skewed conservative and "
    "they want this floor to feel substantively different — warmer, more "
    "biophilic, with materials that read as natural and tactile. Open-plan "
    "with collaboration zones and a small number of focus rooms. Budget "
    "is mid-range — not value-engineered, but not luxury either; the GC "
    "has been clear that we are aiming for the middle of the market on "
    "spec'd assemblies. Required: low-VOC interior finishes, FSC wood "
    "where wood is used, and durable flooring suited to moderate office "
    "traffic. Anticipated CDs Q3 2026; please flag any long-lead items "
    "in your response."
)


BRIEF_CASES: list[BriefCase] = [
    BriefCase(
        id="hospital_corridor",
        brief=(
            "High-traffic hospital corridor that needs to meet infection "
            "control standards, LEED Silver minimum, and a calming "
            "aesthetic. Budget is mid-range."
        ),
        expectations=Expectations(
            must_extract_categories=["flooring"],
            must_resolve_certifications=["LEED"],
            must_extract_aesthetics=["calming"],
            min_recommendations=5,
            min_distinct_suppliers=3,
            forbidden_phrases_in_why_it_fits=[
                "GREENGUARD Gold certified",
                "antimicrobial coating",
                "low-VOC certified",
                "meets ASTM",
            ],
            must_populate_caveats=True,
        ),
    ),
    BriefCase(
        id="residential_kitchen",
        brief=(
            "Warm residential kitchen, FSC-certified cabinetry, "
            "child-safe finishes."
        ),
        expectations=Expectations(
            must_extract_categories=["cabinet"],
            must_resolve_certifications=["FSC"],
            must_extract_aesthetics=["warm"],
            min_recommendations=5,
            min_distinct_suppliers=3,
            forbidden_phrases_in_why_it_fits=[
                "FSC certified",
                "FSC-certified product",
                "child-safe certified",
                "non-toxic certified",
            ],
            must_populate_caveats=True,
        ),
    ),
    BriefCase(
        id="branded_office",
        brief=(
            "Open-plan tech office floor, want to spec Mannington carpet, "
            "must be Cradle-to-Cradle."
        ),
        expectations=Expectations(
            must_extract_categories=["carpet"],
            must_resolve_certifications=["Cradle"],
            must_extract_aesthetics=[],
            min_recommendations=5,
            min_distinct_suppliers=2,
            forbidden_phrases_in_why_it_fits=[
                "Cradle to Cradle Certified",
                "Cradle-to-Cradle certified",
                "C2C Gold",
                "verified Cradle-to-Cradle",
            ],
            must_populate_caveats=True,
        ),
    ),
    BriefCase(
        id="conflicting",
        brief="Ultra-luxury feel but tight budget for a school cafeteria.",
        expectations=Expectations(
            must_extract_categories=[],
            must_resolve_certifications=[],
            must_extract_aesthetics=["luxury"],
            min_recommendations=5,
            min_distinct_suppliers=2,
            forbidden_phrases_in_why_it_fits=[
                "high-end certified",
                "luxury-grade rated",
            ],
            must_populate_caveats=True,
        ),
    ),
    BriefCase(
        id="acoustic_focus",
        brief=(
            "Recording studio control room, prioritize acoustic absorption "
            "and zero-VOC."
        ),
        expectations=Expectations(
            must_extract_categories=[],
            must_resolve_certifications=["VOC"],
            must_extract_aesthetics=[],
            min_recommendations=5,
            min_distinct_suppliers=2,
            forbidden_phrases_in_why_it_fits=[
                "zero-VOC certified",
                "GREENGUARD certified",
                "NRC rated",
                "acoustic-rated",
            ],
            must_populate_caveats=True,
        ),
    ),
    BriefCase(
        id="terse_query",
        brief="hospital flooring",
        expectations=Expectations(
            must_extract_categories=["flooring"],
            must_resolve_certifications=[],
            must_extract_aesthetics=[],
            min_recommendations=5,
            min_distinct_suppliers=2,
            forbidden_phrases_in_why_it_fits=[
                "antimicrobial certified",
                "infection-control rated",
                "LEED certified",
            ],
            must_populate_caveats=True,
        ),
    ),
    BriefCase(
        id="vague_minimal",
        brief="A nice modern bathroom",
        expectations=Expectations(
            must_extract_categories=[],
            must_resolve_certifications=[],
            must_extract_aesthetics=["modern"],
            min_recommendations=5,
            min_distinct_suppliers=2,
            forbidden_phrases_in_why_it_fits=[
                "WaterSense certified",
                "ADA compliant",
                "anti-slip rated",
            ],
            must_populate_caveats=True,
        ),
    ),
    BriefCase(
        id="missing_info",
        brief="flooring for an office",
        expectations=Expectations(
            must_extract_categories=["flooring"],
            must_resolve_certifications=[],
            must_extract_aesthetics=[],
            min_recommendations=5,
            min_distinct_suppliers=2,
            forbidden_phrases_in_why_it_fits=[
                "LEED certified",
                "low-VOC certified",
                "FloorScore certified",
            ],
            must_populate_caveats=True,
        ),
    ),
    BriefCase(
        id="over_detailed",
        brief=_OVER_DETAILED_BRIEF,
        expectations=Expectations(
            must_extract_categories=["flooring"],
            must_resolve_certifications=["LEED"],
            must_extract_aesthetics=["biophilic"],
            min_recommendations=5,
            min_distinct_suppliers=3,
            forbidden_phrases_in_why_it_fits=[
                "FSC certified product",
                "LEED Silver certified",
                "low-VOC certified",
                "biophilic certified",
            ],
            must_populate_caveats=True,
        ),
    ),
    BriefCase(
        id="jargon_dense",
        brief=(
            "H&S corridor specs, IIC > 50, ASTM E84 Class A, no PVC, "
            "GBI Tier 2"
        ),
        expectations=Expectations(
            must_extract_categories=[],
            must_resolve_certifications=["ASTM"],
            must_extract_aesthetics=[],
            min_recommendations=5,
            min_distinct_suppliers=2,
            forbidden_phrases_in_why_it_fits=[
                "ASTM E84 Class A rated",
                "IIC 50 rated",
                "PVC-free certified",
                "GBI Tier 2 certified",
            ],
            must_populate_caveats=True,
        ),
    ),
]
