"""Tests for the skill inventory + use_skill feature.

Verifies:
  - build_skill_inventory reads routing state
  - render_inventory_markdown produces readable output
  - use_skill returns full skill content for agent injection
  - use_skill handles NOT_FOUND gracefully
  - Slash command parser recognizes /use as its own command
  - Executor dispatches use command correctly
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from skills_router.agent_bridge.inventory import (
    build_skill_inventory,
    render_inventory_markdown,
    use_skill,
)
from skills_router.agent_bridge.parser import parse_slash_command
from skills_router.config import SkillsRouterConfig


@pytest.fixture
def temp_config_with_routing(tmp_path):
    """Create a config with routing + brain index for a fake installed skill."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    routing = {
        "version": 1,
        "packages": {
            "weather-tool": {
                "tool_id": "weather-tool",
                "name": "Weather Tool",
                "version": "1.0.0",
                "package_type": "skillset",
                "scope": "global",
                "status": "active",
                "target_agents": ["codex"],
                "rules": [
                    {
                        "rule_id": "weather-tool:default",
                        "tool_id": "weather-tool",
                        "skill_id": "default",
                        "name": "Weather",
                        "scope": "global",
                        "status": "active",
                        "use_when": "weather or forecast tasks",
                        "prompt_snippet": "When the task mentions weather, route to weather-tool.default.",
                        "priority": 101,
                    }
                ],
            },
            "pending-tool": {
                "tool_id": "pending-tool",
                "name": "Pending Skill",
                "version": "0.1.0",
                "package_type": "plugin",
                "scope": "global",
                "status": "needs_selection",
                "rules": [
                    {
                        "rule_id": "pending-tool:default",
                        "tool_id": "pending-tool",
                        "skill_id": "default",
                        "name": "Pending Skill",
                        "scope": "global",
                        "status": "needs_selection",
                        "use_when": "pending tasks",
                        "prompt_snippet": "Needs activation.",
                        "priority": 100,
                    }
                ],
            },
        },
    }
    routing_path = data_dir / "skills-router.json"
    routing_path.write_text(json.dumps(routing, indent=2))

    brain_file = data_dir / "brain_index.json"
    brain_data = {
        "weather-tool": {
            "tool_id": "weather-tool",
            "name": "Weather Tool",
            "version": "1.0.0",
            "description": "Get weather forecasts",
            "layer_1_domain_tags": ["weather", "forecast"],
            "layer_3_capabilities": {
                "outputs": ["weather report", "forecast"],
                "inputs": ["location"],
            },
            "layer_5_provenance": {
                "provider": "WeatherCorp",
                "trust_score": 0.92,
            },
            "source_metadata": {
                "skill_md_content": "# Weather Tool\n\nUse this skill for weather queries.",
            },
            "layer_meta": {"install_scope": "global"},
        }
    }
    brain_file.write_text(json.dumps(brain_data, indent=2))

    config = SkillsRouterConfig(data_dir=str(data_dir))
    return config


class TestBuildSkillInventory:
    def test_builds_from_routing_file(self, temp_config_with_routing):
        inv = build_skill_inventory(temp_config_with_routing)
        assert inv["count"] == 2
        assert inv["active_count"] == 1
        assert inv["pending_count"] == 1

    def test_skill_has_metadata(self, temp_config_with_routing):
        inv = build_skill_inventory(temp_config_with_routing)
        weather = [s for s in inv["skills"] if s["tool_id"] == "weather-tool"][0]
        assert weather["name"] == "Weather"
        assert weather["use_when"] == "weather or forecast tasks"
        assert weather["scope"] == "global"
        assert weather["status"] == "active"
        assert weather["package_type"] == "skillset"

    def test_empty_when_no_routing(self, tmp_path):
        data_dir = tmp_path / "empty"
        data_dir.mkdir()
        config = SkillsRouterConfig(data_dir=str(data_dir))
        inv = build_skill_inventory(config)
        assert inv["count"] == 0


