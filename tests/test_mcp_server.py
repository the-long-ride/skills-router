"""Tests for local JSON-RPC tool server."""

from skills_router.config import SkillsRouterConfig
from skills_router.mcp_server import handle_request


def test_mcp_initialize(tmp_path):
    config = SkillsRouterConfig(data_dir=str(tmp_path))
    response = handle_request(
        {"jsonrpc": "2.0", "id": 1, "method": "initialize"},
        config,
    )

    assert response["result"]["serverInfo"]["name"] == "skills-router"


def test_mcp_tools_list(tmp_path):
    config = SkillsRouterConfig(data_dir=str(tmp_path))
    response = handle_request(
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        config,
    )

    tool_names = {tool["name"] for tool in response["result"]["tools"]}
    assert "install_tool" in tool_names
    assert "uninstall_tool" in tool_names
    assert "index_routes" in tool_names
    assert "refine_routes" in tool_names
    assert "route_task" in tool_names
    assert "get_agent_prompt" in tool_names
    assert "parse_slash_command" in tool_names
    assert "run_slash_command" in tool_names
    assert "watch_once" in tool_names


def test_mcp_unknown_method(tmp_path):
    config = SkillsRouterConfig(data_dir=str(tmp_path))
    response = handle_request(
        {"jsonrpc": "2.0", "id": 3, "method": "nope"},
        config,
    )

    assert response["error"]["code"] == -32601


def test_mcp_parse_slash_command(tmp_path):
    config = SkillsRouterConfig(data_dir=str(tmp_path))
    response = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {
                "name": "parse_slash_command",
                "arguments": {
                    "text": "/skills-router install weather-tool for me",
                    "target": "opencode",
                    "agent_id": "open-local",
                },
            },
        },
        config,
    )

    intent = response["result"]["structuredContent"]["intent"]
    assert intent["command"] == "install"
    assert intent["target"] == "opencode"
    assert intent["scope"] == "workspace:open-local"
    assert response["result"]["content"][0]["text"] == (
        "Parsed /skills-router install request."
    )


def test_mcp_get_agent_prompt_defaults_to_compact_text(tmp_path):
    config = SkillsRouterConfig(data_dir=str(tmp_path))
    response = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 6,
            "method": "tools/call",
            "params": {
                "name": "get_agent_prompt",
                "arguments": {"target": "codex", "agent_id": "codex-local"},
            },
        },
        config,
    )

    prompt = response["result"]["content"][0]["text"]
    assert "Cheapest path" in prompt
    assert "Preferred execution order" not in prompt
    assert prompt == response["result"]["structuredContent"]["prompt"]


def test_mcp_uninstall_tool_removes_skills_router_state(tmp_path):
    from skills_router.storage.memory_store import MemoryBrainIndexStore

    config = SkillsRouterConfig(data_dir=str(tmp_path))
    store = MemoryBrainIndexStore(
        brain_index_path=config.brain_index_path,
        dep_graph_path=config.dep_graph_path,
    )
    store.save_tool({
        "tool_id": "writer-pack",
        "name": "Writer Pack",
        "version": "1.0.0",
    })

    response = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 5,
            "method": "tools/call",
            "params": {
                "name": "uninstall_tool",
                "arguments": {
                    "tool_id": "writer-pack",
                    "user_id": "mcp-agent",
                },
            },
        },
        config,
    )

    result = response["result"]["structuredContent"]
    refreshed = MemoryBrainIndexStore(
        brain_index_path=config.brain_index_path,
        dep_graph_path=config.dep_graph_path,
    )
    assert result["status"] == "UNINSTALLED"
    assert result["package_resources_removed"] is False
    assert result["route_reconciliation"]["status"] == "EMPTY"
    assert refreshed.get_tool("writer-pack") is None
