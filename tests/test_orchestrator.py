"""Tests for the full pipeline orchestrator."""

import json
import pytest
from skills_router.config import SkillsRouterConfig
from skills_router.orchestrator import SkillsRouterOrchestrator
from skills_router.storage.memory_store import MemoryBrainIndexStore


class TestOrchestrator:
    """Integration tests for the full pipeline."""

    @pytest.fixture
    def orch(self, config, store):
        """Orchestrator with explicit approve callback."""
        def always_approve(_prompt, _options):
            return 0

        return SkillsRouterOrchestrator(
            config=config,
            store=store,
            decision_callback=always_approve,
        )

    def test_install_brand_new_tool(self, orch, weather_manifest):
        """Installing a brand new tool should succeed."""
        result = orch.install(weather_manifest, scope="global")
        assert result["status"] == "INSTALLED"
        assert result["tool_id"] == "global-meteo-suite"
        assert result["wg_case"] == "CASE_1"
        assert result["decision"] == "APPROVE"

    def test_install_hard_reject(self, orch, untrusted_manifest):
        """Tool with very low trust should be HARD_REJECT."""
        result = orch.install(untrusted_manifest, scope="global")
        assert result["status"] == "HARD_REJECT"
        assert result["wg_case"] == "CASE_TRUST_WARN"

    def test_install_does_not_snapshot_package_resources(self, orch, weather_manifest):
        """Install should not snapshot resources Skills Router does not own."""
        result = orch.install(weather_manifest, scope="global")
        assert "snapshot_id" not in result
        assert result["recovery_action"] is None

    def test_install_saves_to_store(self, orch, store, weather_manifest):
        """Installed tool should be retrievable from the store."""
        orch.install(weather_manifest, scope="global")
        tool = store.get_tool("global-meteo-suite")
        assert tool is not None
        assert tool["name"] == "GlobalMeteo Suite"

    def test_install_writes_audit_log(self, orch, config, weather_manifest):
        """Install should create an audit log entry."""
        from skills_router.audit.logger import AuditLogger
        orch.install(weather_manifest, scope="global")
        audit = AuditLogger(log_path=config.audit_log_path)
        entries = audit.query(tool_id="global-meteo-suite")
        assert len(entries) >= 1

    def test_install_merges_deps(self, orch, store, weather_manifest):
        """Install should merge deps into the dependency graph."""
        orch.install(weather_manifest, scope="global")
        graph = store.get_dep_graph()
        assert "requests" in graph
        assert "numpy" in graph

    def test_orchestrator_does_not_uninstall_packages(self, orch, store, weather_manifest):
        """Package removal is intentionally outside Skills Router."""
        orch.install(weather_manifest, scope="global")
        assert not hasattr(orch, "uninstall")
        assert store.get_tool("global-meteo-suite") is not None

    def test_list_tools(self, orch, weather_manifest):
        """list_tools should return installed tools."""
        orch.install(weather_manifest, scope="global")
        tools = orch.list_tools()
        assert len(tools) == 1
        assert tools[0]["tool_id"] == "global-meteo-suite"

    def test_list_tools_scope_filter(self, orch, weather_manifest):
        """list_tools with scope filter should only return matching tools."""
        orch.install(weather_manifest, scope="global")
        assert len(orch.list_tools(scope="global")) == 1
        assert len(orch.list_tools(scope="workspace:ws-42")) == 0

    def test_inspect_tool(self, orch, weather_manifest):
        """inspect_tool should return the full Brain Index entry."""
        orch.install(weather_manifest, scope="global")
        tool = orch.inspect_tool("global-meteo-suite")
        assert tool is not None
        assert "layer_5_provenance" in tool

    def test_install_with_cancel_callback(self, config, store, weather_manifest):
        """Install with a cancel callback should not install."""
        def always_cancel(prompt, options):
            return len(options) - 1  # Last option is always cancel

        orch = SkillsRouterOrchestrator(
            config=config, store=store, decision_callback=always_cancel,
        )
        result = orch.install(weather_manifest, scope="global")
        assert result["status"] == "CANCELLED"
        assert store.get_tool("global-meteo-suite") is None

    def test_install_with_no_callback_defaults_to_cancel(self, config, store, weather_manifest):
        """No callback should fail closed to cancel."""
        orch = SkillsRouterOrchestrator(
            config=config, store=store, decision_callback=None,
        )
        result = orch.install(weather_manifest, scope="global")
        assert result["status"] == "CANCELLED"
        assert store.get_tool("global-meteo-suite") is None

    def test_install_json_string(self, orch, weather_manifest):
        """Install should accept a JSON string manifest."""
        result = orch.install(json.dumps(weather_manifest), scope="global")
        assert result["status"] == "INSTALLED"

    def test_install_invalid_manifest(self, orch):
        """Invalid manifest should return ERROR."""
        result = orch.install({"name": "Missing tool_id"}, scope="global")
        assert result["status"] == "ERROR"

    def test_install_dry_run_does_not_save_tool(self, orch, store, weather_manifest):
        """Dry-run evaluates the pipeline without mutating registry state."""
        result = orch.install(weather_manifest, scope="global", dry_run=True)

        assert result["status"] == "DRY_RUN_APPROVED"
        assert store.get_tool("global-meteo-suite") is None
        assert store.get_dep_graph() == {}

    def test_install_with_out_of_bounds_callback(self, config, store, weather_manifest):
        """Out of bounds index from callback should default to cancel (last option)."""
        def bad_callback(prompt, options):
            return 999  # out of bounds

        orch = SkillsRouterOrchestrator(
            config=config, store=store, decision_callback=bad_callback,
        )
        result = orch.install(weather_manifest, scope="global")
        assert result["status"] == "CANCELLED"
        assert store.get_tool("global-meteo-suite") is None

    def test_install_with_non_int_callback(self, config, store, weather_manifest):
        """Non-integer from callback should default to cancel (last option)."""
        def bad_callback(prompt, options):
            return "0"  # string instead of int

        orch = SkillsRouterOrchestrator(
            config=config, store=store, decision_callback=bad_callback,
        )
        result = orch.install(weather_manifest, scope="global")
        assert result["status"] == "CANCELLED"
        assert store.get_tool("global-meteo-suite") is None

    def test_install_with_exception_callback(self, config, store, weather_manifest):
        """Exception raised by callback should default to cancel (last option) and not crash."""
        def crashing_callback(prompt, options):
            raise RuntimeError("Something went wrong in the agent UI")

        orch = SkillsRouterOrchestrator(
            config=config, store=store, decision_callback=crashing_callback,
        )
        result = orch.install(weather_manifest, scope="global")
        assert result["status"] == "CANCELLED"
        assert store.get_tool("global-meteo-suite") is None

    def test_parse_error_dependency_installs_isolated_without_graph_mutation(self, orch, store):
        """Approving a parse-error dependency review should not mutate the shared graph."""
        manifest = {
            "tool_id": "bad-dep-tool",
            "name": "Bad Dep Tool",
            "version": "1.0.0",
            "dependencies": {"bad-pkg": "not_a_valid_spec!!!"},
            "layer_5_provenance": {
                "signature_verified": True,
                "trust_factors": {
                    "open_critical_cves": 0,
                    "last_commit_days_ago": 10,
                    "community_sentiment_score": 0.9,
                },
                "install_source": "official-registry",
            },
        }
        result = orch.install(manifest, scope="global")
        assert result["status"] == "INSTALLED"
        assert result["details"]["dependencies"]["status"] == "PARSE_ERROR"
        assert "bad-pkg" not in store.get_dep_graph()
