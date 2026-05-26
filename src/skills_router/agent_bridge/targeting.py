"""Target selection helpers for all-agent installs."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from skills_router.agent_bridge.profiles import (
    AgentProfile,
    default_all_agent_targets,
    get_agent_profile,
    normalize_agent_target,
)
from skills_router.config import SkillsRouterConfig


_GENERIC_INSTRUCTION_FILES = {"AGENTS.md"}
_GENERIC_WORKSPACE_SKILL_DIRS = {".agents/skills"}


def normalize_agent_targets(values: list[str] | tuple[str, ...] | None) -> list[str]:
    """Normalize a possibly comma-separated target list while preserving order."""
    seen: set[str] = set()
    normalized: list[str] = []
    for raw in values or []:
        for item in str(raw).split(","):
            target = item.strip()
            if not target:
                continue
            canonical = normalize_agent_target(target)
            if canonical in seen:
                continue
            normalized.append(canonical)
            seen.add(canonical)
    return normalized


def default_one_time_targets() -> list[str]:
    """Return canonical targets for the one-time all-agent install workflow."""
    return list(default_all_agent_targets())


def build_agent_target_report(
    config: SkillsRouterConfig,
    *,
    targets: list[str] | tuple[str, ...] | None = None,
) -> dict[str, Any]:
    """Describe where a global one-time skill install applies.

    The install is still stored once in Skills Router. Each target uses the
    same global route state through MCP or the CLI bridge.
    """
    target_names = normalize_agent_targets(targets) or default_one_time_targets()
    entries = [
        _target_entry(get_agent_profile(target), config)
        for target in target_names
    ]
    installed = [entry for entry in entries if entry["installed"]]
    return {
        "status": "OK",
        "mode": "all_agents",
        "scope": "global",
        "target_names": target_names,
        "target_count": len(entries),
        "installed_target_count": len(installed),
        "targets": entries,
        "routing_note": (
            "One global Skills Router route is visible to every workspace "
            "agent scope. Configure each host's bridge prompt or MCP server to "
            "use the shared route lookup."
        ),
    }


def _target_entry(profile: AgentProfile, config: SkillsRouterConfig) -> dict[str, Any]:
    evidence_paths = _existing_target_paths(profile, config)
    return {
        "target": profile.target,
        "display_name": profile.display_name,
        "installed": bool(evidence_paths),
        "evidence_paths": evidence_paths,
        "instruction_files": list(profile.instruction_files),
        "workspace_skill_dirs": list(profile.workspace_skill_dirs),
        "global_skill_dirs": list(profile.global_skill_dirs),
        "mcp_config_hint": profile.mcp_config_hint,
        "invocation_hint": profile.invocation_hint,
    }


def _existing_target_paths(profile: AgentProfile, config: SkillsRouterConfig) -> list[str]:
    workspace_root = Path(config.workspace_root)
    existing: list[str] = []

    for raw in profile.instruction_files:
        if raw in _GENERIC_INSTRUCTION_FILES:
            continue
        path = _resolve_path(raw, workspace_root=workspace_root)
        if path is not None and path.exists():
            existing.append(str(path))

    for raw in profile.workspace_skill_dirs:
        if _is_generic_workspace_skill_dir(raw):
            continue
        path = _resolve_path(raw, workspace_root=workspace_root)
        if path is not None and path.exists():
            existing.append(str(path))

    for raw in profile.global_skill_dirs:
        path = _resolve_path(raw, workspace_root=workspace_root)
        if path is not None and path.exists():
            existing.append(str(path))

    return sorted(dict.fromkeys(existing))


def _is_generic_workspace_skill_dir(raw: str) -> bool:
    normalized = raw.strip().replace("\\", "/").rstrip("/")
    return normalized in _GENERIC_WORKSPACE_SKILL_DIRS


def _resolve_path(raw: str, *, workspace_root: Path) -> Path | None:
    expanded = os.path.expandvars(os.path.expanduser(raw))
    if "$" in expanded or "%" in expanded:
        return None
    path = Path(expanded)
    if not path.is_absolute():
        path = workspace_root / path
    return path
