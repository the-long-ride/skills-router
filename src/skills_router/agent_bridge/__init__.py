"""Agent-facing bridge helpers for slash commands and prompt adapters."""

from skills_router.agent_bridge.executor import execute_slash_command
from skills_router.agent_bridge.indexer import index_installed_skillsets
from skills_router.agent_bridge.parser import SlashCommandIntent, parse_slash_command
from skills_router.agent_bridge.profiles import (
    AgentProfile,
    get_agent_profile,
    list_agent_profiles,
    normalize_agent_target,
)
from skills_router.agent_bridge.prompts import render_agent_prompt
from skills_router.agent_bridge.routing import build_routing_plan
from skills_router.agent_bridge.uninstaller import uninstall_skill_metadata

__all__ = [
    "AgentProfile",
    "SlashCommandIntent",
    "build_routing_plan",
    "execute_slash_command",
    "get_agent_profile",
    "index_installed_skillsets",
    "list_agent_profiles",
    "normalize_agent_target",
    "parse_slash_command",
    "render_agent_prompt",
    "uninstall_skill_metadata",
]
