"""Tests for Workspace/Global prompt templates and engine."""

import pytest
from skills_router.wg.prompt_engine import PromptEngine
from skills_router.wg import templates


class TestWGTemplates:
    """Test that all templates render without errors."""

    def test_case_1_renders(self):
        ctx = {
            "domain_tags": "Weather, API",
            "output_desc": "temperature, forecast",
            "input_desc": "zipcode",
            "permissions": "network: outbound_https",
            "trust_score": 0.91,
            "publisher": "meteo-org",
        }
        output = templates.case_1_brand_new(ctx)
        assert "capabilities not found" in output
        assert "meteo-org" in output

    def test_case_2_renders(self):
        ctx = {
            "new_features": "alerts, push notifications",
            "delta_permissions": "push",
            "perf_delta": "100",
            "perf_direction": "slower",
            "d_community": "0.79",
            "a_community": "0.84",
            "a_workflows": "daily-brief",
        }
        output = templates.case_2_partial_overlap(ctx)
        assert "Overlap" in output

    def test_case_2_options_with_extensible(self):
        opts = templates.case_2_options(extensible=True)
        assert any("extension" in o.lower() for o in opts)

    def test_case_2_options_without_extensible(self):
        opts = templates.case_2_options(extensible=False)
        assert not any("extension" in o.lower() for o in opts)

    def test_case_3_renders(self):
        output = templates.case_3_parent_child({})
        assert "Redundancy" in output

    def test_case_4_renders(self):
        output = templates.case_4_exact_match({})
        assert "Exact duplicate" in output

    def test_case_5_renders(self):
        output = templates.case_5_tangential({
            "shared": ["a"], "d_only": ["b"], "x_only": ["c"],
        })
        assert "Partial Overlap" in output

    def test_case_dep_renders(self):
        output = templates.case_dep_conflict({
            "package": "numpy",
            "version_d": "1.19",
            "version_locked": "1.21",
            "locked_by": "tool-a",
        })
        assert "Dependency Conflict" in output

    def test_case_dep_with_parse_errors(self):
        output = templates.case_dep_conflict({
            "package": "numpy",
            "parse_errors": [
                {"package": "bad", "specifier": "!!!", "error": "invalid"},
            ],
        })
        assert "could not be parsed" in output

    def test_case_trust_warn_renders(self):
        output = templates.case_trust_warn({"score": 0.45, "factors": {"cve": "3 open"}})
        assert "Low Trust" in output

    def test_case_trust_degraded_renders(self):
        output = templates.case_trust_degraded({
            "tool_name": "Test",
            "tool_id": "test-id",
            "score_at_install": 0.91,
            "current_score": 0.50,
            "last_evaluated": "2024-01-15",
            "changes": {"cve": "0 → 2"},
        })
        assert "Trust Degraded" in output
        assert "Last checked" in output

    def test_case_llm_unknown_renders(self):
        output = templates.case_llm_unknown({
            "tool_name": "Tool",
            "new_tool_name": "New",
            "new_confidence": "missing",
            "existing_tool_name": "Old",
            "existing_confidence": "auto",
        })
        assert "Cannot Auto-Compare" in output

    def test_case_llm_overlap_renders(self):
        output = templates.case_llm_overlap({
            "combined_score": 0.92,
            "shared_behaviors": ["Drafts text"],
            "new_only_behaviors": ["Formats markdown"],
        })
        assert "LLM Behavioral Overlap" in output


class TestPromptEngine:
    """Test the prompt engine dispatch."""

    def setup_method(self):
        self.engine = PromptEngine()

    def test_render_known_case(self):
        prompt = self.engine.render("CASE_1", {"trust_score": 0.9})
        assert isinstance(prompt, str)
        assert len(prompt) > 0

    def test_render_unknown_case(self):
        with pytest.raises(ValueError, match="Unknown WG case"):
            self.engine.render("CASE_NONEXISTENT", {})

    def test_get_options(self):
        opts = self.engine.get_options("CASE_1")
        assert len(opts) >= 2

    def test_render_full(self):
        prompt, options = self.engine.render_full("CASE_4", {})
        assert "Exact duplicate" in prompt
        assert len(options) == 2

    def test_prompt_engine_truncates_long_prompts(self):
        engine = PromptEngine(max_chars=420)
        prompt = engine.render("CASE_5", {
            "shared": [f"shared-{i}" for i in range(20)],
            "d_only": [f"d-{i}" for i in range(20)],
            "x_only": [f"x-{i}" for i in range(20)],
        })
        assert len(prompt) <= 470
        assert "(+15 more)" in prompt

    def test_all_template_keys_valid(self):
        """Every key in TEMPLATES should render and return options."""
        for key in templates.TEMPLATES:
            prompt = self.engine.render(key, {})
            assert isinstance(prompt, str)
            opts = self.engine.get_options(key)
            assert len(opts) >= 2
