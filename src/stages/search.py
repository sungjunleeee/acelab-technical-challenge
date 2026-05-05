"""Stage 3 — SEARCH.

Autonomous LLM tool-calling loop that decomposes the criteria into orthogonal
product queries. Each call to ``search_products`` is required to label the
*axis* of the criteria it derives from, so every product hit carries
provenance: which queries surfaced it, at what score, for which axis.

That provenance is what lets Stage 4 explain ``why_it_fits`` honestly without
hallucinating product attributes the SDK never returned.
"""

from __future__ import annotations

import json
import os
from typing import Any

from acelab import AsyncAcelab

from src.llm import Tool, tool_calling_loop
from src.schemas import (
    CriteriaSpec,
    EventCallback,
    GroundedContext,
    ProductHit,
    QueryMatch,
    SearchProgress,
)

MAX_ITERS = 8
MAX_TOOL_CALLS = 12
PRODUCT_SEARCH_DEFAULT_LIMIT = 5


def _system_prompt(criteria: CriteriaSpec, grounded: GroundedContext) -> str:
    """Brief the LLM with the structured criteria and grounding."""
    return f"""You are a material recommendation specialist searching the Acelab catalog for an architect.

YOUR JOB: issue 5–10 well-decomposed product searches via the `search_products` tool, each labeled with which axis of the criteria it targets. When you have enough diverse candidates, call `finish_searches`.

DECOMPOSITION RULES:
1. Cover orthogonal axes — do NOT issue the same query phrased differently. Each search should target a distinct (category × use-case × constraint) combination.
2. PREFER the user's original phrasing for certifications/constraints (the `requested` text in the criteria). Use canonical names from grounding only when they're clearly the same standard the user meant.
3. If grounding resolved a MasterFormat code or canonical taxonomy label, weave it into queries for the relevant category — embedding search is more precise with canonical terms.
4. Only run brand-named queries for brands the USER mentioned (i.e. brands present in `grounding.brands` with `verified: true`). Do NOT inject vendor names from your prior knowledge — let the catalog surface vendors naturally via category/use-case queries; otherwise top results saturate around one vendor and crowd out alternatives.
5. Cover all material categories the user requested. Don't dump 10 queries on flooring if the brief also mentions ceiling and walls.

AXIS LABELING:
Every `search_products` call must include `axis_label`. Use one of these forms:
- `category: <name>` — primary product type (e.g. "category: flooring")
- `performance: <constraint>` — functional requirement (e.g. "performance: infection control")
- `certification: <name>` — third-party standard (e.g. "certification: LEED Silver")
- `aesthetic: <quality>` — style/mood (e.g. "aesthetic: calming biophilic")
- `brand: <name>` — vendor-driven (e.g. "brand: Mannington")
- `synthesis: <short label>` — multi-axis combined query (e.g. "synthesis: high-traffic healthcare resilient")

SCOPE:
- Max ~10 product searches total. Quality over quantity.
- Each `limit` 3–7. Smaller for highly specific queries.
- Don't search for things the user did not ask for (no fishing for unrelated categories).

CRITERIA:
{criteria.model_dump_json(indent=2, exclude={'raw_brief'})}

ORIGINAL BRIEF:
{criteria.raw_brief}

GROUNDING (canonical terms from the catalog — use as hints, not gospel):
{grounded.model_dump_json(indent=2)}

Begin. Issue your decomposed searches now."""


async def search(
    criteria: CriteriaSpec,
    grounded: GroundedContext,
    on_event: EventCallback | None = None,
) -> list[ProductHit]:
    """Run the tool-calling search loop and return deduplicated product hits."""
    api_key = os.environ["ACELAB_API_KEY"]
    base_url = os.environ["ACELAB_BASE_URL"]

    hits: dict[str, ProductHit] = {}

    async with AsyncAcelab(api_key=api_key, base_url=base_url) as client:

        async def search_products(
            query: str,
            axis_label: str,
            limit: int = PRODUCT_SEARCH_DEFAULT_LIMIT,
        ) -> list[dict[str, Any]]:
            res = await client.search(query, limit=min(limit, 8))
            summary: list[dict[str, Any]] = []
            for r in res.results:
                if r.product_id not in hits:
                    hits[r.product_id] = ProductHit(
                        product_id=r.product_id,
                        product_name=r.manufacturer_product_name,
                        supplier=r.supplier_name,
                        market_status=r.market_status,
                    )
                hits[r.product_id].matches.append(
                    QueryMatch(
                        query=query,
                        axis_label=axis_label,
                        score=r.similarity_score,
                    )
                )
                summary.append(
                    {
                        "name": r.manufacturer_product_name,
                        "supplier": r.supplier_name,
                        "score": round(r.similarity_score, 2),
                    }
                )
            return summary

        async def search_companies(name: str) -> list[dict[str, Any]]:
            res = await client.companies.search(name, limit=3)
            return [
                {
                    "name": c.name,
                    "website": c.website,
                    "status": c.status_name,
                    "score": round(c.similarity_score, 2),
                }
                for c in res.results
            ]

        async def finish_searches() -> str:  # pragma: no cover (handled by loop)
            return "OK"

        def _on_tool_call(name: str, args: dict[str, Any], _result: Any) -> None:
            if on_event and name == "search_products":
                on_event(
                    SearchProgress(
                        angles_explored=sum(
                            1 for h in hits.values() for _ in h.matches
                        ),
                        products_found=len(hits),
                        last_query=args.get("query"),
                    )
                )

        tools = [
            Tool(
                name="search_products",
                description=(
                    "Semantic search across Acelab's product catalog. Returns up to "
                    "`limit` products with similarity scores. Each call is recorded "
                    "as provenance for the products it surfaces."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Natural-language product search query.",
                        },
                        "axis_label": {
                            "type": "string",
                            "description": (
                                "Which axis of the criteria this query targets. "
                                "Format: 'category: ...', 'performance: ...', "
                                "'certification: ...', 'aesthetic: ...', "
                                "'brand: ...', or 'synthesis: ...'."
                            ),
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Max results to return (3-7 recommended).",
                            "default": 5,
                        },
                    },
                    "required": ["query", "axis_label"],
                },
                handler=search_products,
            ),
            Tool(
                name="search_companies",
                description=(
                    "Look up a vendor by brand name to discover its canonical "
                    "company record. Useful for vendor portfolio expansion: once "
                    "you find a strong product from a vendor, follow up with "
                    "vendor-named product searches to consolidate procurement."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Brand or company name to look up.",
                        }
                    },
                    "required": ["name"],
                },
                handler=search_companies,
            ),
            Tool(
                name="finish_searches",
                description=(
                    "Call when you have enough diverse, high-quality candidates "
                    "across all relevant axes of the criteria. Do not call this "
                    "before issuing at least 4 product searches across different "
                    "axes."
                ),
                parameters={"type": "object", "properties": {}},
                handler=finish_searches,
            ),
        ]

        await tool_calling_loop(
            messages=[
                {"role": "system", "content": _system_prompt(criteria, grounded)},
                {
                    "role": "user",
                    "content": (
                        "Decompose the criteria into orthogonal searches. "
                        "Call `finish_searches` when ready."
                    ),
                },
            ],
            tools=tools,
            max_iters=MAX_ITERS,
            max_tool_calls=MAX_TOOL_CALLS,
            terminator_tool="finish_searches",
            on_tool_call=_on_tool_call,
            temperature=0.3,
        )

    return list(hits.values())
