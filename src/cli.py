"""CLI entry point.

Run end-to-end on a brief and print results. Status events go to stderr so
``--json`` output on stdout stays parseable.

Usage:
    uv run python -m src.cli "<brief>" [--json]
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from dotenv import load_dotenv

from src.agent import run_agent
from src.render import report_to_markdown
from src.schemas import (
    AgentEvent,
    CriteriaExtracted,
    Done,
    GroundingResolved,
    RankingStarted,
    SearchProgress,
)


def _print_event(event: AgentEvent) -> None:
    """Stream stage-level progress to stderr."""
    if isinstance(event, CriteriaExtracted):
        c = event.criteria
        sys.stderr.write(
            f"[understand] space={c.space_type!r} "
            f"categories={c.material_categories} "
            f"certs={c.certifications_required} "
            f"perf={c.performance_constraints} "
            f"brands={c.branded_preferences}\n"
        )
    elif isinstance(event, GroundingResolved):
        g = event.grounded
        sys.stderr.write(
            f"[ground] {len(g.certifications)} cert(s), "
            f"{len(g.taxonomies)} taxonomy term(s), "
            f"{len(g.brands)} brand(s)\n"
        )
        for cert in g.certifications:
            sys.stderr.write(
                f"  cert: {cert.requested!r} → "
                f"{cert.canonical_name!r} (score {cert.score:.2f})\n"
            )
        for t in g.taxonomies:
            sys.stderr.write(
                f"  tax:  {t.category!r} → "
                f"{t.canonical_label!r} ({t.masterformat_code or '-'})\n"
            )
        for b in g.brands:
            verified = "✓" if b.verified else "?"
            sys.stderr.write(
                f"  brand: {b.requested!r} → "
                f"{b.canonical_name!r} {verified}\n"
            )
    elif isinstance(event, SearchProgress):
        sys.stderr.write(
            f"[search] {event.angles_explored} matches across "
            f"{event.products_found} unique products | "
            f"last query: {event.last_query!r}\n"
        )
    elif isinstance(event, RankingStarted):
        sys.stderr.write("[rank] synthesizing recommendations...\n")
    elif isinstance(event, Done):
        sys.stderr.write(
            f"[done] {len(event.report.recommendations)} recommendations\n"
        )


async def _amain(brief: str, json_output: bool) -> None:
    report = await run_agent(brief, on_event=_print_event)
    if json_output:
        sys.stdout.write(report.model_dump_json(indent=2))
        sys.stdout.write("\n")
    else:
        sys.stdout.write(report_to_markdown(report))


def main() -> None:
    load_dotenv()

    parser = argparse.ArgumentParser(
        prog="src.cli",
        description=(
            "Material recommendation agent. Takes a natural-language project "
            "brief and returns ranked product recommendations grounded in the "
            "Acelab catalog."
        ),
    )
    parser.add_argument(
        "brief",
        help='Project brief in natural language, e.g. "high-traffic hospital corridor..."',
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Dump the full structured Report as JSON instead of markdown.",
    )
    args = parser.parse_args()

    asyncio.run(_amain(args.brief, json_output=args.json))


if __name__ == "__main__":
    main()
