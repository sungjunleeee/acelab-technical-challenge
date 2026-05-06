"""Stage 1 — UNDERSTAND.

Parse a free-text architect brief into a structured ``CriteriaSpec``. This is
the only stage that interprets the user's natural language; downstream stages
operate on the structured output and never re-read the raw brief.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from src.llm import structured_completion
from src.schemas import CriteriaSpec, SuggestedAdditions


class _ExtractedSuggestions(BaseModel):
    """Adjacent items the architect might also want, but did not state.

    The UI shows these as **unchecked** checkboxes alongside the extracted
    (checked) values, so users can opt in without having to type. Each list
    is hard-capped to 4 items so the UI stays scannable.
    """

    performance_constraints: list[str] = Field(
        default_factory=list,
        description="Up to 4 commonly-paired performance needs the brief did "
        "NOT mention but a working architect on this kind of project might "
        "want. e.g. for a hospital corridor: 'slip resistance', 'sound absorption'.",
    )
    certifications_required: list[str] = Field(
        default_factory=list,
        description="Up to 4 commonly-paired cert names. Use widely recognized "
        "standards (LEED, GREENGUARD, FloorScore, FSC, Cradle-to-Cradle, "
        "low VOC, ASTM E84). Do NOT repeat anything in the extracted list.",
    )
    aesthetic_qualities: list[str] = Field(
        default_factory=list,
        description="Up to 4 aesthetic words that often pair with the brief's "
        "stated style/use, but were not stated. Skip if the brief says nothing aesthetic.",
    )
    material_categories: list[str] = Field(
        default_factory=list,
        description="Up to 4 adjacent material categories the brief did NOT "
        "mention but the space type makes plausible. e.g. corridor brief that "
        "extracted 'flooring' might suggest 'wall protection', 'handrails', "
        "'ceiling tile'. Do NOT repeat anything in the extracted list.",
    )


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
        "Do NOT guess. Null is the right answer when the brief is silent on budget.",
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
        "'GREENGUARD'. Preserve jargon verbatim. The next stage canonicalizes "
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
        "Empty list if no brand is named. Do NOT invent vendors.",
    )
    suggested_additions: _ExtractedSuggestions = Field(
        default_factory=_ExtractedSuggestions,
        description="Adjacent items the user did NOT mention but might want. "
        "These will be shown as unchecked checkboxes in the UI for the user to "
        "opt into. Never duplicate items already in the extracted lists.",
    )


SYSTEM_PROMPT = """You are an analyst that decomposes architect briefs into structured criteria for a material recommendation pipeline.

RULES FOR EXTRACTED FIELDS (the user's stated intent):
1. Extract ONLY what the brief states or strongly implies. Do not invent constraints, certifications, or vendors that the brief does not mention.
2. Preserve jargon verbatim in `certifications_required` (e.g. "IIC > 50", "ASTM E84 Class A"). A downstream API call canonicalizes them. Silently dropping or paraphrasing them defeats the pipeline.
3. Distinguish certifications (third-party standards: LEED, FSC, GREENGUARD, Cradle-to-Cradle, ASTM, UL) from performance constraints (functional needs: infection control, slip resistance, acoustic absorption).
4. For terse briefs, leave fields empty or null. The pipeline correctly handles low-information inputs; padding with assumptions makes recommendations worse.
5. For `material_categories`, imply categories only when the space type makes them obvious (a hospital corridor needs flooring; a kitchen needs countertops). Do NOT speculate about secondary categories not implied by the brief.
6. `budget_tier` must be null unless the brief uses budget language ("tight budget", "luxury", "mid-range", a dollar figure). Do not infer from the project type.

RULES FOR `suggested_additions` (adjacent items the user might also want):
7. Populate `suggested_additions` with items the brief did NOT state but a working architect on this kind of project would commonly consider. These appear as unchecked checkboxes in the UI for the user to opt into. They are never auto-applied.
8. Do NOT repeat anything from the extracted lists in `suggested_additions` (no duplicates).
9. Cap each `suggested_additions` list at 4 items. Quality over quantity.
10. Use the most widely recognized, vendor-neutral terms (LEED, GREENGUARD, FloorScore, FSC). Avoid brand-specific or obscure standards.
11. Tailor suggestions to the brief: don't suggest "biophilic" for a server room or "antimicrobial" for a residential bedroom. If a category has no plausible adjacent suggestions, leave that suggestion list empty."""


async def understand(brief: str) -> CriteriaSpec:
    """Parse a free-text brief into a CriteriaSpec via a single LLM call."""
    extracted = await structured_completion(
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"BRIEF:\n{brief}"},
        ],
        response_model=_Extracted,
    )
    data = extracted.model_dump()
    sug = data.pop("suggested_additions")
    return CriteriaSpec(
        raw_brief=brief,
        suggested_additions=SuggestedAdditions(**sug),
        **data,
    )
