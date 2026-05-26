"""Discover host-agent skills that are installed outside Skills Router state."""

from __future__ import annotations

import copy
import hashlib
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from skills_router.config import SkillsRouterConfig
from skills_router.storage.memory_store import MemoryBrainIndexStore


def discover_installed_skillsets(
    config: SkillsRouterConfig,
    *,
    requested_names: list[str] | None = None,
    workspace_scope: str | None = None,
) -> dict[str, Any]:
    """Discover installed AI-agent skillsets from known local/global sources.

    This intentionally discovers metadata only. Skills Router never assumes
    ownership of host-installed package files; it imports enough manifest shape
    to compare routes and ask the human before activating new external routes.
    """
    requested_keys = _requested_keys(requested_names or [])
    records: list[dict[str, Any]] = []
    warnings: list[str] = []

    local_scope = (
        workspace_scope
        if workspace_scope and workspace_scope.startswith("workspace:")
        else "workspace:local"
    )
    for record in _discover_workspace_skill_files(
        config,
        requested_keys,
        local_scope,
        warnings,
    ):
        records.append(record)
    for record in _discover_global_skills_router(config, requested_keys, warnings):
        records.append(record)
    for record in _discover_global_skill_files(config, requested_keys, warnings):
        records.append(record)

    deduped = _dedupe_records(records)
    matched_keys = _matched_requested_keys(deduped, requested_keys)
    return {
        "status": "OK",
        "records": deduped,
        "record_count": len(deduped),
        "sources": sorted({record["source"] for record in deduped}),
        "requested": list(requested_names or []),
        "unmatched_requested": [
            name for name in (requested_names or [])
            if _normalise_key(name) not in matched_keys
        ],
        "warnings": warnings,
    }


