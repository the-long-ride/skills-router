"""Build local AI-agent connection instructions for Skills Router."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

from skills_router.agent_bridge.profiles import get_agent_profile, list_agent_profiles
from skills_router.agent_bridge.prompts import render_agent_prompt
from skills_router.config import SkillsRouterConfig


BEGIN_MARKER = "<!-- BEGIN SKILLS ROUTER BRIDGE -->"
END_MARKER = "<!-- END SKILLS ROUTER BRIDGE -->"
SKILL_BEGIN_MARKER = "<!-- BEGIN SKILLS ROUTER BRIDGE SKILL -->"
SKILL_END_MARKER = "<!-- END SKILLS ROUTER BRIDGE SKILL -->"
TOML_BEGIN_MARKER = "# BEGIN SKILLS ROUTER BRIDGE"
TOML_END_MARKER = "# END SKILLS ROUTER BRIDGE"


def build_agent_connection(
    config: SkillsRouterConfig,
    *,
    target: str = "codex",
    agent_id: str = "local-agent",
    detail: str = "compact",
    from_source: bool = False,
) -> dict[str, Any]:
    """Return MCP config, bridge prompt, and instruction paths for one target."""
    profile = get_agent_profile(target)
    bridge_prompt = render_agent_prompt(
        profile.target,
        agent_id=agent_id,
        detail=detail,
    )
    mcp_server = _mcp_server_spec(from_source=from_source)
    instruction_files = [
        _instruction_entry(raw, config, recommended=idx == 0)
        for idx, raw in enumerate(profile.instruction_files)
    ]
    skill_dirs = [
        _skill_dir_entry(raw, config, recommended=idx == 0)
        for idx, raw in enumerate(profile.workspace_skill_dirs)
    ]
    fallback_command = _fallback_command(
        profile.target,
        agent_id=agent_id,
        from_source=from_source,
    )
    slash_command_files = [
        _slash_command_entry(raw, config, recommended=idx == 0)
        for idx, raw in enumerate(profile.slash_command_files)
    ]
    return {
        "status": "OK",
        "target": profile.target,
        "display_name": profile.display_name,
        "agent_id": agent_id,
        "preferred_bridge": profile.preferred_bridge,
        "mode": "from_source" if from_source else "installed_cli",
        "mcp_config": {"mcpServers": {"skills-router": mcp_server}},
        "mcp_server": mcp_server,
        "bridge_prompt": bridge_prompt,
        "instruction_files": instruction_files,
        "skill_dirs": skill_dirs,
        "slash_command_files": slash_command_files,
        "fallback_command": fallback_command,
        "human_summary": (
            f"Connection kit ready for {profile.display_name}. Add the MCP "
            "server config and the bridge prompt to the target instruction file."
        ),
    }


def build_detected_agent_connections(
    config: SkillsRouterConfig,
    *,
    agent_id: str = "local-agent",
    detail: str = "compact",
    from_source: bool = False,
) -> dict[str, Any]:
    """Return detected global AI-agent skill folders for connect."""
    return _build_global_agent_connection(
        agent_id=agent_id,
        detail=detail,
        from_source=from_source,
    )


def write_detected_bridge_skills(
    connection: dict[str, Any],
    *,
    dry_run: bool = False,
    config: SkillsRouterConfig | None = None,
) -> dict[str, Any]:
    """Write one managed global Skills Router skill per detected skill folder."""
    writes: list[dict[str, Any]] = []
    groups: dict[str, dict[str, Any]] = {}
    for target in connection.get("detected_targets") or []:
        for item in target.get("skill_dirs") or []:
            skill_path = str(item["skill_path"])
            group = groups.setdefault(
                skill_path,
                {
                    "target": "shared",
                    "display_name": "Shared AI-agent bridge",
                    "bridge_targets": [],
                    "skill_path": skill_path,
                },
            )
            group["bridge_targets"].append(target)

    for skill_path, group in groups.items():
        writes.append(
            _write_bridge_skill_path(
                Path(skill_path),
                group,
                dry_run=dry_run,
                config=config,
            )
        )

    return {
        "status": "DRY_RUN" if dry_run else "OK",
        "dry_run": dry_run,
        "written_count": len(writes),
        "writes": writes,
    }


def apply_agent_connection(
    config: SkillsRouterConfig,
    connection: dict[str, Any],
    *,
    dry_run: bool = False,
    instruction_file: str | None = None,
    skill_dir: str | None = None,
) -> dict[str, Any]:
    """Apply the recommended bridge artifact for the target."""
    preferred = str(connection.get("preferred_bridge") or "instructions")
    result: dict[str, Any] = {"status": "OK", "preferred_bridge": preferred}
    if preferred == "skill":
        result["written_skill"] = write_bridge_skill(
            config,
            connection,
            skill_dir=skill_dir,
            dry_run=dry_run,
        )
    else:
        result["written_instruction"] = write_bridge_instructions(
            config,
            connection,
            instruction_file=instruction_file,
            dry_run=dry_run,
        )
    slash_writes = [
        write_slash_command(config, connection, raw=item["configured"], dry_run=dry_run)
        for item in (connection.get("slash_command_files") or [])
    ]
    if slash_writes:
        result["written_slash_commands"] = slash_writes
    return result


def check_agent_connection(
    config: SkillsRouterConfig,
    connection: dict[str, Any],
) -> dict[str, Any]:
    """Verify local MCP tool readiness and bridge file presence for a target."""
    from skills_router.mcp_server import handle_request

    initialize = handle_request(
        {"jsonrpc": "2.0", "id": 1, "method": "initialize"},
        config,
    )
    tools = handle_request(
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        config,
    )

    server_info = initialize["result"]["serverInfo"]
    tool_names = sorted(
        tool["name"] for tool in tools["result"]["tools"] if tool.get("name")
    )
    required_tools = [
        "get_agent_prompt",
        "parse_slash_command",
        "refine_routes",
        "route_task",
        "run_slash_command",
    ]
    missing_tools = [name for name in required_tools if name not in tool_names]

    instruction_files = connection.get("instruction_files") or []
    skill_dirs = connection.get("skill_dirs") or []
    slash_command_files = connection.get("slash_command_files") or []
    managed_instruction_count = sum(
        1 for item in instruction_files if item.get("managed_bridge_present")
    )
    managed_skill_count = sum(1 for item in skill_dirs if item.get("skill_exists"))
    managed_slash_count = sum(
        1 for item in slash_command_files if item.get("managed_present")
    )
    writable_bridge_targets = [
        item["path"]
        for item in instruction_files
        if item.get("recommended")
    ] + [
        item["skill_path"]
        for item in skill_dirs
        if item.get("recommended")
    ] + [
        item["path"]
        for item in slash_command_files
        if item.get("recommended")
    ]

    warnings: list[str] = []
    if missing_tools:
        warnings.append(
            "Missing required MCP tools: " + ", ".join(missing_tools)
        )
    if managed_instruction_count == 0 and managed_skill_count == 0:
        warnings.append(
            "No managed bridge instructions or Skills Router SKILL.md were found "
            "for the target workspace yet."
        )

    ready = not missing_tools and (managed_instruction_count > 0 or managed_skill_count > 0)
    return {
        "status": "OK" if ready else "WARN",
        "ready": ready,
        "target": connection.get("target"),
        "server": {
            "name": server_info.get("name"),
            "version": server_info.get("version"),
            "protocol_version": initialize["result"].get("protocolVersion"),
        },
        "mcp_tools": {
            "required": required_tools,
            "available": tool_names,
            "missing": missing_tools,
        },
        "bridge_files": {
            "managed_instruction_count": managed_instruction_count,
            "managed_skill_count": managed_skill_count,
            "managed_slash_count": managed_slash_count,
            "instruction_files": instruction_files,
            "skill_dirs": skill_dirs,
            "slash_command_files": slash_command_files,
        },
        "writable_bridge_targets": writable_bridge_targets,
        "recommendation": (
            "Connection is ready for an AI agent."
            if ready
            else "Add the bridge prompt or managed SKILL.md, then connect the host to the MCP server."
        ),
        "warnings": warnings,
    }


def write_bridge_instructions(
    config: SkillsRouterConfig,
    connection: dict[str, Any],
    *,
    instruction_file: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Write or update a managed bridge prompt block in an instruction file."""
    target = instruction_file or _default_instruction_file(connection)
    path = _resolve_workspace_path(target, config, label="Instruction files")
    block = _managed_block(str(connection["bridge_prompt"]))
    action = "created"
    if path.exists():
        current = path.read_text(encoding="utf-8")
        updated = _replace_or_append_block(current, block)
        action = "updated" if BEGIN_MARKER in current and END_MARKER in current else "appended"
    else:
        updated = block + "\n"
    if dry_run:
        preview_action = {
            "created": "would_create",
            "updated": "would_update",
            "appended": "would_append",
        }.get(action, f"would_{action}")
        return {
            "status": "DRY_RUN",
            "dry_run": True,
            "action": preview_action,
            "path": str(path),
        }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(updated, encoding="utf-8")
    return {
        "status": "OK",
        "dry_run": False,
        "action": action,
        "path": str(path),
    }


