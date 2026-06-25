"""Tests for gateway support of hooks and MCP servers from installed active skills."""

from __future__ import annotations

import json
import os
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from skills_router.agent_bridge.connect import build_agent_connection, _build_global_agent_connection
from skills_router.agent_bridge.inventory import build_skill_inventory, render_inventory_markdown, use_skill
from skills_router.config import SkillsRouterConfig
from skills_router.layers.manifest_parser import ManifestParser, ManifestParseError
from skills_router.layers.mcp_client import MCPClient
from skills_router.layers.hook_runner import run_hooks_for_event
from skills_router.mcp_server import _get_all_tools_specs, _call_tool
from skills_router.storage.memory_store import MemoryBrainIndexStore


def test_manifest_parser_with_gateway_fields():
    parser = ManifestParser()

    # 1. Valid manifest containing hooks and mcp_servers
    valid_manifest = {
        "tool_id": "test-tool",
        "name": "Test Tool",
        "version": "1.0.0",
        "layer_3_capabilities": {
            "hooks": {
                "SessionStart": [
                    {"type": "command", "command": "echo hello", "async": False}
                ]
            },
            "mcp_servers": {
                "test-mcp": {
                    "command": "node",
                    "args": ["server.js"],
                    "tools": [
                        {
                            "name": "say_hello",
                            "description": "Say hello",
                            "inputSchema": {"type": "object", "properties": {}},
                        }
                    ],
                }
            },
        },
    }

    parsed = parser.parse(valid_manifest)
    caps = parsed["layer_3_capabilities"]
    assert "hooks" in caps
    assert "mcp_servers" in caps
    assert caps["hooks"]["SessionStart"][0]["command"] == "echo hello"
    assert caps["mcp_servers"]["test-mcp"]["command"] == "node"

    # 2. Invalid manifest - hooks is not a dict
    invalid_manifest = {
        "tool_id": "test-tool",
        "name": "Test Tool",
        "version": "1.0.0",
        "layer_3_capabilities": {
            "hooks": "not-a-dict",
        },
    }
    with pytest.raises(ManifestParseError) as exc_info:
        parser.parse(invalid_manifest)
    assert "must be a dict" in str(exc_info.value)


