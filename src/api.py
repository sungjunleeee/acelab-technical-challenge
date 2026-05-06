"""FastAPI HTTP layer over the agent stages.

Endpoints mirror the stage-level API in ``src.agent`` so the web UI can
either call each stage individually (interposing user edits between them) or
hit the all-in-one streaming endpoint for "fast mode".

Live progress (Stage 3 search) and full-pipeline runs are exposed as Server-
Sent Events so the UI can render a live progress sidebar without polling.

Run with:

    uv run uvicorn src.api:app --reload
"""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any, Literal

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from acelab import AsyncAcelab
from src.agent import ground, rank, run_agent, search, understand
from src.schemas import (
    AgentEvent,
    CriteriaSpec,
    GroundedContext,
    ProductHit,
    Report,
)

load_dotenv()

app = FastAPI(
    title="Acelab Material Recommendation Agent",
    version="0.1.0",
    description="HTTP layer over the 4-stage recommendation pipeline.",
)

# Frontend dev server runs on a different port (Vite default 5173). Allowing
# all origins keeps local dev frictionless; tighten for production.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Stage-level endpoints
# ---------------------------------------------------------------------------


class UnderstandIn(BaseModel):
    brief: str = Field(..., min_length=1)


@app.post("/api/understand", response_model=CriteriaSpec)
async def api_understand(req: UnderstandIn) -> CriteriaSpec:
    """Stage 1: parse a brief into structured criteria + suggestions."""
    return await understand(req.brief)


@app.post("/api/ground", response_model=GroundedContext)
async def api_ground(criteria: CriteriaSpec) -> GroundedContext:
    """Stage 2: canonicalize criteria via reference endpoints."""
    return await ground(criteria)


class SearchIn(BaseModel):
    criteria: CriteriaSpec
    grounded: GroundedContext


@app.post("/api/search")
async def api_search(req: SearchIn) -> StreamingResponse:
    """Stage 3 as Server-Sent Events.

    Streams ``search_progress`` events as the agent issues queries, then a
    terminal ``search_done`` event with the deduplicated ProductHit list.
    """
    return _stream_stage(
        runner=lambda on_event: search(req.criteria, req.grounded, on_event=on_event),
        terminal_event_type="search_done",
        terminal_payload_key="hits",
        serialize=lambda hits: [h.model_dump() for h in hits],
    )


class RankIn(BaseModel):
    criteria: CriteriaSpec
    grounded: GroundedContext
    hits: list[ProductHit]
    top_n: int | None = None


@app.post("/api/rank", response_model=Report)
async def api_rank(req: RankIn) -> Report:
    """Stage 4: rank hits and produce the final Report."""
    if req.top_n is not None:
        return await rank(req.criteria, req.grounded, req.hits, top_n=req.top_n)
    return await rank(req.criteria, req.grounded, req.hits)


# ---------------------------------------------------------------------------
# All-in-one streaming endpoint (skip user editing checkpoints)
# ---------------------------------------------------------------------------


@app.post("/api/run")
async def api_run(req: UnderstandIn) -> StreamingResponse:
    """Run the full pipeline end-to-end, streaming every AgentEvent as SSE."""

    async def runner(on_event: Any) -> Report:
        return await run_agent(req.brief, on_event=on_event)

    return _stream_stage(
        runner=runner,
        terminal_event_type=None,  # run_agent already emits a Done event
        terminal_payload_key=None,
        serialize=None,
    )


# ---------------------------------------------------------------------------
# Typo / canonicalization validation (used by Stage 1 user-typed input)
# ---------------------------------------------------------------------------


class ValidateIn(BaseModel):
    phrase: str = Field(..., min_length=1)
    kind: Literal["certification", "category", "brand"]


class ValidateCandidate(BaseModel):
    name: str
    score: float
    extra: str | None = None  # MasterFormat code, issuer, website, etc.


class ValidateOut(BaseModel):
    canonical: str | None
    score: float
    candidates: list[ValidateCandidate]
    confidence: Literal["high", "medium", "low"]


@app.post("/api/validate", response_model=ValidateOut)
async def api_validate(req: ValidateIn) -> ValidateOut:
    """Verify a user-typed phrase by running it through the matching reference
    endpoint. The UI uses this to catch typos and surface canonical names."""
    api_key = _env_or_500("ACELAB_API_KEY")
    base_url = _env_or_500("ACELAB_BASE_URL")

    async with AsyncAcelab(api_key=api_key, base_url=base_url) as client:
        if req.kind == "certification":
            res = await client.certifications.search(req.phrase, limit=3)
            cands = [
                ValidateCandidate(
                    name=r.name or "",
                    score=r.similarity_score,
                    extra=", ".join(r.issuing_body_names or []) or None,
                )
                for r in res.results
                if r.name
            ]
        elif req.kind == "category":
            res = await client.taxonomy.search(
                product_category_scraped=req.phrase, product_description=""
            )
            cand_list = res.new_taxonomy.top_candidates or []
            cands = [
                ValidateCandidate(
                    name=c.display_name or c.name or "",
                    score=c.similarity_score,
                    extra=c.masterformat_code,
                )
                for c in cand_list[:3]
                if (c.display_name or c.name)
            ]
        else:  # brand
            res = await client.companies.search(req.phrase, limit=3)
            cands = [
                ValidateCandidate(
                    name=c.name or "",
                    score=c.similarity_score,
                    extra=c.website,
                )
                for c in res.results
                if c.name
            ]

    if not cands:
        return ValidateOut(
            canonical=None, score=0.0, candidates=[], confidence="low"
        )

    top = cands[0]
    confidence: Literal["high", "medium", "low"]
    if top.score >= 0.85:
        confidence = "high"
    elif top.score >= 0.65:
        confidence = "medium"
    else:
        confidence = "low"

    return ValidateOut(
        canonical=top.name if confidence != "low" else None,
        score=top.score,
        candidates=cands,
        confidence=confidence,
    )


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# SSE plumbing
# ---------------------------------------------------------------------------


def _stream_stage(
    runner: Any,
    terminal_event_type: str | None,
    terminal_payload_key: str | None,
    serialize: Any,
) -> StreamingResponse:
    """Run an async stage that takes an ``on_event`` callback and stream the
    events as SSE. If ``terminal_event_type`` is given, append a terminal event
    with the runner's return value under ``terminal_payload_key``."""

    queue: asyncio.Queue = asyncio.Queue()
    sentinel = object()

    def on_event(event: AgentEvent) -> None:
        queue.put_nowait(event)

    async def background() -> None:
        try:
            result = await runner(on_event)
            if terminal_event_type is not None:
                payload = (
                    serialize(result) if serialize is not None else result
                )
                queue.put_nowait(
                    {"type": terminal_event_type, terminal_payload_key: payload}
                )
        except Exception as e:  # surface errors to the stream
            queue.put_nowait({"type": "error", "message": str(e)})
        finally:
            queue.put_nowait(sentinel)

    async def stream():
        task = asyncio.create_task(background())
        try:
            while True:
                item = await queue.get()
                if item is sentinel:
                    break
                if hasattr(item, "model_dump"):
                    payload = item.model_dump(mode="json")
                else:
                    payload = item
                yield f"data: {json.dumps(payload, default=str)}\n\n"
        finally:
            await task

    return StreamingResponse(stream(), media_type="text/event-stream")


def _env_or_500(name: str) -> str:
    val = os.environ.get(name)
    if not val:
        raise HTTPException(status_code=500, detail=f"Missing env var {name}")
    return val
