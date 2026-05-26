"""Workspace/Global prompt templates — all 10 cases from blueprint §8.

Each function takes a context dict and returns a formatted string.
"""

from __future__ import annotations


def _max_items(ctx: dict) -> int:
    return int(ctx.get("_max_items", 5))


def _fmt(value, ctx: dict | None = None, default: str = "None") -> str:
    limit = _max_items(ctx or {})
    if value is None or value == "":
        return default
    if isinstance(value, dict):
        items = [f"{k}: {v}" for k, v in value.items()]
        return _fmt(items, ctx, default=default)
    if isinstance(value, (list, tuple, set)):
        values = [str(item) for item in value if str(item)]
        if not values:
            return default
        shown = values[:limit]
        suffix = f" (+{len(values) - limit} more)" if len(values) > limit else ""
        return ", ".join(shown) + suffix
    return str(value)


def _recommendation_line(ctx: dict, default: str) -> str:
    recommendation = _fmt(ctx.get("recommendation"), ctx, default)
    return f"  Recommendation: {recommendation}\n"


def _conflict_lines(ctx: dict) -> list[str]:
    conflicts = list(ctx.get("conflicts", []))
    if not conflicts and ctx.get("package"):
        conflicts = [{
            "package": ctx.get("package"),
            "new_tool_requires": ctx.get("version_d"),
            "currently_locked": ctx.get("version_locked"),
            "locked_by_tools": ctx.get("locked_by"),
        }]

    lines = []
    for conflict in conflicts[: _max_items(ctx)]:
        locked_by = conflict.get("locked_by_tools", conflict.get("locked_by", []))
        lines.append(
            f"  - {conflict.get('package', '?')}: requires {conflict.get('new_tool_requires', '?')}; "
            f"locked {conflict.get('currently_locked', '?')} by {_fmt(locked_by, ctx)}"
        )
    if len(conflicts) > _max_items(ctx):
        lines.append(f"  - +{len(conflicts) - _max_items(ctx)} more conflicts")
    return lines


def case_1_brand_new(ctx: dict) -> str:
    """Case 1 — Brand New Scope."""
    return (
        f"Decision: new capability scope (capabilities not found elsewhere).\n"
        f"\n"
        f"  Capability:  {_fmt(ctx.get('output_desc'), ctx, 'N/A')}\n"
        f"  Inputs:      {_fmt(ctx.get('input_desc'), ctx, 'N/A')}\n"
        f"  Domain:      {_fmt(ctx.get('domain_tags'), ctx, 'N/A')}\n"
        f"  Permissions: {_fmt(ctx.get('permissions'), ctx, 'None')}\n"
        f"  Trust:       {ctx.get('trust_score', 0)}/1.0 ({ctx.get('publisher', 'Unknown')})\n"
    )


def case_1_options() -> list[str]:
    return [
        "Install globally",
        "Install for this workspace only",
        "Cancel",
    ]


def case_2_partial_overlap(ctx: dict) -> str:
    """Case 2 — Partial Overlap (D covers everything A does, plus more)."""
    rec = _recommendation_line(
        ctx,
        "Prefer route-level replacement only after workflow review",
    )
    return (
        f"Overlap: decision is replace, keep both, or cancel. Tool D covers Tool A plus extras.\n"
        f"\n"
        f"{rec}"
        f"  Adds:                    {_fmt(ctx.get('new_features'), ctx, 'N/A')}\n"
        f"  New permissions:         {_fmt(ctx.get('delta_permissions'), ctx, 'N/A')}\n"
        f"  Performance delta:       D is {ctx.get('perf_delta', '?')}ms {ctx.get('perf_direction', 'slower')} than A\n"
        f"  Community score:         D rated {ctx.get('d_community', '?')} vs A rated {ctx.get('a_community', '?')}\n"
        f"  Workflows using A:       {_fmt(ctx.get('a_workflows'), ctx)}\n"
    )


def case_2_options(extensible: bool = False) -> list[str]:
    opts = [
        "Install D, route overlapping tasks to D (recommended after workflow review)",
        "Install D, keep both route sets active",
    ]
    if extensible:
        opts.append(
            "Activate only D's new routes as an extension to A"
        )
    opts.append("Cancel installation of D")
    return opts


