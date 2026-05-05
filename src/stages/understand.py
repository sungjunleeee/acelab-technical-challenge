"""Stage 1 — UNDERSTAND.

Parse a free-text architect brief into a structured ``CriteriaSpec``. This is
the only stage that interprets the user's natural language; downstream stages
operate on the structured output and never re-read the raw brief.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from src.llm import structured_completion
from src.schemas import CriteriaSpec


class _Extracted(BaseModel):
    """Sub-schema sent to the LLM. ``raw_brief`` is populated programmatically
    from the input rather than wasting tokens having the model echo it."""

    space_type: str | None = Field(
        None, description="e.g. 'hospital corridor', 'residential kitchen'. Null if unstated."
    )
    traffic_level: str | None = Field(
        None, description="One of 'high', 'medium', 'low', or null if unstated."
    )
    budget_tier: str | None = Field(
        None,
        description="One of 'luxury', 'mid_range', 'budget', or null if unstated. "
        "Do NOT guess — null is the right answer when the brief is silent on budget.",
    )
    performance_constraints: list[str] = Field(
        default_factory=list,
        description="Functional/performance requirements like 'infection control', "
        "'slip resistance', 'acoustic absorption', 'IIC > 50'. NOT certifications.",
    )
    certifications_required: list[str] = Field(
        default_factory=list,
        description="Cert names, standards, or rating systems exactly as written: "
        "'LEED Silver', 'low VOC', 'FSC certified', 'Cradle-to-Cradle', "
        "'GREENGUARD'. Preserve jargon verbatim — the next stage canonicalizes "
        "via the certifications API.",
    )
    aesthetic_qualities: list[str] = Field(
        default_factory=list,
        description="Style/mood words: 'calming', 'biophilic', 'warm', 'modern', 'industrial'.",
    )
    material_categories: list[str] = Field(
        default_factory=list,
        description="Material or product categories the brief mentions or implies: "
        "'flooring', 'wall protection', 'ceiling', 'cabinetry', 'countertop', "
        "'acoustic panel'. Imply only when the space type strongly suggests it "
        "(e.g. corridor implies flooring + walls).",
    )
    branded_preferences: list[str] = Field(
        default_factory=list,
        description="Vendor/manufacturer names the brief explicitly mentions. "
        "Empty list if no brand is named — do NOT invent vendors.",
    )


SYSTEM_PROMPT = """You are an analyst that decomposes architect briefs into structured criteria for a material recommendation pipeline.

RULES:
1. Extract ONLY what the brief states or strongly implies. Do not invent constraints, certifications, or vendors that the brief does not mention.
2. Preserve jargon verbatim in `certifications_required` (e.g. "IIC > 50", "ASTM E84 Class A"). A downstream API call canonicalizes them — silently dropping or paraphrasing them defeats the pipeline.
3. Distinguish certifications (third-party standards: LEED, FSC, GREENGUARD, Cradle-to-Cradle, ASTM, UL) from performance constraints (functional needs: infection control, slip resistance, acoustic absorption).
4. For terse briefs, leave fields empty or null. The pipeline correctly handles low-information inputs; padding with assumptions makes recommendations worse.
5. For `material_categories`, imply categories only when the space type makes them obvious (a hospital corridor needs flooring; a kitchen needs countertops). Do NOT speculate about secondary categories not implied by the brief.
6. `budget_tier` must be null unless the brief uses budget language ("tight budget", "luxury", "mid-range", a dollar figure). Do not infer from the project type."""


async def understand(brief: str) -> CriteriaSpec:
    """Parse a free-text brief into a CriteriaSpec via a single LLM call."""
    extracted = await structured_completion(
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"BRIEF:\n{brief}"},
        ],
        response_model=_Extracted,
    )
    return CriteriaSpec(raw_brief=brief, **extracted.model_dump())