def write_bridge_skill(
    config: SkillsRouterConfig,
    connection: dict[str, Any],
    *,
    skill_dir: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Write or update a managed Skills Router SKILL.md for one agent target."""
    target = skill_dir or _default_skill_dir(connection)
    root = _resolve_workspace_path(target, config, label="Skill directories")
    path = root / "skills-router" / "SKILL.md"
    return _write_bridge_skill_path(path, connection, dry_run=dry_run)


def write_slash_command(
    config: SkillsRouterConfig,
    connection: dict[str, Any],
    *,
    raw: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Write or update a managed Skills Router slash command TOML for one agent target."""
    slash_files = connection.get("slash_command_files") or []
    target_raw = raw or (slash_files[0]["configured"] if slash_files else None)
    if not target_raw:
        raise ValueError("No slash command file is configured for this agent target")
    path = _resolve_workspace_path(target_raw, config, label="Slash command files")
    content = _slash_command_document(connection)
    action = "created"
    if path.exists():
        current = path.read_text(encoding="utf-8")
        if TOML_BEGIN_MARKER not in current or TOML_END_MARKER not in current:
            raise ValueError(
                "Refusing to overwrite unmanaged slash command file. "
                f"Got: {path}"
            )
        action = "updated"
    if dry_run:
        return {
            "status": "DRY_RUN",
            "dry_run": True,
            "action": "would_create" if action == "created" else "would_update",
            "path": str(path),
            "target": connection.get("target"),
        }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return {
        "status": "OK",
        "dry_run": False,
        "action": action,
        "path": str(path),
        "target": connection.get("target"),
    }


def _slash_command_entry(
    raw: str,
    config: SkillsRouterConfig,
    *,
    recommended: bool,
) -> dict[str, Any]:
    path = _resolve_workspace_path(raw, config, label="Slash command files")
    managed_present = False
    if path.exists():
        text = path.read_text(encoding="utf-8")
        managed_present = TOML_BEGIN_MARKER in text and TOML_END_MARKER in text
    return {
        "configured": raw,
        "path": str(path),
        "exists": path.exists(),
        "managed_present": managed_present,
        "recommended": recommended,
    }


def _slash_command_document(connection: dict[str, Any]) -> str:
    """Render a managed .gemini/commands/skills-router.toml for one agent target."""
    target = connection.get("target", "antigravity-ide")
    agent_id = connection.get("agent_id", "<agent-id>")
    return (
        f"{TOML_BEGIN_MARKER}\n"
        f"# Generated by Skills Router connect. Edit with care.\n"
        f'description = "Route /skills-router requests through Skills Router MCP or CLI."\n'
        f'prompt = """\n'
        f"Handle this as a Skills Router registry request.\n"
        f"User text: /skills-router {{{{args}}}}\n\n"
        f"Preferred execution order:\n"
        f"1. If MCP tools are available, call `run_slash_command` with the full user text.\n"
        f"   Use `refine_routes` for structured skillset names; `route_task` for task routing.\n"
        f'2. Fallback: `skills-router chat "/skills-router {{{{args}}}}" '
        f"--target {target} --agent-id {agent_id} --json`.\n\n"
        f"Reply: prefer `human_summary`; do not paste raw JSON unless asked.\n"
        f'Safety: never use --yes or auto_approve unless the user explicitly accepts risk.\n"""\n'
        f"{TOML_END_MARKER}\n"
    )


def _build_global_agent_connection(
    *,
    agent_id: str,
    detail: str,
    from_source: bool,
) -> dict[str, Any]:
    mcp_server = _mcp_server_spec(from_source=from_source)
    detected_targets: list[dict[str, Any]] = []
    missing_targets: list[dict[str, Any]] = []

    for profile in list_agent_profiles():
        entries = [
            _global_skill_dir_entry(raw, recommended=idx == 0)
            for idx, raw in enumerate(profile.global_skill_dirs)
        ]
        detected = [entry for entry in entries if entry["detected"]]
        target_report = {
            "target": profile.target,
            "display_name": profile.display_name,
            "global_skill_dirs": entries,
        }
        if detected:
            target_report["bridge_prompt"] = render_agent_prompt(
                profile.target,
                agent_id=agent_id,
                detail=detail,
            )
            target_report["fallback_command"] = _fallback_command(
                profile.target,
                agent_id=agent_id,
                from_source=from_source,
            )
            target_report["skill_dirs"] = [detected[0]]
            detected_targets.append(target_report)
        else:
            missing_targets.append(target_report)

    if not detected_targets:
        candidates = sorted(
            {
                entry["path"]
                for target in missing_targets
                for entry in target["global_skill_dirs"]
                if entry.get("path")
            }
        )
        preview = ", ".join(candidates[:8])
        suffix = f" Checked candidate folders: {preview}." if preview else ""
        raise ValueError(
            "No supported AI-agent global skill folders were detected."
            f"{suffix}"
        )

    return {
        "status": "OK",
        "target": "all",
        "display_name": "Detected AI-agent hosts",
        "agent_id": agent_id,
        "preferred_bridge": "global-skill",
        "mode": "from_source" if from_source else "installed_cli",
        "mcp_config": {"mcpServers": {"skills-router": mcp_server}},
        "mcp_server": mcp_server,
        "detected_target_count": len(detected_targets),
        "missing_target_count": len(missing_targets),
        "detected_targets": detected_targets,
        "missing_targets": missing_targets,
        "human_summary": (
            "Detected "
            f"{len(detected_targets)} supported AI-agent target(s). "
            "Connect writes managed Skills Router skills to their global folders."
        ),
    }


def _write_bridge_skill_path(
    path: Path,
    connection: dict[str, Any],
    *,
    dry_run: bool,
    config: SkillsRouterConfig | None = None,
) -> dict[str, Any]:
    content = _skill_document(connection)
    if config is not None:
        try:
            from skills_router.agent_bridge.inventory import (
                build_skill_inventory,
                render_inventory_markdown,
            )
            inventory = build_skill_inventory(config)
            content += "\n\n" + render_inventory_markdown(inventory)
        except Exception:
            pass
    action = "created"
    if path.exists():
        current = path.read_text(encoding="utf-8")
        if SKILL_BEGIN_MARKER not in current or SKILL_END_MARKER not in current:
            raise ValueError(
                "Refusing to overwrite unmanaged Skills Router skill file. "
                f"Got: {path}"
            )
        action = "updated"
    if dry_run:
        preview_action = {
            "created": "would_create",
            "updated": "would_update",
        }.get(action, f"would_{action}")
        return {
            "status": "DRY_RUN",
            "dry_run": True,
            "action": preview_action,
            "path": str(path),
            "target": connection.get("target"),
        }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return {
        "status": "OK",
        "dry_run": False,
        "action": action,
        "path": str(path),
        "target": connection.get("target"),
    }



def _mcp_server_spec(*, from_source: bool) -> dict[str, Any]:
    if not from_source:
        return {"command": "skills-router", "args": ["mcp"]}
    src_root = Path(__file__).resolve().parents[2]
    return {
        "command": sys.executable,
        "args": ["-m", "skills_router.cli", "mcp"],
        "env": {"PYTHONPATH": str(src_root)},
    }


def _fallback_command(target: str, *, agent_id: str, from_source: bool) -> str:
    base = (
        f"{sys.executable} -m skills_router.cli"
        if from_source
        else "skills-router"
    )
    return (
        f'{base} chat "/skills-router <request>" --target {target} '
        f"--agent-id {agent_id} --json"
    )


def _instruction_entry(
    raw: str,
    config: SkillsRouterConfig,
    *,
    recommended: bool,
) -> dict[str, Any]:
    path = _resolve_workspace_path(raw, config, label="Instruction files")
    managed_bridge_present = False
    if path.exists():
        text = path.read_text(encoding="utf-8")
        managed_bridge_present = BEGIN_MARKER in text and END_MARKER in text
    return {
        "configured": raw,
        "path": str(path),
        "exists": path.exists(),
        "managed_bridge_present": managed_bridge_present,
        "recommended": recommended,
    }


def _skill_dir_entry(
    raw: str,
    config: SkillsRouterConfig,
    *,
    recommended: bool,
) -> dict[str, Any]:
    path = _resolve_workspace_path(raw, config, label="Skill directories")
    skill_path = path / "skills-router" / "SKILL.md"
    managed_skill_present = False
    if skill_path.exists():
        text = skill_path.read_text(encoding="utf-8")
        managed_skill_present = (
            SKILL_BEGIN_MARKER in text and SKILL_END_MARKER in text
        )
    return {
        "configured": raw,
        "path": str(path),
        "skill_path": str(skill_path),
        "exists": path.exists(),
        "skill_exists": skill_path.exists(),
        "managed_skill_present": managed_skill_present,
        "recommended": recommended,
    }


def _global_skill_dir_entry(
    raw: str,
    *,
    recommended: bool,
) -> dict[str, Any]:
    path = _resolve_global_path(raw)
    agent_home = path.parent
    skill_path = path / "skills-router" / "SKILL.md"
    detected = path.exists() or agent_home.exists()
    detection_reason = (
        "global_skill_dir_exists"
        if path.exists()
        else "agent_home_exists"
        if agent_home.exists()
        else "missing"
    )
    managed_skill_present = False
    if skill_path.exists():
        text = skill_path.read_text(encoding="utf-8")
        managed_skill_present = (
            SKILL_BEGIN_MARKER in text and SKILL_END_MARKER in text
        )
    return {
        "configured": raw,
        "path": str(path),
        "skill_path": str(skill_path),
        "scope": "global",
        "agent_home": str(agent_home),
        "detected": detected,
        "detection_reason": detection_reason,
        "exists": path.exists(),
        "skill_exists": skill_path.exists(),
        "managed_skill_present": managed_skill_present,
        "recommended": recommended,
    }


def _default_instruction_file(connection: dict[str, Any]) -> str:
    files = connection.get("instruction_files") or []
    if not files:
        raise ValueError("No instruction file is configured for this agent target")
    return str(files[0]["configured"])


def _default_skill_dir(connection: dict[str, Any]) -> str:
    dirs = connection.get("skill_dirs") or []
    if not dirs:
        raise ValueError("No workspace skill directory is configured for this agent target")
    return str(dirs[0]["configured"])


def _resolve_workspace_path(raw: str, config: SkillsRouterConfig, *, label: str) -> Path:
    workspace_root = Path(config.workspace_root).resolve(strict=False)
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = workspace_root / path
    path = path.resolve(strict=False)
    try:
        path.relative_to(workspace_root)
    except ValueError as exc:
        raise ValueError(
            f"{label} must be inside the workspace root. "
            f"Got: {path}"
        ) from exc
    return path


def _resolve_global_path(raw: str) -> Path:
    # os.path.expandvars only handles %VAR% on Windows, not $VAR.
    # Manually expand $VAR / ${VAR} so profiles stay cross-platform.
    import re

    def _expand_dollar(m: re.Match) -> str:  # type: ignore[type-arg]
        return os.environ.get(m.group(1) or m.group(2), m.group(0))

    dollar_expanded = re.sub(
        r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}|\$([A-Za-z_][A-Za-z0-9_]*)",
        _expand_dollar,
        str(raw),
    )
    expanded = os.path.expandvars(dollar_expanded)  # also handle %VAR% style
    return Path(expanded).expanduser().resolve(strict=False)