def case_3_parent_child(ctx: dict) -> str:
    """Case 3 — Parent/Child (B already covers what D does)."""
    rec = _recommendation_line(
        ctx,
        "Keep B as default unless D is needed for a specialized route",
    )
    return (
        f"Redundancy: decision is install only for specialization, replace B, or cancel. Existing tool B is broader.\n"
        f"\n"
        f"{rec}"
        f"  B-only features:              {_fmt(ctx.get('b_extra_features'), ctx, 'N/A')}\n"
        f"  Specialization argument for D: D runs {ctx.get('perf_delta', '?')}ms faster for {ctx.get('specialization', 'specific task')}\n"
        f"  D's dependency footprint:      {ctx.get('dep_footprint', 'N/A')}\n"
        f"  Trust: D={ctx.get('d_trust', '?')} vs B={ctx.get('b_trust', '?')}\n"
    )


def case_3_options() -> list[str]:
    return [
        "Install D for specialized use (keep B)",
        "Install D, route B's tasks to D only if D covers current usages",
        "Cancel — use B as-is",
    ]


def case_4_exact_match(ctx: dict) -> str:
    """Case 4 — Exact Match (identical operational footprints)."""
    rec = _recommendation_line(
        ctx,
        "Keep the currently routed package unless D clearly has better trust or maintenance",
    )
    return (
        f"Exact duplicate: decision is swap duplicate tools or keep current tool C.\n"
        f"\n"
        f"{rec}"
        f"  Comparison:\n"
        f"    Community prefers:    {ctx.get('preferred_tool', 'N/A')} — reason: {ctx.get('preference_reason', 'N/A')}\n"
        f"    Dependency difference: {ctx.get('dep_diff', 'N/A')}\n"
        f"    Maintenance:           D last updated {ctx.get('d_updated_days', '?')} days ago vs C {ctx.get('c_updated_days', '?')} days ago\n"
        f"    Trust scores:          D={ctx.get('d_trust', '?')} vs C={ctx.get('c_trust', '?')}\n"
        f"  Workflows using C:       {_fmt(ctx.get('c_workflows'), ctx)} — update these if you swap.\n"
    )


def case_4_options() -> list[str]:
    return [
        "Install D, route duplicate tasks to D",
        "Cancel — keep C",
    ]


def case_5_tangential(ctx: dict) -> str:
    """Case 5 — Tangential Overlap."""
    shared = ctx.get("shared", [])
    d_only = ctx.get("d_only", [])
    x_only = ctx.get("x_only", [])
    return (
        f"Partial Overlap: decision is keep both if both unique feature sets matter.\n"
        f"\n"
        f"{_recommendation_line(ctx, 'Keep both and split routes by unique capability')}"
        f"  D only: {_fmt(d_only, ctx)}\n"
        f"  Shared: {_fmt(shared, ctx)}\n"
        f"  X only: {_fmt(x_only, ctx)}\n"
    )


def case_5_options() -> list[str]:
    return [
        "Install both — no true redundancy if your workflows need features from both",
        "Install D only — only if X's unique features are unused in your workflows",
        "Cancel — keep X as-is",
    ]


def case_dep_conflict(ctx: dict) -> str:
    """Case DEP — Dependency Conflict (v5 with parse errors)."""
    lines = [
        "Dependency Conflict: review needed\n",
        "  Why it matters: unresolved dependencies can break existing tools or hide an unsafe install.",
        _recommendation_line(
            ctx,
            "Prefer isolated install/update and re-index routes after verification",
        ).rstrip(),
    ]
    conflicts = _conflict_lines(ctx)
    if conflicts:
        lines.append("\n  Hard conflicts:")
        lines.extend(conflicts)
    parse_errors = ctx.get("parse_errors", [])
    if parse_errors:
        lines.append("\n  Specifiers that could not be parsed:")
        for pe in parse_errors[: _max_items(ctx)]:
            lines.append(
                f"  - {pe['package']}: \"{pe['specifier']}\" — {pe['error']}"
            )
        if len(parse_errors) > _max_items(ctx):
            lines.append(f"  - +{len(parse_errors) - _max_items(ctx)} more parse errors")
    lines.append("")
    return "\n".join(lines)


def case_dep_options(parse_only: bool = False) -> list[str]:
    if parse_only:
        return [
            "Install D in an isolated virtual environment and keep dependency graph unchanged",
            "Cancel installation of D",
        ]
    return [
        "Install D in an isolated virtual environment (safe, but higher memory overhead)",
        "Upgrade the package and re-test dependent tools",
        "Cancel installation of D",
    ]