@patch("subprocess.Popen")
def test_mcp_client_discover_and_call(mock_popen):
    mock_process = MagicMock()
    mock_process.poll.return_value = None
    mock_popen.return_value = mock_process

    # Set up client
    client = MCPClient("node", ["server.js"])

    # 1. Test discover_tools
    # Initialize response (ID=1) followed by tools/list response (ID=2)
    mock_process.stdout.readline.side_effect = [
        json.dumps({"jsonrpc": "2.0", "id": 1, "result": {"protocolVersion": "2024-11-05"}}) + "\n",
        json.dumps({
            "jsonrpc": "2.0",
            "id": 2,
            "result": {
                "tools": [
                    {"name": "test_tool", "description": "A test tool", "inputSchema": {}}
                ]
            }
        }) + "\n"
    ]

    tools = client.discover_tools()
    assert len(tools) == 1
    assert tools[0]["name"] == "test_tool"
    mock_popen.assert_called_with(
        ["node", "server.js"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=dict(os.environ),
        bufsize=1,
    )

    # 2. Test call_tool
    # Reset mock and mock readline calls for initialize (ID=1) and tools/call (ID=2)
    mock_process.stdout.readline.side_effect = [
        json.dumps({"jsonrpc": "2.0", "id": 1, "result": {"protocolVersion": "2024-11-05"}}) + "\n",
        json.dumps({
            "jsonrpc": "2.0",
            "id": 2,
            "result": {"content": [{"type": "text", "text": "Tool called successfully!"}]}
        }) + "\n"
    ]

    result = client.call_tool("test_tool", {"arg": "val"})
    assert result["content"][0]["text"] == "Tool called successfully!"


@patch("subprocess.run")
def test_hook_runner(mock_run):
    # Mock subprocess.run to return successful JSON string output
    mock_res = MagicMock()
    mock_res.returncode = 0
    mock_res.stdout = json.dumps({
        "additional_context": "Merged markdown instructions context here."
    })
    mock_run.return_value = mock_res

    active_hooks = {
        "SessionStart": [
            {"type": "command", "command": "python run-hook.py", "async": False}
        ]
    }

    result = run_hooks_for_event("SessionStart", active_hooks, {"agent_id": "test-agent"})
    assert result["status"] == "OK"
    assert "Merged markdown instructions context here." in result["additional_context"]

    # Verify context variables were propagated to hook environment
    args, kwargs = mock_run.call_args
    env = kwargs["env"]
    assert "SKILLS_ROUTER_CONTEXT" in env
    assert env["SKILLS_ROUTER_AGENT_ID"] == "test-agent"


@pytest.fixture
def temp_gateway_config(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    routing = {
        "version": 1,
        "packages": {
            "mcp-skill": {
                "tool_id": "mcp-skill",
                "name": "MCP Skill",
                "version": "1.0.0",
                "package_type": "skillset",
                "scope": "global",
                "status": "active",
                "rules": [
                    {
                        "rule_id": "mcp-skill:default",
                        "tool_id": "mcp-skill",
                        "skill_id": "default",
                        "name": "MCP Skill",
                        "scope": "global",
                        "status": "active",
                    }
                ],
            }
        },
    }
    (data_dir / "skills-router.json").write_text(json.dumps(routing, indent=2))

    brain_data = {
        "mcp-skill": {
            "tool_id": "mcp-skill",
            "name": "MCP Skill",
            "version": "1.0.0",
            "description": "Exposes an MCP server and hooks",
            "layer_3_capabilities": {
                "hooks": {
                    "SessionStart": [
                        {"type": "command", "command": "echo 'Hello session'", "async": False}
                    ]
                },
                "mcp_servers": {
                    "skill-mcp": {
                        "command": "node",
                        "args": ["server.js"],
                        "tools": [
                            {
                                "name": "skill_mcp_tool",
                                "description": "Skill MCP Tool",
                                "inputSchema": {"type": "object", "properties": {}},
                            }
                        ],
                    }
                },
            },
            "source_metadata": {
                "skill_md_content": "# MCP Skill\n\nRuns MCP server.",
            },
            "layer_meta": {"install_scope": "global"},
        }
    }
    (data_dir / "brain_index.json").write_text(json.dumps(brain_data, indent=2))

    return SkillsRouterConfig(data_dir=str(data_dir))


def test_connect_merges_mcp_servers_and_hooks(temp_gateway_config):
    # Verify build_agent_connection merges active skills' MCP configs and hooks
    result = build_agent_connection(temp_gateway_config, target="codex")
    mcp_servers = result["mcp_config"]["mcpServers"]
    assert "skills-router" in mcp_servers
    assert "skill-mcp" in mcp_servers
    assert mcp_servers["skill-mcp"]["command"] == "node"
    assert "SessionStart" in result["hooks"]
    assert result["hooks"]["SessionStart"][0]["command"] == "echo 'Hello session'"


def test_inventory_and_use_skill_expose_gateway_fields(temp_gateway_config):
    # 1. Test build_skill_inventory includes hooks/mcp_servers
    inv = build_skill_inventory(temp_gateway_config)
    skill = inv["skills"][0]
    assert "hooks" in skill
    assert "mcp_servers" in skill
    assert "SessionStart" in skill["hooks"]
    assert "skill-mcp" in skill["mcp_servers"]

    # 2. Test render_inventory_markdown describes them
    md = render_inventory_markdown(inv)
    assert "Hooks: SessionStart" in md
    assert "MCP Servers: skill-mcp" in md

    # 3. Test use_skill includes hooks/mcp_servers in metadata and content
    res = use_skill(temp_gateway_config, "mcp-skill")
    assert res["status"] == "OK"
    assert "SessionStart" in res["metadata"]["hooks"]
    assert "skill-mcp" in res["metadata"]["mcp_servers"]
    assert "## Hooks" in res["content"]
    assert "## MCP Servers" in res["content"]


@patch("skills_router.layers.mcp_client.MCPClient.call_tool")
def test_mcp_server_proxying_and_run_hook(mock_call_tool, temp_gateway_config):
    # Mock proxy tool call response
    mock_call_tool.return_value = {
        "content": [{"type": "text", "text": "Proxied response!"}]
    }

    # 1. Test tools list contains all tools
    specs = _get_all_tools_specs(temp_gateway_config)
    names = [spec["name"] for spec in specs]
    assert "run_agent_hook" in names
    assert "skill_mcp_tool" in names

    # 2. Test proxy call routing to subprocess mcp server
    res = _call_tool({
        "name": "skill_mcp_tool",
        "arguments": {"x": 1}
    }, temp_gateway_config)
    assert res["content"][0]["text"] == "Proxied response!"
    mock_call_tool.assert_called_with("skill_mcp_tool", {"x": 1})

    # 3. Test run_agent_hook built-in tool call
    with patch("skills_router.layers.hook_runner.subprocess.run") as mock_run:
        mock_run_res = MagicMock()
        mock_run_res.returncode = 0
        mock_run_res.stdout = "Raw hook stdout context output"
        mock_run.return_value = mock_run_res

        hook_res = _call_tool({
            "name": "run_agent_hook",
            "arguments": {
                "event_name": "SessionStart",
                "context": {"user": "tester"}
            }
        }, temp_gateway_config)

        # Result is formatted by _tool_result, containing structuredContent
        structured = hook_res["structuredContent"]
        assert structured["status"] == "OK"
        assert "Raw hook stdout context output" in structured["additional_context"]


def test_cli_run_hook(temp_gateway_config):
    from skills_router.cli import build_parser, cmd_run_hook
    import argparse

    # Test run-hook CLI command execution
    parser = build_parser()
    args = parser.parse_args(["run-hook", "SessionStart", "--context", '{"user": "cli-test"}'])
    assert args.command == "run-hook"
    assert args.event == "SessionStart"
    assert args.context == '{"user": "cli-test"}'

    with patch("skills_router.layers.hook_runner.subprocess.run") as mock_run:
        mock_run_res = MagicMock()
        mock_run_res.returncode = 0
        mock_run_res.stdout = json.dumps({"additional_context": "CLI hook output"})
        mock_run.return_value = mock_run_res

        with patch("skills_router.cli.console.print") as mock_print:
            rc = cmd_run_hook(args, temp_gateway_config)
            assert rc == 0
            mock_print.assert_called_once_with("CLI hook output")


def test_format_hook_response_targets():
    from skills_router.layers.hook_runner import format_hook_response

    # Cursor
    res_cursor = format_hook_response("SessionStart", "test-context", target="cursor")
    assert res_cursor == {"additional_context": "test-context"}

    # Claude
    res_claude = format_hook_response("SessionStart", "test-context", target="claude")
    assert res_claude == {
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": "test-context",
        }
    }

    # Generic / other
    res_generic = format_hook_response("SessionStart", "test-context", target="generic")
    assert res_generic == {"additionalContext": "test-context"}

    # Auto-detection via environment variables
    with patch.dict(os.environ, {"CURSOR_PLUGIN_ROOT": "/some/path"}):
        res_auto = format_hook_response("SessionStart", "test-context")
        assert res_auto == {"additional_context": "test-context"}

    with patch.dict(os.environ, {"CLAUDE_PLUGIN_ROOT": "/some/path"}):
        res_auto = format_hook_response("SessionStart", "test-context")
        assert res_auto == {
            "hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": "test-context",
            }
        }