def _managed_block(prompt: str) -> str:
    return f"{BEGIN_MARKER}\n{prompt.strip()}\n{END_MARKER}"


def _skill_document(connection: dict[str, Any]) -> str:
    prompt = _bridge_skill_prompt(connection)
    return (
        "---\n"
        "name: skills-router\n"
        "description: Use when the user asks Skills Router to manage AI-agent "
        "skills, plugins, routes, or messages starting /skills-router or "
        "skills-router.\n"
        "---\n\n"
        f"{SKILL_BEGIN_MARKER}\n"
        f"{prompt}\n"
        f"{SKILL_END_MARKER}\n"
    )


def _bridge_skill_prompt(connection: dict[str, Any]) -> str:
    targets = connection.get("bridge_targets") or []
    if not targets:
        return str(connection["bridge_prompt"]).strip()

    sections = [
        "# Skills Router Shared Bridge",
        "",
        "This managed global skill is shared by multiple detected AI-agent hosts. "
        "When handling a Skills Router request, use the section matching the "
        "current host target.",
    ]
    for target in targets:
        sections.extend(
            [
                "",
                f"## {target['display_name']} (`{target['target']}`)",
                "",
                str(target["bridge_prompt"]).strip(),
            ]
        )
    return "\n".join(sections).strip()


def _replace_or_append_block(text: str, block: str) -> str:
    start = text.find(BEGIN_MARKER)
    end = text.find(END_MARKER)
    if start != -1 and end != -1 and end > start:
        end += len(END_MARKER)
        return text[:start] + block + text[end:]
    stripped = text.rstrip()
    if stripped:
        return stripped + "\n\n" + block + "\n"
    return block + "\n"