def case_trust_warn(ctx: dict) -> str:
    """Case TRUST_WARN — Low Trust Score."""
    lines = [
        f"Low Trust: decision is override or cancel. Score: {ctx.get('score', 0)}/1.0\n",
        _recommendation_line(
            ctx,
            "Cancel unless the human explicitly accepts the risk",
        ).rstrip(),
        "  Risk factors:",
    ]
    factors = ctx.get("factors", {})
    if isinstance(factors, str):
        factors = {"reason": factors}
    for factor, detail in list(factors.items())[: _max_items(ctx)]:
        lines.append(f"    {factor}: {detail}")
    if not factors:
        lines.append("    None provided")
    lines.append("")
    return "\n".join(lines)


def case_trust_warn_options() -> list[str]:
    return [
        "Proceed anyway (I accept the risk)",
        "Cancel",
    ]


def case_trust_degraded(ctx: dict) -> str:
    """Case TRUST_DEGRADED — Trust Score Dropped Post-Install (v5)."""
    lines = [
        f"Trust Degraded: decision needed for {ctx.get('tool_name', '?')} ({ctx.get('tool_id', '?')})\n",
        _recommendation_line(
            ctx,
            "Disable active routing until the trust change is reviewed",
        ).rstrip(),
        f"  Approved at install: {ctx.get('score_at_install', '?')}/1.0",
        f"  Current score:       {ctx.get('current_score', '?')}/1.0",
        f"  Last checked:        {ctx.get('last_evaluated', '?')}\n",
        "  What changed:",
    ]
    for factor, detail in list(ctx.get("changes", {}).items())[: _max_items(ctx)]:
        lines.append(f"    {factor}: {detail}")
    lines.append("")
    return "\n".join(lines)


def case_trust_degraded_options() -> list[str]:
    return [
        "Keep installed — I accept the updated risk",
        "Disable Skills Router routing until reviewed",
        "Remind me in 7 days",
    ]


def case_llm_unknown(ctx: dict) -> str:
    """Case LLM_UNKNOWN — No Behavioral Embedding Available."""
    rec = _recommendation_line(
        ctx,
        "Ask the human to compare package READMEs before route activation",
    )
    return (
        f"Cannot Auto-Compare: LLM behavior cannot be safely compared for {ctx.get('tool_name', '?')}.\n"
        f"\n"
        f"{rec}"
        f"  One or both tools lack a verified BehaviorSpec embedding:\n"
        f"    · New tool:      {ctx.get('new_tool_name', '?')} — embedding_confidence: {ctx.get('new_confidence', '?')}\n"
        f"    · Existing tool: {ctx.get('existing_tool_name', '?')} — embedding_confidence: {ctx.get('existing_confidence', '?')}\n"
    )


def case_llm_unknown_options() -> list[str]:
    return [
        "Install anyway — treat as brand new scope (higher risk of silent redundancy)",
        "Review tool READMEs manually, then decide",
        "Cancel installation",
    ]


def case_llm_overlap(ctx: dict) -> str:
    """Case LLM_OVERLAP — LLM tools with behavioral overlap."""
    rec = _recommendation_line(
        ctx,
        "Route overlapping behavior to the safer package and keep the other inactive",
    )
    return (
        f"LLM Behavioral Overlap: decision needed.\n"
        f"\n"
        f"{rec}"
        f"  Combined similarity score: {ctx.get('combined_score', '?')}\n"
        f"  Shared behaviors:          {_fmt(ctx.get('shared_behaviors', []), ctx)}\n"
        f"  New-only behaviors:        {_fmt(ctx.get('new_only_behaviors', []), ctx)}\n"
    )


def case_llm_overlap_options() -> list[str]:
    return [
        "Install new tool, route overlapping behavior to it",
        "Install both — behaviors are complementary",
        "Cancel installation",
    ]


# -- Template registry -------------------------------------------------------

TEMPLATES: dict[str, tuple] = {
    "CASE_1": (case_1_brand_new, case_1_options),
    "CASE_2": (case_2_partial_overlap, case_2_options),
    "CASE_3": (case_3_parent_child, case_3_options),
    "CASE_4": (case_4_exact_match, case_4_options),
    "CASE_5": (case_5_tangential, case_5_options),
    "CASE_DEP": (case_dep_conflict, case_dep_options),
    "CASE_TRUST_WARN": (case_trust_warn, case_trust_warn_options),
    "CASE_TRUST_DEGRADED": (case_trust_degraded, case_trust_degraded_options),
    "CASE_LLM_UNKNOWN": (case_llm_unknown, case_llm_unknown_options),
    "CASE_LLM_OVERLAP": (case_llm_overlap, case_llm_overlap_options),
}
