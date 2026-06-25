"""Minimal stdio JSON-RPC tool surface for local AI agents.

This intentionally avoids external MCP dependencies while exposing the common
``initialize``, ``tools/list``, and ``tools/call`` methods used by local agent
hosts.
"""

from __future__ import annotations

import json
import logging
import sys
from typing import Any, TextIO

logger = logging.getLogger(__name__)

from skills_router import __version__
from skills_router.config import SkillsRouterConfig
from skills_router.daemon.live_signal_fetcher import LiveSignalFetcher
from skills_router.daemon.registry_watch import RegistryWatchDaemon
from skills_router.layers.lockfile import SkillsRouterLockfile
from skills_router.layers.registry_resolver import RegistryResolutionError, RegistryResolver
from skills_router.layers.semantic_evaluator import SemanticEvaluator
from skills_router.layers.source_analyzer import (
    SourceAnalysisError,
    SourceAnalyzer,
    is_supported_source_ref,
)
from skills_router.layers.trust_gate import TrustGate
from skills_router.orchestrator import SkillsRouterOrchestrator
from skills_router.storage.memory_store import MemoryBrainIndexStore
from skills_router.wg.notifier import WGNotifier


def run_mcp_server(
    config: SkillsRouterConfig,
    input_stream: TextIO | None = None,
    output_stream: TextIO | None = None,
) -> None:
    """Run a JSON-lines stdio server."""
    input_stream = input_stream or sys.stdin
    output_stream = output_stream or sys.stdout
    for line in input_stream:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
            response = handle_request(request, config)
        except Exception as exc:
            response = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32603, "message": str(exc)},
            }
        output_stream.write(json.dumps(response) + "\n")
        output_stream.flush()


def handle_request(request: dict[str, Any], config: SkillsRouterConfig) -> dict[str, Any]:
    """Handle one JSON-RPC request."""
    request_id = request.get("id")
    method = request.get("method")
    params = request.get("params") or {}

    try:
        if method == "initialize":
            result = {
                "protocolVersion": "2024-11-05",
                "serverInfo": {"name": "skills-router", "version": __version__},
                "capabilities": {"tools": {}},
            }
        elif method == "tools/list":
            result = {"tools": _get_all_tools_specs(config)}
        elif method == "tools/call":
            result = _call_tool(params, config)
        else:
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": -32601, "message": f"Unknown method: {method}"},
            }
        return {"jsonrpc": "2.0", "id": request_id, "result": result}
    except RegistryResolutionError as exc:
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": -32000, "message": str(exc)},
        }


