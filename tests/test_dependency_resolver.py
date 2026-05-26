"""Tests for Layer 1.5 — DependencyConflictResolver."""

import pytest
from skills_router.layers.dependency_resolver import DependencyConflictResolver


class TestDependencyConflictResolver:
    """Test CONFLICT_FOUND, CLEAN, and parse_errors paths."""

    def setup_method(self):
        self.resolver = DependencyConflictResolver()

    def test_clean_no_overlap(self):
        """No overlapping packages → CLEAN."""
        new_tool = {"dependencies": {"pandas": ">=1.3.0"}}
        dep_graph = {
            "requests": {"locked_version": "2.28.0", "required_by": ["tool-a"]},
        }
        result = self.resolver.resolve(new_tool, dep_graph)
        assert result["status"] == "CLEAN"
        assert result["action"] == "PROCEED_TO_EMBEDDER"

    def test_clean_compatible_version(self):
        """Overlapping package but compatible version → CLEAN."""
        new_tool = {"dependencies": {"requests": ">=2.25.0"}}
        dep_graph = {
            "requests": {"locked_version": "2.28.0", "required_by": ["tool-a"]},
        }
        result = self.resolver.resolve(new_tool, dep_graph)
        assert result["status"] == "CLEAN"

    def test_hard_conflict(self):
        """Incompatible version → CONFLICT_FOUND."""
        new_tool = {"dependencies": {"numpy": "==1.19.0"}}
        dep_graph = {
            "numpy": {"locked_version": "1.21.0", "required_by": ["tool-a"]},
        }
        result = self.resolver.resolve(new_tool, dep_graph)
        assert result["status"] == "CONFLICT_FOUND"
        assert result["action"] == "ROUTE_TO_DEP_WG"
        assert len(result["hard_conflicts"]) == 1
        assert result["hard_conflicts"][0]["package"] == "numpy"
        assert result["hard_conflicts"][0]["severity"] == "HARD"

    def test_soft_warning_not_pinned_identically(self):
        """Compatible but not pinned identically → soft warning."""
        new_tool = {"dependencies": {"requests": ">=2.25.0"}}
        dep_graph = {
            "requests": {"locked_version": "2.28.0", "required_by": ["tool-a"]},
        }
        result = self.resolver.resolve(new_tool, dep_graph)
        assert result["status"] == "CLEAN"
        assert len(result["soft_warnings"]) == 1
        assert result["soft_warnings"][0]["severity"] == "SOFT"

    def test_parse_errors_surfaced(self):
        """Unparseable specifiers → parse_errors list (v5)."""
        new_tool = {"dependencies": {"bad-pkg": "not_a_valid_spec!!!"}}
        dep_graph = {
            "bad-pkg": {"locked_version": "1.0.0", "required_by": ["tool-a"]},
        }
        result = self.resolver.resolve(new_tool, dep_graph)
        assert result["status"] == "PARSE_ERROR"
        assert result["action"] == "ROUTE_TO_DEP_WG"
        assert len(result["parse_errors"]) == 1
        assert result["parse_errors"][0]["package"] == "bad-pkg"

    def test_parse_errors_for_new_dependency_also_route_to_review(self):
        """Invalid specs should be reviewed even when the package is not installed yet."""
        new_tool = {"dependencies": {"new-bad-pkg": "not_a_valid_spec!!!"}}
        result = self.resolver.resolve(new_tool, {})
        assert result["status"] == "PARSE_ERROR"
        assert result["parse_errors"][0]["package"] == "new-bad-pkg"

    def test_empty_dependencies(self):
        """Tool with no deps → CLEAN."""
        result = self.resolver.resolve({"dependencies": {}}, {"numpy": {"locked_version": "1.0", "required_by": []}})
        assert result["status"] == "CLEAN"

    def test_multiple_conflicts(self):
        """Multiple conflicting packages."""
        new_tool = {"dependencies": {
            "numpy": "==1.19.0",
            "pandas": "==0.25.0",
        }}
        dep_graph = {
            "numpy": {"locked_version": "1.21.0", "required_by": ["tool-a"]},
            "pandas": {"locked_version": "1.3.0", "required_by": ["tool-b"]},
        }
        result = self.resolver.resolve(new_tool, dep_graph)
        assert result["status"] == "CONFLICT_FOUND"
        assert len(result["hard_conflicts"]) == 2
