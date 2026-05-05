"""Agent orchestrator.

Two ways to drive the pipeline:

1. **Stage-level API** — call ``understand``, ``ground``, ``search``, and
   ``rank`` directly. Each stage takes typed input and returns typed output;
   a UI can interpose user edits between any two adjacent stages without
   special pause/resume logic in the agent itself.

2. **Convenience wrapper** — ``run_agent`` runs the full pipeline end-to-end
   and emits ``AgentEvent``s through an optional ``on_event`` callback. This
   is what the CLI uses.
"""

from __future__ import annotations

from src.schemas import (
    CriteriaExtracted,
    Done,
    EventCallback,
    GroundingResolved,
    RankingStarted,
    Report,
)
from src.stages.ground import ground
from src.stages.rank import rank
from src.stages.search import search
from src.stages.understand import understand

__all__ = ["understand", "ground", "search", "rank", "run_agent"]


async def run_agent(
    brief: str,
    on_event: EventCallback | None = None,
) -> Report:
    """Run the full pipeline. Emits AgentEvents at every stage transition."""
    criteria = await understand(brief)
    if on_event:
        on_event(CriteriaExtracted(criteria=criteria))

    grounded = await ground(criteria)
    if on_event:
        on_event(GroundingResolved(grounded=grounded))

    hits = await search(criteria, grounded, on_event=on_event)

    if on_event:
        on_event(RankingStarted())
    report = await rank(criteria, grounded, hits)
    if on_event:
        on_event(Done(report=report))

    return report