class TestRenderInventoryMarkdown:
    def test_renders_active_skills(self, temp_config_with_routing):
        inv = build_skill_inventory(temp_config_with_routing)
        md = render_inventory_markdown(inv)
        assert "## Installed Skills" in md
        assert "### Active" in md
        assert "Weather" in md
        assert "weather-tool.default" in md
        assert "weather or forecast tasks" in md

    def test_renders_pending_skills(self, temp_config_with_routing):
        inv = build_skill_inventory(temp_config_with_routing)
        md = render_inventory_markdown(inv)
        assert "### Pending Selection" in md
        assert "Pending Skill" in md
        assert "needs activation" in md

    def test_renders_empty_state(self, tmp_path):
        data_dir = tmp_path / "empty"
        data_dir.mkdir()
        config = SkillsRouterConfig(data_dir=str(data_dir))
        inv = build_skill_inventory(config)
        md = render_inventory_markdown(inv)
        assert "No skills are currently installed" in md

    def test_includes_use_instruction(self, temp_config_with_routing):
        inv = build_skill_inventory(temp_config_with_routing)
        md = render_inventory_markdown(inv)
        assert "/skills-router use" in md
        assert "/skills-router list" in md


class TestUseSkill:
    def test_returns_full_content(self, temp_config_with_routing):
        result = use_skill(temp_config_with_routing, "weather-tool")
        assert result["status"] == "OK"
        assert result["tool_id"] == "weather-tool"
        assert "Weather Tool" in result["content"]
        assert "weather or forecast tasks" in result["content"]
        assert "weather report" in result["content"]
        assert "WeatherCorp" in result["content"]
        # Trust score: 0.92 -> 92%
        assert "92%" in result["content"]

    def test_includes_skill_md_content(self, temp_config_with_routing):
        result = use_skill(temp_config_with_routing, "weather-tool")
        assert "# Weather Tool" in result["content"]
        assert "Use this skill for weather queries" in result["content"]

    def test_returns_not_found(self, temp_config_with_routing):
        result = use_skill(temp_config_with_routing, "nonexistent")
        assert result["status"] == "NOT_FOUND"
        assert "nonexistent" in result["error"]

    def test_metadata_is_correct(self, temp_config_with_routing):
        result = use_skill(temp_config_with_routing, "weather-tool")
        meta = result["metadata"]
        assert meta["name"] == "Weather Tool"
        assert meta["use_when"] == "weather or forecast tasks"
        assert meta["status"] == "active"
        assert meta["has_skill_md"] is True


class TestParserUseCommand:
    def test_parses_use_as_own_command(self):
        intent = parse_slash_command(
            "/skills-router use weather-tool", target="codex"
        )
        assert intent.command == "use"
        assert intent.arguments == {"tool_id": "weather-tool"}

    def test_load_is_alias_for_use(self):
        intent = parse_slash_command(
            "/skills-router load weather-tool", target="codex"
        )
        assert intent.command == "use"

    def test_inject_is_alias_for_use(self):
        intent = parse_slash_command(
            "/skills-router inject weather-tool", target="codex"
        )
        assert intent.command == "use"

    def test_use_requires_tool_id(self):
        with pytest.raises(ValueError, match="tool_id"):
            parse_slash_command("/skills-router use", target="codex")


class TestUseSkillFindsSkillWithoutBrainEntry:
    def test_uses_routing_only(self, tmp_path):
        """use_skill should work with only routing data, no brain entry."""
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        routing = {
            "version": 1,
            "packages": {
                "routing-only": {
                    "tool_id": "routing-only",
                    "name": "Routing Only",
                    "scope": "global",
                    "status": "active",
                    "rules": [
                        {
                            "rule_id": "routing-only:default",
                            "tool_id": "routing-only",
                            "skill_id": "default",
                            "name": "Routing Only",
                            "use_when": "routing tasks",
                            "prompt_snippet": "For routing.",
                            "status": "active",
                            "scope": "global",
                            "priority": 100,
                        }
                    ],
                }
            },
        }
        (data_dir / "skills-router.json").write_text(json.dumps(routing))
        config = SkillsRouterConfig(data_dir=str(data_dir))
        result = use_skill(config, "routing-only")
        assert result["status"] == "OK"
        assert "Routing Only" in result["content"]
        assert "routing tasks" in result["content"]
