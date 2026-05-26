"""Generate and persist agent routing rules for installed skill/plugin packages."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from skills_router.agent_bridge.profiles import (
    default_all_agent_targets,
    normalize_agent_target,
)
from skills_router.config import SkillsRouterConfig


ROUTING_FILE_NAME = "skills-router.json"


@dataclass
class SkillRoute:
    """One AI-agent route into an installed package."""

    rule_id: str
    tool_id: str
    package_type: str
    skill_id: str
    name: str
    scope: str
    status: str
    use_when: str
    permissions: list[str] = field(default_factory=list)
    priority: int = 100
    prompt_snippet: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "tool_id": self.tool_id,
            "package_type": self.package_type,
            "skill_id": self.skill_id,
            "name": self.name,
            "scope": self.scope,
            "status": self.status,
            "use_when": self.use_when,
            "permissions": list(self.permissions),
            "priority": self.priority,
            "prompt_snippet": self.prompt_snippet,
        }


def build_routing_plan(
    manifest: dict[str, Any],
    *,
    scope: str,
    package_type: str = "auto",
    routing_mode: str = "full_package",
    target_agents: list[str] | tuple[str, ...] | None = None,
) -> dict[str, Any]:
    """Build routing rules for a complete installed package.

    Skills Router should install whole packages by default, then use this routing
    layer to decide which skills/plugins an AI agent should actively call.
    """
    resolved_type = infer_package_type(manifest, package_type)
    skillsets = _extract_skillsets(manifest)
    selective = routing_mode == "selective_routes"
    status = "needs_selection" if selective else "active"
    agents = _unique_agent_targets(target_agents or [])
    rules = [
        _build_route(
            manifest,
            skill,
            package_type=resolved_type,
            scope=scope,
            status=status,
            index=idx,
        )
        for idx, skill in enumerate(skillsets, start=1)
    ]

    return {
        "tool_id": manifest["tool_id"],
        "name": manifest.get("name", manifest["tool_id"]),
        "version": manifest.get("version", ""),
        "package_type": resolved_type,
        "physical_install": "full_package",
        "routing_mode": routing_mode,
        "scope": scope,
        "status": status,
        "target_agents": agents,
        "applies_to_all_agents": _applies_to_all_default_targets(agents),
        "rules": [rule.to_dict() for rule in rules],
        "human_summary": _routing_summary(manifest, resolved_type, routing_mode, len(rules)),
    }


def persist_routing_plan(config: SkillsRouterConfig, plan: dict[str, Any]) -> None:
    """Upsert routes from a successful package install into the routing file."""
    path = routing_file_path(config)
    data = _read_routing_file(path)
    now = datetime.now(timezone.utc).isoformat()
    data["updated_at"] = now
    packages = data.setdefault("packages", {})
    packages[plan["tool_id"]] = {
        "tool_id": plan["tool_id"],
        "name": plan.get("name", ""),
        "version": plan.get("version", ""),
        "package_type": plan.get("package_type", "tool"),
        "physical_install": plan.get("physical_install", "full_package"),
        "routing_mode": plan.get("routing_mode", "full_package"),
        "scope": plan.get("scope", "global"),
        "status": plan.get("status", "active"),
        "target_agents": plan.get("target_agents", []),
        "applies_to_all_agents": bool(plan.get("applies_to_all_agents", False)),
        "rules": plan.get("rules", []),
        "updated_at": now,
    }
    _write_routing_file(path, data)


def read_routing_state(config: SkillsRouterConfig) -> dict[str, Any]:
    """Read the local routing state without mutating it."""
    return _read_routing_file(routing_file_path(config))


def write_routing_state(config: SkillsRouterConfig, data: dict[str, Any]) -> None:
    """Persist the local routing state."""
    _write_routing_file(routing_file_path(config), data)


def remove_tool_routes(config: SkillsRouterConfig, tool_id: str) -> bool:
    """Remove Skills Router-owned routing rules for one indexed package."""
    path = routing_file_path(config)
    data = _read_routing_file(path)
    packages = data.setdefault("packages", {})
    if tool_id not in packages:
        return False
    del packages[tool_id]
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    _write_routing_file(path, data)
    return True


def route_task(
    config: SkillsRouterConfig,
    task: str,
    *,
    scope: str | None = None,
    agent_target: str | None = None,
    limit: int = 5,
    include_inactive: bool = False,
) -> dict[str, Any]:
    """Return current routing candidates for a natural-language task."""
    query = task.strip()
    if not query:
        return {"status": "ERROR", "error": "Task text is required"}
    try:
        normalized_agent_target = (
            normalize_agent_target(agent_target) if agent_target else None
        )
    except ValueError as exc:
        return {"status": "ERROR", "error": str(exc)}

    data = read_routing_state(config)
    active: list[dict[str, Any]] = []
    review: list[dict[str, Any]] = []
    for package in data.get("packages", {}).values():
        if not _package_visible(package, scope, normalized_agent_target):
            continue
        if package.get("status") == "missing_from_index":
            continue
        for rule in package.get("rules", []):
            candidate = _route_candidate(query, package, rule)
            if candidate is None:
                continue
            status = candidate["status"]
            if status == "active":
                active.append(candidate)
            elif include_inactive or status == "needs_selection":
                review.append(candidate)

    active.sort(key=_route_sort_key)
    review.sort(key=_route_sort_key)
    if active:
        routes = active[:limit]
        return {
            "status": "OK",
            "task": query,
            "scope": scope,
            "agent_target": normalized_agent_target,
            "routes": routes,
            "recommendation": f"Route this task to {routes[0]['route']}.",
        }
    if review:
        routes = review[:limit]
        return {
            "status": "REVIEW_NEEDED",
            "task": query,
            "scope": scope,
            "agent_target": normalized_agent_target,
            "routes": routes,
            "recommendation": (
                "A matching route exists but needs human activation before use."
            ),
        }
    return {
        "status": "NO_ROUTE",
        "task": query,
        "scope": scope,
        "agent_target": normalized_agent_target,
        "routes": [],
        "recommendation": "No active Skills Router route matched this task.",
    }


def routing_file_path(config: SkillsRouterConfig) -> Path:
    """Return the local routing file path."""
    return Path(config.data_dir) / ROUTING_FILE_NAME


def _route_candidate(
    query: str,
    package: dict[str, Any],
    rule: dict[str, Any],
) -> dict[str, Any] | None:
    status = rule.get("status") or package.get("status", "")
    if status == "missing_from_index":
        return None
    score = _text_score(
        query,
        " ".join(
            str(value)
            for value in (
                package.get("name", ""),
                rule.get("name", ""),
                rule.get("use_when", ""),
                rule.get("prompt_snippet", ""),
            )
        ),
    )
    if score <= 0:
        return None
    tool_id = rule.get("tool_id") or package.get("tool_id")
    skill_id = rule.get("skill_id", "default")
    return {
        "route": f"{tool_id}.{skill_id}",
        "tool_id": tool_id,
        "skill_id": skill_id,
        "name": rule.get("name", package.get("name", tool_id)),
        "scope": rule.get("scope", package.get("scope", "global")),
        "status": status,
        "score": score,
        "priority": int(rule.get("priority", 100)),
        "target_agents": _unique_agent_targets(package.get("target_agents", [])),
        "use_when": rule.get("use_when", ""),
        "prompt_snippet": rule.get("prompt_snippet", ""),
    }


def _route_sort_key(candidate: dict[str, Any]) -> tuple[float, int, str]:
    return (-candidate["score"], candidate.get("priority", 100), candidate["route"])


def _package_visible(
    package: dict[str, Any],
    scope: str | None,
    agent_target: str | None,
) -> bool:
    if not scope:
        scope_visible = True
    else:
        package_scope = package.get("scope", "global")
        if scope == "global":
            scope_visible = package_scope == "global"
        else:
            scope_visible = package_scope in {"global", scope}
    if not scope_visible:
        return False
    if not agent_target:
        return True
    target_agents = _unique_agent_targets(package.get("target_agents", []))
    if not target_agents:
        return True
    return agent_target in target_agents


def _text_score(query: str, route_text: str) -> float:
    query_terms = _terms(query)
    route_terms = _terms(route_text)
    if not query_terms or not route_terms:
        return 0.0
    overlap = query_terms & route_terms
    if not overlap:
        return 0.0
    return round(len(overlap) / max(len(query_terms), 1), 4)


def _terms(text: str) -> set[str]:
    terms: set[str] = set()
    current: list[str] = []
    for char in text.lower():
        if char.isalnum():
            current.append(char)
        else:
            if len(current) >= 3:
                terms.add("".join(current))
            current = []
    if len(current) >= 3:
        terms.add("".join(current))
    return terms


def infer_package_type(manifest: dict[str, Any], requested: str = "auto") -> str:
    """Infer whether a manifest is a skillset, plugin, or generic tool."""
    if requested and requested != "auto":
        return requested
    package_meta = manifest.get("agent_package", {})
    explicit = (
        package_meta.get("type")
        or manifest.get("package_type")
        or manifest.get("agent_package_type")
    )
    if explicit:
        return _normalise_package_type(str(explicit))
    if package_meta.get("skillsets") or manifest.get("skillsets"):
        return "skillset"
    if package_meta.get("plugins") or manifest.get("plugins"):
        return "plugin"
    return "tool"


def _extract_skillsets(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    package_meta = manifest.get("agent_package", {})
    raw = (
        package_meta.get("skillsets")
        or package_meta.get("plugins")
        or manifest.get("skillsets")
        or manifest.get("plugins")
        or []
    )
    if raw:
        entries = _skill_entries(raw)
        return [
            _normalise_skill_entry(entry, idx)
            for idx, entry in enumerate(entries, start=1)
        ]

    caps = manifest.get("layer_3_capabilities", manifest.get("capabilities", {}))
    outputs = caps.get("outputs", [])
    domains = manifest.get("layer_1_domain_tags", [])
    description = ", ".join(outputs or domains or [manifest.get("name", manifest["tool_id"])])
    return [
        {
            "id": "default",
            "name": manifest.get("name", manifest["tool_id"]),
            "description": description,
            "use_when": description,
            "permissions": _listify(caps.get("permissions", [])),
        }
    ]


def _skill_entries(raw: Any) -> list[Any]:
    if isinstance(raw, dict):
        entries = []
        for key, value in raw.items():
            if isinstance(value, dict):
                with_id = dict(value)
                with_id.setdefault("id", key)
                entries.append(with_id)
            else:
                entries.append({"id": key, "name": str(value)})
        return entries
    if isinstance(raw, list):
        return raw
    return [raw]


def _normalise_skill_entry(entry: Any, index: int) -> dict[str, Any]:
    if isinstance(entry, str):
        return {
            "id": _slug(entry) or f"skill-{index}",
            "name": entry,
            "description": entry,
            "use_when": entry,
            "permissions": [],
        }
    if isinstance(entry, dict):
        name = str(entry.get("name") or entry.get("id") or f"skill-{index}")
        return {
            "id": _slug(str(entry.get("id") or name)) or f"skill-{index}",
            "name": name,
            "description": str(entry.get("description") or entry.get("use_when") or name),
            "use_when": str(entry.get("use_when") or entry.get("description") or name),
            "permissions": _listify(entry.get("permissions") or []),
        }
    return {
        "id": f"skill-{index}",
        "name": f"Skill {index}",
        "description": str(entry),
        "use_when": str(entry),
        "permissions": [],
    }


def _build_route(
    manifest: dict[str, Any],
    skill: dict[str, Any],
    *,
    package_type: str,
    scope: str,
    status: str,
    index: int,
) -> SkillRoute:
    tool_id = manifest["tool_id"]
    skill_id = skill["id"]
    rule = SkillRoute(
        rule_id=f"{tool_id}:{skill_id}",
        tool_id=tool_id,
        package_type=package_type,
        skill_id=skill_id,
        name=skill["name"],
        scope=scope,
        status=status,
        use_when=skill["use_when"],
        permissions=skill.get("permissions", []),
        priority=100 + index,
    )
    rule.prompt_snippet = _prompt_snippet(rule)
    return rule


def _prompt_snippet(rule: SkillRoute) -> str:
    permissions = ", ".join(rule.permissions) if rule.permissions else "none declared"
    return (
        f"When the task matches '{rule.use_when}', route to "
        f"{rule.tool_id}.{rule.skill_id}. Permissions: {permissions}."
    )


def _routing_summary(
    manifest: dict[str, Any],
    package_type: str,
    routing_mode: str,
    rule_count: int,
) -> str:
    if routing_mode == "selective_routes":
        return (
            f"Installed full {package_type} package {manifest['tool_id']}; "
            f"{rule_count} route(s) need user selection before activation."
        )
    return (
        f"Installed full {package_type} package {manifest['tool_id']}; "
        f"activated {rule_count} route(s)."
    )


def _normalise_package_type(value: str) -> str:
    cleaned = value.strip().lower().replace("_", "-")
    if cleaned in {"skill", "skills", "agent-skill", "agent-skills"}:
        return "skillset"
    if cleaned in {"plugin", "plugins", "agent-plugin", "agent-plugins"}:
        return "plugin"
    return cleaned or "tool"


def _unique_agent_targets(values: list[str] | tuple[str, ...]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        item = str(value).strip()
        if not item:
            continue
        item = normalize_agent_target(item)
        if item in seen:
            continue
        result.append(item)
        seen.add(item)
    return result


def _applies_to_all_default_targets(values: list[str]) -> bool:
    defaults = set(default_all_agent_targets())
    return bool(values) and len(values) == len(defaults) and set(values) == defaults


def _listify(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value if str(item)]
    return [str(value)]


def _slug(value: str) -> str:
    chars = []
    prev_dash = False
    for char in value.lower():
        if char.isalnum():
            chars.append(char)
            prev_dash = False
        elif not prev_dash:
            chars.append("-")
            prev_dash = True
    return "".join(chars).strip("-")


def _read_routing_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"version": 1, "packages": {}}
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        return {"version": 1, "packages": {}}
    data.setdefault("version", 1)
    data.setdefault("packages", {})
    return data


def _write_routing_file(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f".{path.name}.tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=True)
    try:
        tmp_path.replace(path)
    except PermissionError:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, sort_keys=True)
        try:
            tmp_path.unlink()
        except OSError:
            pass