def _discover_workspace_skill_files(
    config: SkillsRouterConfig,
    requested_keys: set[str],
    local_scope: str,
    warnings: list[str],
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    workspace_root = Path(config.workspace_root)
    for raw_dir in config.workspace_skill_dirs:
        path = _expand_discovery_path(raw_dir, workspace_root=workspace_root)
        if path is None:
            continue
        records.extend(
            _discover_skill_files(
                path,
                requested_keys,
                scope=local_scope,
                source="workspace-skill-dir",
                warnings=warnings,
            )
        )
    return records


def _discover_global_skill_files(
    config: SkillsRouterConfig,
    requested_keys: set[str],
    warnings: list[str],
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for raw_dir in config.global_skill_dirs:
        path = _expand_discovery_path(raw_dir, workspace_root=Path(config.workspace_root))
        if path is None:
            continue
        records.extend(
            _discover_skill_files(
                path,
                requested_keys,
                scope="global",
                source="global-skill-dir",
                warnings=warnings,
            )
        )
    return records


def _discover_global_skills_router(
    config: SkillsRouterConfig,
    requested_keys: set[str],
    warnings: list[str],
) -> list[dict[str, Any]]:
    current_dir = Path(config.data_dir).expanduser().resolve()
    global_dir = Path(config.global_data_dir).expanduser().resolve()
    if current_dir == global_dir:
        return []

    brain_index_path = global_dir / "brain_index.json"
    dep_graph_path = global_dir / "dep_graph.json"
    if not brain_index_path.exists():
        return []

    try:
        store = MemoryBrainIndexStore(
            brain_index_path=str(brain_index_path),
            dep_graph_path=str(dep_graph_path),
        )
    except Exception as exc:
        warnings.append(f"Could not read global Skills Router index: {exc}")
        return []

    records: list[dict[str, Any]] = []
    for tool in store.get_all_tools():
        manifest = copy.deepcopy(tool)
        if not _matches_requested(manifest, requested_keys):
            continue
        meta = manifest.setdefault("layer_meta", {})
        meta.setdefault("install_scope", "global")
        meta["discovered_source"] = "skills-router-global"
        meta["discovered_path"] = str(brain_index_path)
        records.append({
            "tool_id": manifest["tool_id"],
            "name": manifest.get("name", manifest["tool_id"]),
            "source": "skills-router-global",
            "path": str(brain_index_path),
            "external": False,
            "manifest": manifest,
        })
    return records


def _discover_skill_files(
    root: Path,
    requested_keys: set[str],
    *,
    scope: str,
    source: str,
    warnings: list[str],
) -> list[dict[str, Any]]:
    if not root.exists() or not root.is_dir():
        return []

    records: list[dict[str, Any]] = []
    for skill_file in sorted(root.rglob("SKILL.md")):
        try:
            manifest = _skill_file_manifest(skill_file, scope=scope, source=source)
        except Exception as exc:
            warnings.append(f"Could not read skill file {skill_file}: {exc}")
            continue
        if not _matches_requested(manifest, requested_keys):
            continue
        records.append({
            "tool_id": manifest["tool_id"],
            "name": manifest.get("name", manifest["tool_id"]),
            "source": source,
            "path": str(skill_file),
            "external": True,
            "manifest": manifest,
        })
    return records


def _skill_file_manifest(path: Path, *, scope: str, source: str) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    frontmatter = _parse_frontmatter(text)
    name = frontmatter.get("name") or path.parent.name
    description = frontmatter.get("description") or _first_content_line(text) or name
    tool_id = _stable_tool_id(name or path.parent.name)
    skill_id = _stable_tool_id(name)
    fingerprint = hashlib.sha256(text.encode("utf-8")).hexdigest()
    now = datetime.now(timezone.utc).isoformat()

    return {
        "tool_id": tool_id,
        "name": name,
        "version": "0.0.0",
        "dependencies": {},
        "layer_1_domain_tags": ["ai-agent-skill", source],
        "layer_3_capabilities": {
            "inputs": ["natural language task request"],
            "outputs": [description],
            "permissions": [],
            "extensible": False,
        },
        "layer_5_provenance": {
            "publisher_id": "host-agent",
            "signature_hash": fingerprint,
            "signature_verified": False,
            "trust_score": 0.66,
            "trust_factors": {
                "publisher_known": False,
                "github_stars": 0,
                "last_commit_days_ago": 999,
                "open_critical_cves": 0,
                "community_sentiment_score": 0.5,
            },
            "install_source": source,
            "published_at": "",
            "trust_score_last_evaluated": now,
        },
        "layer_6_behavior_spec": {
            "tool_type": "agent_skill",
            "declared_behaviors": [description],
            "known_nondeterminism": "host-agent skill behavior may depend on agent runtime",
            "behavioral_embedding": [],
            "embedding_confidence": "auto",
            "spec_superseded_by": None,
            "tested_input_output_pairs": [],
        },
        "layer_meta": {
            "dependent_workflows": [],
            "install_scope": scope,
            "agent_id": None,
            "installed_at": now,
            "version_pin_strategy": "external",
            "physical_install": "external_discovery",
            "skills_router_discovered": True,
            "discovered_source": source,
            "discovered_path": str(path),
            "discovered_sha256": fingerprint,
            "discovered_at": now,
        },
        "agent_package": {
            "type": "skillset",
            "skillsets": [
                {
                    "id": skill_id,
                    "name": name,
                    "description": description,
                    "use_when": description,
                    "permissions": [],
                }
            ],
        },
    }


def _parse_frontmatter(text: str) -> dict[str, str]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    meta: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        if key:
            meta[key] = value.strip().strip("\"'")
    return meta


def _first_content_line(text: str) -> str | None:
    in_frontmatter = False
    for idx, line in enumerate(text.splitlines()):
        stripped = line.strip()
        if idx == 0 and stripped == "---":
            in_frontmatter = True
            continue
        if in_frontmatter:
            if stripped == "---":
                in_frontmatter = False
            continue
        if stripped and not stripped.startswith("#"):
            return stripped
    return None


def _expand_discovery_path(raw: str, *, workspace_root: Path) -> Path | None:
    expanded = os.path.expandvars(os.path.expanduser(raw))
    if "$" in expanded or "%" in expanded:
        return None
    path = Path(expanded)
    if not path.is_absolute():
        path = workspace_root / path
    return path


def _dedupe_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_tool_id: dict[str, dict[str, Any]] = {}
    for record in records:
        by_tool_id.setdefault(record["tool_id"], record)
    return list(by_tool_id.values())


def _requested_keys(names: list[str]) -> set[str]:
    return {_normalise_key(name) for name in names if _normalise_key(name)}


def _matched_requested_keys(
    records: list[dict[str, Any]],
    requested_keys: set[str],
) -> set[str]:
    matched: set[str] = set()
    for record in records:
        manifest = record["manifest"]
        candidates = _candidate_keys(manifest)
        matched.update(requested_keys & candidates)
    return matched


def _matches_requested(manifest: dict[str, Any], requested_keys: set[str]) -> bool:
    if not requested_keys:
        return True
    return bool(_candidate_keys(manifest) & requested_keys)


def _candidate_keys(manifest: dict[str, Any]) -> set[str]:
    values = [
        manifest.get("tool_id", ""),
        manifest.get("name", ""),
    ]
    package = manifest.get("agent_package", {})
    for key in ("skillsets", "plugins"):
        raw = package.get(key) or manifest.get(key) or []
        values.extend(_skill_candidate_values(raw))
    return {_normalise_key(value) for value in values if _normalise_key(value)}


def _skill_candidate_values(raw: Any) -> list[str]:
    values: list[str] = []
    if isinstance(raw, dict):
        for key, value in raw.items():
            values.append(str(key))
            if isinstance(value, dict):
                values.extend(str(value.get(field, "")) for field in ("id", "name"))
            else:
                values.append(str(value))
    elif isinstance(raw, list):
        for item in raw:
            if isinstance(item, dict):
                values.extend(str(item.get(field, "")) for field in ("id", "name"))
            else:
                values.append(str(item))
    elif raw:
        values.append(str(raw))
    return values


def _normalise_key(value: str) -> str:
    return _slug(str(value).strip().lower())


def _stable_tool_id(value: str) -> str:
    slug = _slug(value)
    if len(slug) >= 2:
        return slug[:128].strip("-")
    return f"{slug or 'ai'}-skill"


def _slug(value: str) -> str:
    chars: list[str] = []
    previous_dash = False
    for char in value.lower():
        if char.isalnum():
            chars.append(char)
            previous_dash = False
        elif not previous_dash:
            chars.append("-")
            previous_dash = True
    return "".join(chars).strip("-")
