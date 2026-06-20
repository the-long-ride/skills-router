"""Build a skill inventory that AI agents can consume.

Reads the routing file and Brain Index to generate a structured list of
installed skills with their ``use_when`` triggers, prompt snippets, and
SKILL.md content.  The inventory is injected into the connect bridge
prompt so agents know *what* is installed, and the ``use`` slash
command reads a specific skill's content for agent injection.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from skills_router.agent_bridge.routing import read_routing_state
from skills_router.config import SkillsRouterConfig
from skills_router.storage.base import AbstractBrainIndexStore
from skills_router.storage.memory_store import MemoryBrainIndexStore


def build_skill_inventory(
    config: SkillsRouterConfig,
    store: AbstractBrainIndexStore | None = None,
) -> dict[str, Any]:
    """Return a structured inventory of installed skills.

    Returns a dict with:
      - ``skills``: list of skill entries
      - ``active`` / ``pending`` / ``inactive``: filtered views
      - ``count`` / ``active_count`` / ``pending_count``: counts
      - ``human_summary``: one-line summary
    """
    routing = read_routing_state(config)
    if store is None:
        store = MemoryBrainIndexStore(config.brain_index_path)

    packages = routing.get("packages", {})
    skills: list[dict[str, Any]] = []

    for tool_id, package in packages.items():
        brain_entry = store.get_tool(tool_id) or {}
        rules = package.get("rules", [])
        for rule in rules:
            if rule.get("status") == "missing_from_index":
                continue
            skill = {
                "tool_id": tool_id,
                "rule_id": rule.get("rule_id", f"{tool_id}:default"),
                "skill_id": rule.get("skill_id", "default"),
                "name": rule.get("name") or package.get("name", tool_id),
                "scope": rule.get("scope") or package.get("scope", "global"),
                "status": rule.get("status") or package.get("status", "active"),
                "use_when": rule.get("use_when", ""),
                "prompt_snippet": rule.get("prompt_snippet", ""),
                "priority": rule.get("priority", 100),
                "package_type": package.get("package_type", "tool"),
                "version": package.get("version", ""),
                "has_skill_md": bool(
                    brain_entry.get("source_metadata", {}).get("has_skill_md", False)
                ),
                "source_ref": brain_entry.get("_source_ref", ""),
            }
            skills.append(skill)

    active = [s for s in skills if s["status"] == "active"]
    pending = [s for s in skills if s["status"] == "needs_selection"]
    inactive = [s for s in skills if s["status"] not in ("active", "needs_selection")]

    return {
        "skills": skills,
        "active": active,
        "pending": pending,
        "inactive": inactive,
        "count": len(skills),
        "active_count": len(active),
        "pending_count": len(pending),
        "human_summary": (
            f"{len(active)} active skill(s), "
            f"{len(pending)} pending selection"
        ),
    }


def render_inventory_markdown(inventory: dict[str, Any]) -> str:
    """Render a compact Markdown section listing installed skills.

    Designed to be appended to the connect bridge prompt so agents
    see available skills in their context.
    """
    active = inventory.get("active", [])
    pending = inventory.get("pending", [])

    if not active and not pending:
        return (
            "## Installed Skills\n\n"
            "No skills are currently installed via Skills Router. "
            "Use `/skills-router install <package>` to add one.\n"
        )

    lines = ["## Installed Skills", ""]

    if active:
        lines.append("### Active")
        for skill in active:
            use_when = skill["use_when"] or "(any task)"
            lines.append(
                f"- **{skill['name']}** "
                f"(`{skill['tool_id']}.{skill['skill_id']}`)"
            )
            lines.append(f"  Use when: {use_when}")
        lines.append("")

    if pending:
        lines.append("### Pending Selection")
        for skill in pending:
            lines.append(
                f"- **{skill['name']}** "
                f"(`{skill['tool_id']}.{skill['skill_id']}`)"
            )
            lines.append("  Status: needs activation before use")
        lines.append("")

    lines.append(
        "To load a skill into context, use `/skills-router use <tool_id>`. "
        "To list skills: `/skills-router list`."
    )

    return "\n".join(lines)


def use_skill(
    config: SkillsRouterConfig,
    tool_id: str,
    store: AbstractBrainIndexStore | None = None,
) -> dict[str, Any]:
    """Load a skill for injection into an AI agent's context.

    Looks up the skill in the brain index and routing state, then
    builds a prompt-ready document containing routing metadata and
    cached SKILL.md content.

    Returns a dict with ``content`` (the full prompt text) and
    ``metadata`` (structured info about the skill).
    """
    if store is None:
        store = MemoryBrainIndexStore(config.brain_index_path)

    brain_entry = store.get_tool(tool_id)
    routing = read_routing_state(config)
    package = routing.get("packages", {}).get(tool_id, {})

    if brain_entry is None and not package:
        return {
            "status": "NOT_FOUND",
            "tool_id": tool_id,
            "error": f"No installed skill found for '{tool_id}'",
        }

    if brain_entry is None:
        brain_entry = {}

    rules = package.get("rules", [])

    name = brain_entry.get("name") or package.get("name", tool_id)
    version = brain_entry.get("version") or package.get("version", "")
    description = brain_entry.get("description", "")
    source_ref = brain_entry.get("_source_ref", "")

    sections = [
        f"# Skills Router: {name}",
        "",
        f"**Tool ID:** `{tool_id}`",
    ]
    if version:
        sections.append(f"**Version:** {version}")
    if description:
        sections.append(f"**Description:** {description}")
    if source_ref:
        sections.append(f"**Source:** {source_ref}")

    # Skill content from brain index
    skill_md_content = _extract_skill_md_content(brain_entry)
    if skill_md_content:
        sections.append("")
        sections.append("## Skill Content")
        sections.append("")
        sections.append(skill_md_content)

    # Routing rules
    if rules:
        sections.append("")
        sections.append("## Routing Rules")
        for rule in rules:
            rule_id = rule.get("rule_id", f"{tool_id}:default")
            use_when = rule.get("use_when", "(any)")
            prompt = rule.get("prompt_snippet", "")
            sections.append(f"- **{rule_id}**: {use_when}")
            if prompt:
                sections.append(f"  {prompt}")

    # Capabilities
    capabilities = (
        brain_entry.get("layer_3_capabilities")
        or brain_entry.get("capabilities", {})
    )
    if capabilities:
        inputs_list = capabilities.get("inputs", [])
        outputs_list = capabilities.get("outputs", [])
        if inputs_list or outputs_list:
            sections.append("")
            sections.append("## Capabilities")
            if outputs_list:
                sections.append(
                    f"- **Outputs:** {', '.join(outputs_list)}"
                )
            if inputs_list:
                sections.append(
                    f"- **Inputs:** {', '.join(inputs_list)}"
                )

    # Domain tags
    domains = brain_entry.get("layer_1_domain_tags", [])
    if domains:
        sections.append("")
        sections.append(f"**Domains:** {', '.join(domains)}")

    # Trust info
    trust = brain_entry.get("layer_5_provenance", {})
    if trust:
        provider = trust.get("provider") or trust.get("publisher", "")
        score = trust.get("trust_score")
        if provider:
            sections.append(f"**Provider:** {provider}")
        if score is not None:
            sections.append(
                f"**Trust Score:** {score:.0%}"
                if isinstance(score, float) and score <= 1
                else f"**Trust Score:** {score}"
            )

    sections.append("")
    sections.append(
        "---\n"
        "*This skill is managed by Skills Router. "
        "Use `/skills-router list` to see all installed skills.*"
    )

    content = "\n".join(sections)

    metadata = {
        "tool_id": tool_id,
        "name": name,
        "version": version,
        "use_when": rules[0].get("use_when", "") if rules else "",
        "status": package.get("status", "active"),
        "scope": package.get("scope", "global"),
        "has_skill_md": bool(skill_md_content),
    }

    return {
        "status": "OK",
        "tool_id": tool_id,
        "content": content,
        "metadata": metadata,
        "human_summary": (
            f"Loaded skill '{name}' — "
            f"{len(content)} chars ready for agent injection."
        ),
    }


def _extract_skill_md_content(brain_entry: dict[str, Any]) -> str | None:
    """Extract SKILL.md body from the brain index entry if stored."""
    source_md = brain_entry.get("source_metadata", {})
    for key in ("skill_md_content", "readme_content", "description_long"):
        value = source_md.get(key)
        if isinstance(value, str) and len(value.strip()) > 10:
            return value.strip()

    manifest_md = (
        brain_entry.get("agent_package", {}).get("skill_content")
    )
    if isinstance(manifest_md, str) and len(manifest_md.strip()) > 10:
        return manifest_md.strip()

    return None
