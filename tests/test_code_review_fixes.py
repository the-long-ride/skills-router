"""Tests for code review fixes — config wiring, scope filtering, validation, thread safety."""

from __future__ import annotations

import threading

import pytest

from skills_router.config import SkillsRouterConfig
from skills_router.layers.capability_checker import CapabilityChecker
from skills_router.layers.manifest_parser import ManifestParser, ManifestParseError
from skills_router.layers.semantic_evaluator import SemanticEvaluator
from skills_router.layers.trust_gate import TrustGate
from skills_router.orchestrator import SkillsRouterOrchestrator
from skills_router.storage.memory_store import MemoryBrainIndexStore


class TestConfigWiring:
    """🔴1: Verify config thresholds are wired into layer classes."""

    def test_trust_gate_uses_config_thresholds(self):
        gate = TrustGate(hard_block_threshold=0.50, soft_warn_threshold=0.80)
        assert gate.HARD_BLOCK_THRESHOLD == 0.50
        assert gate.SOFT_WARN_THRESHOLD == 0.80

    def test_trust_gate_default_thresholds(self):
        gate = TrustGate()
        assert gate.HARD_BLOCK_THRESHOLD == 0.30
        assert gate.SOFT_WARN_THRESHOLD == 0.65

    def test_semantic_evaluator_uses_config_threshold(self):
        ev = SemanticEvaluator(similarity_threshold=0.90)
        assert ev.SIMILARITY_THRESHOLD == 0.90

    def test_capability_checker_uses_config_threshold(self):
        cc = CapabilityChecker(behavior_sim_threshold=0.75)
        assert cc.BEHAVIOR_SIM_THRESHOLD == 0.75

    def test_orchestrator_passes_config_to_layers(self, config, store):
        config.trust_hard_block_threshold = 0.40
        config.trust_soft_warn_threshold = 0.75
        config.similarity_threshold = 0.92
        config.behavior_sim_threshold = 0.88

        orch = SkillsRouterOrchestrator(config=config, store=store)
        assert orch.trust_gate.HARD_BLOCK_THRESHOLD == 0.40
        assert orch.trust_gate.SOFT_WARN_THRESHOLD == 0.75
        assert orch.evaluator.SIMILARITY_THRESHOLD == 0.92
        assert orch.capability_checker.BEHAVIOR_SIM_THRESHOLD == 0.88

    def test_custom_threshold_changes_trust_verdict(self):
        """Raising SOFT_WARN_THRESHOLD above computed score triggers warning."""
        strict = TrustGate(soft_warn_threshold=1.0)
        manifest = {
            "publisher_signature": {"verified": True},
            "install_source": "official-registry",
            "open_critical_cves": 0,
            "last_commit_days_ago": 10,
            "community_sentiment_score": 0.9,
        }
        result = strict.evaluate(manifest)
        # Trust score is 0.99 — with threshold=1.0 this becomes SOFT_WARN
        assert result["verdict"] == "SOFT_WARN"
        assert result["score"] < 1.0


class TestScopeFiltering:
    """🔴3: Verify _in_memory filters by scope."""

    def test_scope_filtering_excludes_other_workspaces(self):
        ev = SemanticEvaluator()
        new_tool = {
            "tool_id": "new-tool",
            "name": "New Tool",
            "layer_1_domain_tags": ["Weather"],
            "layer_3_capabilities": {"inputs": ["x"], "outputs": ["y"], "permissions": []},
            "layer_meta": {"install_scope": "workspace:ws-1"},
        }
        brain_index = [
            {
                "tool_id": "other-ws-tool",
                "name": "Other Workspace Tool",
                "layer_1_domain_tags": ["Weather"],
                "layer_3_capabilities": {"inputs": ["x"], "outputs": ["y"], "permissions": []},
                "layer_meta": {"install_scope": "workspace:ws-99"},
            },
            {
                "tool_id": "global-tool",
                "name": "Global Tool",
                "layer_1_domain_tags": ["Weather"],
                "layer_3_capabilities": {"inputs": ["x"], "outputs": ["y"], "permissions": []},
                "layer_meta": {"install_scope": "global"},
            },
        ]
        result = ev.evaluate(new_tool, scope="workspace:ws-1", brain_index=brain_index)
        # Should only compare against global-tool, not other-ws-tool
        tool_ids_compared = [s["tool_id"] for s in result["all_scores"]]
        assert "other-ws-tool" not in tool_ids_compared
        assert "global-tool" in tool_ids_compared


class TestManifestValidation:
    """🟢7: Strengthened manifest validation."""

    def test_valid_tool_id_passes(self):
        parser = ManifestParser()
        result = parser.parse({
            "tool_id": "my-valid-tool",
            "name": "Valid Tool",
            "version": "1.0.0",
        })
        assert result["tool_id"] == "my-valid-tool"

    def test_invalid_tool_id_spaces(self):
        parser = ManifestParser()
        with pytest.raises(ManifestParseError, match="Invalid tool_id"):
            parser.parse({"tool_id": "bad tool id", "name": "X", "version": "1.0.0"})

    def test_invalid_tool_id_uppercase(self):
        parser = ManifestParser()
        with pytest.raises(ManifestParseError, match="Invalid tool_id"):
            parser.parse({"tool_id": "BadTool", "name": "X", "version": "1.0.0"})

    def test_invalid_tool_id_single_char(self):
        parser = ManifestParser()
        with pytest.raises(ManifestParseError, match="Invalid tool_id"):
            parser.parse({"tool_id": "x", "name": "X", "version": "1.0.0"})

    def test_invalid_version(self):
        parser = ManifestParser()
        with pytest.raises(ManifestParseError, match="Invalid version"):
            parser.parse({"tool_id": "my-tool", "name": "X", "version": "not-a-version"})

    def test_invalid_dependency_specifier_deferred_to_resolver(self):
        parser = ManifestParser()
        result = parser.parse({
            "tool_id": "my-tool",
            "name": "X",
            "version": "1.0.0",
            "dependencies": {"requests": ">>invalid<<"},
        })
        assert result["dependencies"]["requests"] == ">>invalid<<"

    def test_valid_dependencies_pass(self):
        parser = ManifestParser()
        result = parser.parse({
            "tool_id": "my-tool",
            "name": "X",
            "version": "1.0.0",
            "dependencies": {"requests": ">=2.25.0", "numpy": "==1.21.0"},
        })
        assert "requests" in result["dependencies"]