def test_cli_run_hook_with_targets(temp_gateway_config):
    from skills_router.cli import build_parser, cmd_run_hook

    # Target Claude with JSON output
    parser = build_parser()
    args = parser.parse_args(["run-hook", "SessionStart", "--target", "claude", "--json"])
    
    with patch("skills_router.layers.hook_runner.subprocess.run") as mock_run:
        mock_run_res = MagicMock()
        mock_run_res.returncode = 0
        mock_run_res.stdout = json.dumps({"additional_context": "CLI hook output"})
        mock_run.return_value = mock_run_res

        with patch("skills_router.cli._print_json") as mock_print_json:
            rc = cmd_run_hook(args, temp_gateway_config)
            assert rc == 0
            mock_print_json.assert_called_once()
            payload = mock_print_json.call_args[0][0]
            assert "hookSpecificOutput" in payload
            assert payload["hookSpecificOutput"]["additionalContext"] == "CLI hook output"


@pytest.fixture
def temp_empty_config(tmp_path):
    data_dir = tmp_path / "data_empty"
    data_dir.mkdir()

    routing = {
        "version": 1,
        "packages": {},
    }
    (data_dir / "skills-router.json").write_text(json.dumps(routing, indent=2))

    brain_data = {}
    (data_dir / "brain_index.json").write_text(json.dumps(brain_data, indent=2))

    return SkillsRouterConfig(data_dir=str(data_dir))


def test_connect_omits_hooks_config_when_empty(temp_empty_config):
    # Verify build_agent_connection does NOT have hooks or hooks_config when none exist
    result = build_agent_connection(temp_empty_config, target="codex")
    assert "hooks" not in result
    assert "hooks_config" not in result
    # It should only contain the router itself in mcpServers
    mcp_servers = result["mcp_config"]["mcpServers"]
    assert "skills-router" in mcp_servers
    assert len(mcp_servers) == 1


def test_render_agent_prompt_dynamic_mcp_and_hooks(temp_gateway_config, temp_empty_config):
    from skills_router.agent_bridge.prompts import render_agent_prompt

    # 1. With empty config (no hooks/MCP)
    prompt_empty = render_agent_prompt("codex", config=temp_empty_config)
    assert "Lifecycle Hooks" not in prompt_empty
    assert "Proxied MCP Tools" not in prompt_empty

    # 2. With gateway config (has active hooks and MCP)
    prompt_active = render_agent_prompt("codex", config=temp_gateway_config)
    assert "### Lifecycle Hooks" in prompt_active
    assert "### Proxied MCP Tools" in prompt_active