def _call_tool(params: dict[str, Any], config: SkillsRouterConfig) -> dict[str, Any]:
    name = params.get("name")
    arguments = params.get("arguments") or {}

    builtin_tools = {
        "get_agent_prompt",
        "get_router_status",
        "parse_slash_command",
        "run_slash_command",
        "analyze_package_source",
        "install_tool",
        "index_routes",
        "refine_routes",
        "route_task",
        "uninstall_tool",
        "list_tools",
        "inspect_tool",
        "use_skill",
        "watch_once",
        "run_agent_hook",
    }

    if name not in builtin_tools:
        active_mcp = _get_active_mcp_specs(config)
        target_spec = None
        for server_name, spec in active_mcp.items():
            declared_tools = spec.get("tools")
            if isinstance(declared_tools, list):
                if any(t.get("name") == name for t in declared_tools):
                    target_spec = spec
                    break
            else:
                command = spec.get("command")
                args = spec.get("args") or []
                env = spec.get("env")
                if command:
                    try:
                        from skills_router.layers.mcp_client import MCPClient
                        client = MCPClient(command, args, env)
                        discovered = client.discover_tools()
                        if any(t.get("name") == name for t in discovered):
                            target_spec = spec
                            break
                    except Exception:
                        pass
        if target_spec:
            command = target_spec["command"]
            args = target_spec.get("args") or []
            env = target_spec.get("env")
            from skills_router.layers.mcp_client import MCPClient
            client = MCPClient(command, args, env)
            return client.call_tool(name, arguments)
        else:
            raise ValueError(f"Unknown tool: {name}")

    if name == "run_agent_hook":
        from skills_router.layers.hook_runner import run_hooks_for_event
        from skills_router.storage.memory_store import MemoryBrainIndexStore
        from skills_router.agent_bridge.routing import read_routing_state
        
        event_name = arguments["event_name"]
        context = arguments.get("context")
        
        active_hooks = {}
        try:
            store = MemoryBrainIndexStore(
                brain_index_path=config.brain_index_path,
                dep_graph_path=config.dep_graph_path,
            )
            routing = read_routing_state(config)
            packages = routing.get("packages", {})
            for tool_id, pkg in packages.items():
                if pkg.get("status") == "active":
                    entry = store.get_tool(tool_id)
                    if entry:
                        caps = entry.get("layer_3_capabilities", {})
                        hooks = caps.get("hooks", {})
                        for h_event, h_specs in hooks.items():
                            active_hooks.setdefault(h_event, []).extend(h_specs)
        except Exception:
            pass
            
        result = run_hooks_for_event(event_name, active_hooks, context)
        return _tool_result(result)

    if name == "get_agent_prompt":
        from skills_router.agent_bridge.prompts import render_agent_prompt

        result = {
            "status": "OK",
            "target": arguments.get("target", "codex"),
            "agent_id": arguments.get("agent_id", "<agent-id>"),
            "prompt": render_agent_prompt(
                arguments.get("target", "codex"),
                agent_id=arguments.get("agent_id", "<agent-id>"),
                detail=arguments.get("detail", "compact"),
            ),
        }
        return _tool_result(result)

    if name == "get_router_status":
        from skills_router.status import build_router_status

        store = _build_store(config)
        return _tool_result(build_router_status(config, store))

    if name == "parse_slash_command":
        from skills_router.agent_bridge.parser import parse_slash_command

        intent = parse_slash_command(
            arguments["text"],
            target=arguments.get("target"),
            agent_id=arguments.get("agent_id", "mcp-agent"),
            default_scope=arguments.get("scope"),
        )
        return _tool_result({"status": "OK", "intent": intent.to_dict()})

    if name == "run_slash_command":
        from skills_router.agent_bridge.executor import execute_slash_command

        result = execute_slash_command(
            arguments["text"],
            config,
            target=arguments.get("target"),
            agent_id=arguments.get("agent_id", "mcp-agent"),
            default_scope=arguments.get("scope"),
        )
        return _tool_result(result)

    if name == "analyze_package_source":
        result = SourceAnalyzer(config).analyze(arguments["source_ref"])
        return _tool_result(result)

    if name == "install_tool":
        from skills_router.agent_bridge.routing import (
            build_routing_plan,
            persist_routing_plan,
        )

        store = _build_store(config)
        manifest_ref = arguments["package_or_manifest"]
        manifest, source_analysis = _resolve_manifest(
            config,
            manifest_ref,
            infer=bool(arguments.get("infer", False)),
        )
        auto_approve = bool(arguments.get("auto_approve", False))
        decision = (lambda _prompt, _options: 0) if auto_approve else _cancel
        all_agents = bool(arguments.get("all_agents", False))
        target_report = None
        if all_agents:
            from skills_router.agent_bridge.targeting import build_agent_target_report

            target_report = build_agent_target_report(
                config,
                targets=arguments.get("target_agents") or [],
            )
            manifest.setdefault("layer_meta", {})["target_agents"] = (
                target_report["target_names"]
            )
        scope = "global" if all_agents else arguments.get("scope", "global")
        orchestrator = SkillsRouterOrchestrator(config, store, decision_callback=decision)
        result = orchestrator.install(
            manifest,
            scope=scope,
            user_id=arguments.get("user_id", "mcp-agent"),
            dry_run=bool(arguments.get("dry_run", False)),
        )
        result["dry_run"] = bool(arguments.get("dry_run", False))
        if result.get("status") in ("INSTALLED", "DRY_RUN_APPROVED"):
            routing_plan = build_routing_plan(
                manifest,
                scope=scope,
                package_type=arguments.get("package_type", "auto"),
                routing_mode=arguments.get("routing_mode", "full_package"),
                target_agents=(
                    target_report["target_names"] if target_report is not None else None
                ),
            )
            result["skills_routing"] = routing_plan
        if source_analysis is not None:
            result["source_analysis"] = source_analysis
        if target_report is not None:
            result["agent_targets"] = target_report
        if result.get("status") == "INSTALLED":
            installed = store.get_tool(result["tool_id"]) or manifest
            SkillsRouterLockfile(config.registry_lockfile_path).upsert(
                installed,
                requested=manifest_ref,
                scope=scope,
            )
            persist_routing_plan(config, result["skills_routing"])
        return _tool_result(result)

    if name == "index_routes":
        from skills_router.agent_bridge.indexer import index_installed_skillsets

        store = _build_store(config)
        result = index_installed_skillsets(
            config,
            store,
            scope=arguments.get("scope"),
            persist=not bool(arguments.get("dry_run", False)),
        )
        return _tool_result(result)

    if name == "refine_routes":
        from skills_router.agent_bridge.indexer import refine_installed_skillsets

        store = _build_store(config)
        result = refine_installed_skillsets(
            config,
            store,
            skillset_names=arguments.get("skillsets") or [],
            scope=arguments.get("scope"),
            workspace_scope=arguments.get("workspace_scope"),
            persist=not bool(arguments.get("dry_run", False)),
            discover=not bool(arguments.get("no_discovery", False)),
        )
        return _tool_result(result)

    if name == "route_task":
        from skills_router.agent_bridge.routing import route_task

        result = route_task(
            config,
            arguments["task"],
            scope=arguments.get("scope"),
            agent_target=arguments.get("target"),
            limit=int(arguments.get("limit") or 5),
            include_inactive=bool(arguments.get("include_inactive", False)),
        )
        return _tool_result(result)

    if name == "uninstall_tool":
        from skills_router.agent_bridge.uninstaller import uninstall_skill_metadata

        store = _build_store(config)
        result = uninstall_skill_metadata(
            config,
            store,
            arguments["tool_id"],
            user_id=arguments.get("user_id", "mcp-agent"),
            scope=arguments.get("scope"),
            dry_run=bool(arguments.get("dry_run", False)),
        )
        return _tool_result(result)

    if name == "list_tools":
        store = _build_store(config)
        orchestrator = SkillsRouterOrchestrator(config, store)
        result = {
            "status": "OK",
            "tools": orchestrator.list_tools(scope=arguments.get("scope")),
        }
        return _tool_result(result)

    if name == "inspect_tool":
        store = _build_store(config)
        orchestrator = SkillsRouterOrchestrator(config, store)
        tool = orchestrator.inspect_tool(arguments["tool_id"])
        result = {"status": "OK", "tool": tool} if tool else {
            "status": "NOT_FOUND",
            "tool_id": arguments["tool_id"],
        }
        return _tool_result(result)

    if name == "use_skill":
        from skills_router.agent_bridge.inventory import use_skill

        store = _build_store(config)
        result = use_skill(config, arguments["tool_id"], store=store)
        return _tool_result(result)

    if name == "watch_once":
        store = _build_store(config)
        daemon = RegistryWatchDaemon(
            evaluator=SemanticEvaluator(
                model_name=config.embedding_model,
                similarity_threshold=config.similarity_threshold,
            ),
            trust_gate=TrustGate(
                hard_block_threshold=config.trust_hard_block_threshold,
                soft_warn_threshold=config.trust_soft_warn_threshold,
            ),
            brain_index_db=store,
            wg_notifier=WGNotifier(admin_channel_id=config.admin_channel_id, quiet=True),
            live_signal_fetcher=LiveSignalFetcher(
                max_retries=config.max_retries,
                backoff_base=config.backoff_base,
                failure_threshold=config.circuit_failure_threshold,
                reset_seconds=config.circuit_reset_seconds,
            ),
            admin_channel_id=config.admin_channel_id,
            state_path=config.registry_watch_state_path,
            dry_run=bool(arguments.get("dry_run", False)),
        )
        return _tool_result(
            daemon.run_once(
                seed_hashes=True,
                dry_run=bool(arguments.get("dry_run", False)),
            )
        )

    raise ValueError(f"Unknown tool: {name}")


