"""Central configuration for skills-router."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path


def _default_data_dir() -> str:
    """Resolve the default data directory.

    Priority:
    1. SKILLS_ROUTER_HOME environment variable
    2. ~/.skills-router-home file (single-line path)
    3. Default ~/.skills-router/
    """
    env_home = os.environ.get("SKILLS_ROUTER_HOME", "").strip()
    if env_home:
        return env_home
    home_file = Path.home() / ".skills-router-home"
    if home_file.is_file():
        home_content = home_file.read_text(encoding="utf-8").strip()
        if home_content:
            return home_content
    return str(Path.home() / ".skills-router")


def _default_workspace_root() -> str:
    """Resolve the default workspace root for host-agent discovery."""
    return os.getcwd()


@dataclass
class SkillsRouterConfig:
    """Configuration with sensible defaults.

    Loads overrides from ``~/.skills-router/config.json`` if present.
    All threshold constants from blueprint v5 are centralised here.
    """

    # --- Paths ---------------------------------------------------------------
    data_dir: str = field(default_factory=_default_data_dir)
    global_data_dir: str = field(default_factory=_default_data_dir)
    workspace_root: str = field(default_factory=_default_workspace_root)
    audit_log_path: str = ""   # set in __post_init__
    brain_index_path: str = "" # set in __post_init__
    dep_graph_path: str = ""   # set in __post_init__
    registry_cache_dir: str = "" # set in __post_init__
    workspace_skill_dirs: list[str] = field(default_factory=lambda: [
        ".agents/skills",
        ".codex/skills",
        ".claude/skills",
        ".cline/skills",
        ".cursor/skills",
        ".windsurf/skills",
        ".opencode/skills",
        ".agent/skills",
        ".antigravity/skills",
        ".hermes/skills",
        ".kiro/skills",
    ])
    global_skill_dirs: list[str] = field(default_factory=lambda: [
        "$CODEX_HOME/skills",
        "~/.codex/skills",
        "$CLAUDE_HOME/skills",
        "~/.claude/skills",
        "~/.cline/skills",
        "~/.cursor/skills",
        "~/.windsurf/skills",
        "~/.opencode/skills",
        "$ANTIGRAVITY_HOME/skills",
        "~/.antigravity/skills",
        "~/.hermes-agent/skills",
        "~/.hermes/skills",
        "~/.kiro/skills",
    ])

    # --- Registry Resolver ---------------------------------------------------
    registry_base_url: str = "https://registry.skillsrouter.ai/packages"
    registry_fetch_timeout_seconds: int = 10
    registry_max_manifest_bytes: int = 1_048_576
    registry_cache_ttl_seconds: int = 86_400
    registry_require_https: bool = True
    registry_lockfile_path: str = "" # set in __post_init__
    github_manifest_paths: list[str] = field(default_factory=lambda: [
        "skills-router.json",
        "skills_router.json",
        "manifest.json",
        ".skills-router/manifest.json",
    ])

    # --- Backend -------------------------------------------------------------
    storage_backend: str = "memory"  # "memory" | "pgvector"
    pgvector_dsn: str = ""

    # --- Trust Gate thresholds (§4) ------------------------------------------
    trust_hard_block_threshold: float = 0.30
    trust_soft_warn_threshold: float = 0.65

    # --- Semantic Evaluator (§6) ---------------------------------------------
    similarity_threshold: float = 0.85
    embedding_model: str = "all-MiniLM-L6-v2"
    semantic_result_limit: int = 10

    # --- Capability Checker (§7) ---------------------------------------------
    behavior_sim_threshold: float = 0.82

    # --- Human / LLM decision surfaces ---------------------------------------
    prompt_list_limit: int = 5
    prompt_char_limit: int = 1400

    # --- Registry Watch Daemon (§11) -----------------------------------------
    check_interval_seconds: int = 3600
    hysteresis_band: float = 0.05
    registry_watch_state_path: str = "" # set in __post_init__

    # --- LiveSignalFetcher (§12) ---------------------------------------------
    max_retries: int = 3
    backoff_base: int = 2
    circuit_failure_threshold: int = 3
    circuit_reset_seconds: int = 300

    # --- Admin ---------------------------------------------------------------
    admin_channel_id: str = "system-admin"

    def __post_init__(self):
        """Derive paths from data_dir and apply config file overrides."""
        # Apply config file overrides first (may change data_dir)
        config_file = os.path.join(self.data_dir, "config.json")
        if os.path.exists(config_file):
            with open(config_file) as f:
                overrides = json.load(f)
            for key, value in overrides.items():
                if hasattr(self, key):
                    setattr(self, key, value)

        # Derive paths from (possibly overridden) data_dir
        if not self.audit_log_path:
            self.audit_log_path = os.path.join(self.data_dir, "audit.jsonl")
        if not self.brain_index_path:
            self.brain_index_path = os.path.join(self.data_dir, "brain_index.json")
        if not self.dep_graph_path:
            self.dep_graph_path = os.path.join(self.data_dir, "dep_graph.json")
        if not self.registry_cache_dir:
            self.registry_cache_dir = os.path.join(self.data_dir, "registry_cache")
        if not self.registry_lockfile_path:
            self.registry_lockfile_path = os.path.join(
                self.data_dir, "skills-router.lock.json"
            )
        if not self.registry_watch_state_path:
            self.registry_watch_state_path = os.path.join(
                self.data_dir, "registry_watch_state.json"
            )

        # Ensure data_dir exists
        os.makedirs(self.data_dir, exist_ok=True)