class TestThreadSafety:
    """🟢1: Verify thread safety of MemoryBrainIndexStore."""

    def test_concurrent_save_and_read(self):
        store = MemoryBrainIndexStore()
        errors = []

        def writer():
            for i in range(50):
                try:
                    store.save_tool({
                        "tool_id": f"tool-{threading.current_thread().name}-{i}",
                        "name": f"Tool {i}",
                        "version": "1.0.0",
                    })
                except Exception as e:
                    errors.append(e)

        def reader():
            for _ in range(50):
                try:
                    store.get_all_tools()
                except Exception as e:
                    errors.append(e)

        threads = []
        for n in range(4):
            threads.append(threading.Thread(target=writer, name=f"writer-{n}"))
            threads.append(threading.Thread(target=reader, name=f"reader-{n}"))

        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        assert len(errors) == 0, f"Thread safety errors: {errors}"


class TestDaemonSeeding:
    """🔴2: Daemon seeds hashes on start to prevent false alarms."""

    def test_start_seeds_hashes(self):
        from skills_router.daemon.registry_watch import RegistryWatchDaemon

        store = MemoryBrainIndexStore()
        store.save_tool({
            "tool_id": "existing-tool",
            "name": "Existing",
            "version": "1.0.0",
            "layer_4_telemetry": {"last_known_stable_state_hash": "abc123"},
            "layer_5_provenance": {"trust_score": 0.9},
            "layer_meta": {"install_scope": "global"},
        })

        daemon = RegistryWatchDaemon(
            evaluator=SemanticEvaluator(),
            trust_gate=TrustGate(),
            brain_index_db=store,
            wg_notifier=_MockNotifier(),
            live_signal_fetcher=_MockFetcher(),
        )
        daemon._seed_hashes()
        assert "existing-tool" in daemon._last_hashes
        assert daemon._last_hashes["existing-tool"] == "abc123"

    def test_run_once_after_seed_no_false_alerts(self):
        from skills_router.daemon.registry_watch import RegistryWatchDaemon

        store = MemoryBrainIndexStore()
        store.save_tool({
            "tool_id": "existing-tool",
            "name": "Existing",
            "version": "1.0.0",
            "layer_4_telemetry": {"last_known_stable_state_hash": "abc123"},
            "layer_5_provenance": {"trust_score": 0.9},
            "layer_meta": {"install_scope": "global"},
        })

        notifier = _MockNotifier()
        daemon = RegistryWatchDaemon(
            evaluator=SemanticEvaluator(),
            trust_gate=TrustGate(),
            brain_index_db=store,
            wg_notifier=notifier,
            live_signal_fetcher=_MockFetcher(),
        )
        daemon._seed_hashes()
        daemon.run_once()
        # No hash changed → no overlap notifications should fire
        assert len(notifier.history) == 0


class TestPackageExports:
    """🟡6: Package exports work."""

    def test_import_orchestrator(self):
        from skills_router import SkillsRouterOrchestrator
        assert SkillsRouterOrchestrator is not None

    def test_import_config(self):
        from skills_router import SkillsRouterConfig
        assert SkillsRouterConfig is not None

    def test_import_store(self):
        from skills_router import MemoryBrainIndexStore
        assert MemoryBrainIndexStore is not None


class TestDRYCase1Builder:
    """🔴5: CASE_1 context builder is extracted as reusable method."""

    def test_build_case1_ctx_returns_expected_keys(self):
        tool = {
            "layer_1_domain_tags": ["Weather"],
            "layer_3_capabilities": {
                "inputs": ["lat"],
                "outputs": ["temp"],
                "permissions": ["network"],
            },
            "layer_5_provenance": {"publisher_id": "org"},
        }
        trust_result = {"score": 0.91}
        ctx = SkillsRouterOrchestrator._build_case1_ctx(tool, trust_result)
        assert ctx["domain_tags"] == "Weather"
        assert ctx["trust_score"] == 0.91
        assert ctx["publisher"] == "org"
        assert "output_desc" in ctx
        assert "input_desc" in ctx
        assert "permissions" in ctx


# -- Helpers ------------------------------------------------------------------

class _MockNotifier:
    def __init__(self):
        self._history = []

    @property
    def history(self):
        return list(self._history)

    def send(self, **kwargs):
        self._history.append(kwargs)


class _MockFetcher:
    """Returns high-trust signals so no trust degradation fires."""

    def fetch(self, tool):
        prov = tool.get("layer_5_provenance", {})
        return {
            "publisher_signature": {"verified": prov.get("signature_verified", True)},
            "install_source": prov.get("install_source", "official-registry"),
            "open_critical_cves": 0,
            "last_commit_days_ago": 10,
            "community_sentiment_score": 0.9,
        }