def _build_store(config: SkillsRouterConfig) -> MemoryBrainIndexStore:
    return MemoryBrainIndexStore(
        brain_index_path=config.brain_index_path,
        dep_graph_path=config.dep_graph_path,
    )


def _get_active_mcp_specs(config: SkillsRouterConfig) -> dict[str, dict[str, Any]]:
    from skills_router.storage.memory_store import MemoryBrainIndexStore
    from skills_router.agent_bridge.routing import read_routing_state

    mcp_specs = {}
    try:
        store = MemoryBrainIndexStore(
            brain_index_path=config.brain_index_path,
            dep_graph_path=config.dep_graph_path,
        )
        routing = read_routing_state(config)
        packages = routing.get("packages", {})
        for tool_id, pkg in packages.items():
            if pkg.get("status") == "active":
                entry = store.get_tool(tool_id)
                if entry:
                    caps = entry.get("layer_3_capabilities", {})
                    mcp_servers = caps.get("mcp_servers", {})
                    for server_name, server_spec in mcp_servers.items():
                        mcp_specs[server_name] = server_spec
    except Exception:
        pass
    return mcp_specs


def _get_all_tools_specs(config: SkillsRouterConfig) -> list[dict[str, Any]]:
    specs = list(_tool_specs())

    specs.append({
        "name": "run_agent_hook",
        "description": "Execute lifecycle hooks (e.g. SessionStart) from active installed skills.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "event_name": {"type": "string", "description": "Name of hook event (e.g. SessionStart)"},
                "context": {"type": "object", "description": "Context variables to pass to the hook environment"}
            },
            "required": ["event_name"]
        }
    })

    active_mcp = _get_active_mcp_specs(config)
    for server_name, spec in active_mcp.items():
        declared_tools = spec.get("tools")
        if isinstance(declared_tools, list):
            specs.extend(declared_tools)
        else:
            command = spec.get("command")
            args = spec.get("args") or []
            env = spec.get("env")
            if command:
                try:
                    from skills_router.layers.mcp_client import MCPClient
                    client = MCPClient(command, args, env)
                    discovered = client.discover_tools()
                    specs.extend(discovered)
                except Exception as e:
                    logger.error(
                        f"Error discovering tools from MCP server '{server_name}': {e}"
                    )
    return specs


