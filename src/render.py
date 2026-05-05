"""Markdown rendering for the final Report.

Pure transformation over a ``Report``. The agent layer never imports this
module — alternative renderers (HTML, Streamlit, JSON) live alongside.
"""

from __future__ import annotations

from src.schemas import Report


def report_to_markdown(report: Report) -> str:
    lines: list[str] = []
    lines.append("# Material Recommendations")
    lines.append("")
    lines.append(f"> _{report.brief}_")
    lines.append("")
    lines.append(
        f"**{len(report.recommendations)}** recommendation(s) drawn from "
        f"**{report.total_products_considered}** unique products surfaced "
        f"during search."
    )
    lines.append("")

    lines.extend(_render_criteria(report))
    lines.extend(_render_grounding(report))
    lines.extend(_render_recommendations(report))

    return "\n".join(lines).rstrip() + "\n"


def _render_criteria(report: Report) -> list[str]:
    c = report.criteria
    out = ["## Interpreted criteria", ""]
    rows: list[tuple[str, str]] = []
    if c.space_type:
        rows.append(("Space", c.space_type))
    if c.traffic_level:
        rows.append(("Traffic", c.traffic_level))
    if c.budget_tier:
        rows.append(("Budget", c.budget_tier))
    if c.material_categories:
        rows.append(("Material categories", ", ".join(c.material_categories)))
    if c.certifications_required:
        rows.append(("Certifications", ", ".join(c.certifications_required)))
    if c.performance_constraints:
        rows.append(("Performance", ", ".join(c.performance_constraints)))
    if c.aesthetic_qualities:
        rows.append(("Aesthetic", ", ".join(c.aesthetic_qualities)))
    if c.branded_preferences:
        rows.append(("Branded preferences", ", ".join(c.branded_preferences)))

    if not rows:
        out.append("_No structured criteria extracted from the brief._")
    else:
        for label, value in rows:
            out.append(f"- **{label}:** {value}")
    out.append("")
    return out


def _render_grounding(report: Report) -> list[str]:
    g = report.grounded
    if not (g.certifications or g.taxonomies or g.brands):
        return []
    out = ["## Grounded references", ""]

    if g.certifications:
        out.append("**Canonical certifications** (catalog hits for the user's cert/constraint phrases):")
        out.append("")
        for cert in g.certifications:
            issuer = f" ({', '.join(cert.issuer)})" if cert.issuer else ""
            out.append(
                f"- _{cert.requested}_ → **{cert.canonical_name}**{issuer} "
                f"— score {cert.score:.2f}"
            )
        out.append("")

    if g.taxonomies:
        out.append("**Taxonomy classification** (MasterFormat codes for the requested categories):")
        out.append("")
        for t in g.taxonomies:
            mf = t.masterformat_code or "n/a"
            tag = "matched" if t.matched else "candidate"
            out.append(
                f"- _{t.category}_ → **{t.canonical_label}** "
                f"(MasterFormat {mf}, {tag} @ {t.score:.2f})"
            )
        out.append("")

    if g.brands:
        out.append("**Brand verification:**")
        out.append("")
        for b in g.brands:
            verified = "✓" if b.verified else "?"
            status = f" — {b.status}" if b.status else ""
            out.append(
                f"- _{b.requested}_ → **{b.canonical_name}** {verified}{status}"
            )
        out.append("")

    return out


def _render_recommendations(report: Report) -> list[str]:
    out = ["## Ranked recommendations", ""]
    if not report.recommendations:
        out.append("_No products surfaced for the given brief._")
        out.append("")
        return out

    for r in report.recommendations:
        supplier = r.supplier or "(supplier unknown)"
        out.append(f"### {r.rank}. {r.product_name} — {supplier}")
        out.append("")
        out.append(f"- **Fit score:** {r.fit_score:.2f}")
        if r.matched_axes:
            out.append(f"- **Matched axes:** {', '.join(r.matched_axes)}")
        out.append("")
        out.append(f"**Why it fits:** {r.why_it_fits}")
        out.append("")
        if r.caveats:
            out.append("**Verify on the manufacturer spec sheet:**")
            for cav in r.caveats:
                out.append(f"- {cav}")
            out.append("")
    return out