def _resolve_manifest(
    config: SkillsRouterConfig,
    manifest_ref: str,
    *,
    infer: bool = False,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    if infer:
        analysis = SourceAnalyzer(config).analyze(manifest_ref)
        return analysis["manifest"], analysis
    try:
        return RegistryResolver(config).resolve(manifest_ref), None
    except Exception as exc:
        if not is_supported_source_ref(manifest_ref):
            raise
        try:
            analysis = SourceAnalyzer(config).analyze(manifest_ref)
        except SourceAnalysisError as source_exc:
            raise ValueError(
                f"{exc}; source inference also failed: {source_exc}"
            ) from source_exc
        return analysis["manifest"], analysis


def _cancel(_prompt: str, options: list[str]) -> int:
    return max(0, len(options) - 1)


def _tool_result(result: dict[str, Any]) -> dict[str, Any]:
    text = _compact_tool_text(result)
    return {"content": [{"type": "text", "text": text}], "structuredContent": result}


def _compact_tool_text(result: dict[str, Any]) -> str:
    """Return the low-token text part while keeping full structuredContent."""
    if result.get("prompt"):
        return str(result["prompt"])
    if result.get("human_summary"):
        return str(result["human_summary"])
    if result.get("manifest") and result.get("source"):
        manifest = result["manifest"]
        source = result["source"]
        return (
            f"Analyzed {source.get('identifier', 'source')}; "
            f"inferred {manifest.get('tool_id', 'tool')}."
        )
    if result.get("intent"):
        intent = result["intent"]
        return f"Parsed /skills-router {intent.get('command', 'request')} request."
    try:
        from skills_router.agent_bridge.executor import summarize_result

        summary = summarize_result(result)
        if summary:
            return summary
    except Exception:
        pass
    status = result.get("status", "OK")
    if result.get("error"):
        return f"{status}: {result['error']}"
    return str(status)


def _tool_specs() -> list[dict[str, Any]]:
    return [
        {
            "name": "get_agent_prompt",
            "description": (
                "Render compact Skills Router bridge instructions for an "
                "AI-agent target."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "target": {"type": "string"},
                    "agent_id": {"type": "string"},
                    "detail": {
                        "type": "string",
                        "enum": ["compact", "full"],
                        "description": "compact is the default and minimizes prompt tokens.",
                    },
                },
            },
        },
        {
            "name": "get_router_status",
            "description": (
                "Show Skills Router metadata paths, configured host skill "
                "paths, route counts, and overall router status."
            ),
            "inputSchema": {"type": "object", "properties": {}},
        },
        {
            "name": "parse_slash_command",
            "description": "Parse a chat-shaped /skills-router request into structured intent.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "target": {"type": "string"},
                    "agent_id": {"type": "string"},
                    "scope": {"type": "string"},
                },
                "required": ["text"],
            },
        },
        {
            "name": "run_slash_command",
            "description": "Parse and execute a chat-shaped /skills-router request.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "target": {"type": "string"},
                    "agent_id": {"type": "string"},
                    "scope": {"type": "string"},
                },
                "required": ["text"],
            },
        },
        {
            "name": "analyze_package_source",
            "description": (
                "Analyze an npm/GitHub package source link and return a "
                "reviewable inferred Skills Router manifest without installing it."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "source_ref": {
                        "type": "string",
                        "description": (
                            "GitHub URL, npm package URL, github:owner/repo, "
                            "or npm:<package>."
                        ),
                    },
                },
                "required": ["source_ref"],
            },
        },
        {
            "name": "install_tool",
            "description": "Install or dry-run an skills-router tool manifest/package.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "package_or_manifest": {"type": "string"},
                    "scope": {"type": "string"},
                    "user_id": {"type": "string"},
                    "dry_run": {"type": "boolean"},
                    "auto_approve": {"type": "boolean"},
                    "infer": {
                        "type": "boolean",
                        "description": (
                            "Infer a manifest from a supported npm/GitHub source "
                            "link when no skills-router.json is available."
                        ),
                    },
                    "package_type": {
                        "type": "string",
                        "enum": ["auto", "skillset", "plugin", "tool"],
                    },
                    "routing_mode": {
                        "type": "string",
                        "enum": ["full_package", "selective_routes"],
                    },
                    "all_agents": {
                        "type": "boolean",
                        "description": (
                            "Install once with global routes visible to the "
                            "configured all-agent target set."
                        ),
                    },
                    "target_agents": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
                "required": ["package_or_manifest"],
            },
        },
        {
            "name": "index_routes",
            "description": (
                "Re-index installed AI-agent skills/plugins, detect routing "
                "conflicts, and return recommendations for human choice."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "scope": {"type": "string"},
                    "dry_run": {"type": "boolean"},
                },
            },
        },
        {
            "name": "refine_routes",
            "description": (
                "Discover installed AI-agent skills, import route metadata, "
                "detect conflicts, and return recommendations for human choice."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "skillsets": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "scope": {"type": "string"},
                    "workspace_scope": {"type": "string"},
                    "dry_run": {"type": "boolean"},
                    "no_discovery": {"type": "boolean"},
                },
            },
        },
        {
            "name": "route_task",
            "description": "Find current Skills Router routing candidates for a task.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "task": {"type": "string"},
                    "scope": {"type": "string"},
                    "target": {"type": "string"},
                    "limit": {"type": "integer"},
                    "include_inactive": {"type": "boolean"},
                },
                "required": ["task"],
            },
        },
        {
            "name": "uninstall_tool",
            "description": (
                "Remove an installed skill/package from Skills Router-owned "
                "metadata, lockfile, dependency graph, and routing rules. "
                "Does not delete host-owned package resources."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "tool_id": {"type": "string"},
                    "user_id": {"type": "string"},
                    "scope": {"type": "string"},
                    "dry_run": {"type": "boolean"},
                },
                "required": ["tool_id"],
            },
        },
        {
            "name": "list_tools",
            "description": "List installed skills-router tools.",
            "inputSchema": {"type": "object", "properties": {"scope": {"type": "string"}}},
        },
        {
            "name": "inspect_tool",
            "description": "Inspect one installed tool.",
            "inputSchema": {
                "type": "object",
                "properties": {"tool_id": {"type": "string"}},
                "required": ["tool_id"],
            },
        },
        {
            "name": "use_skill",
            "description": (
                "Load a skill's full content for injection into the AI "
                "agent's context. Returns routing rules, capabilities, "
                "use_when triggers, and cached SKILL.md content."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {"tool_id": {"type": "string"}},
                "required": ["tool_id"],
            },
        },
        {
            "name": "watch_once",
            "description": "Run one Registry Watch check cycle.",
            "inputSchema": {
                "type": "object",
                "properties": {"dry_run": {"type": "boolean"}},
            },
        },
    ]
