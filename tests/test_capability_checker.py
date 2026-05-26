"""Tests for Layer 3 — CapabilityChecker."""

import numpy as np
import pytest
from skills_router.layers.capability_checker import CapabilityChecker


class TestCapabilityChecker:
    """Test all 7 case outputs."""

    def setup_method(self):
        self.checker = CapabilityChecker()

    def test_case_4_exact_match(self):
        """Identical capability sets → CASE_4_EXACT_MATCH."""
        new = {"capabilities": {"inputs": ["a"], "outputs": ["b"], "permissions": ["c"]}}
        existing = {"capabilities": {"inputs": ["a"], "outputs": ["b"], "permissions": ["c"]}}
        result = self.checker.determine_relationship(new, existing)
        assert result["case"] == "CASE_4_EXACT_MATCH"

    def test_case_2_partial_overlap(self):
        """New tool is superset → CASE_2_PARTIAL_OVERLAP."""
        new = {"capabilities": {"inputs": ["a", "x"], "outputs": ["b"], "permissions": ["c"]}}
        existing = {"capabilities": {"inputs": ["a"], "outputs": ["b"], "permissions": ["c"]}}
        result = self.checker.determine_relationship(new, existing)
        assert result["case"] == "CASE_2_PARTIAL_OVERLAP"
        assert "x" in result["new_features_in_d"]

    def test_case_3_parent_child(self):
        """New tool is subset → CASE_3_PARENT_CHILD."""
        new = {"capabilities": {"inputs": ["a"], "outputs": ["b"], "permissions": []}}
        existing = {"capabilities": {"inputs": ["a"], "outputs": ["b"], "permissions": ["c"]}}
        result = self.checker.determine_relationship(new, existing)
        assert result["case"] == "CASE_3_PARENT_CHILD"
        assert "c" in result["features_missing_in_d"]

    def test_case_5_tangential(self):
        """Partial intersection → CASE_5_TANGENTIAL."""
        new = {"capabilities": {"inputs": ["a", "x"], "outputs": [], "permissions": []}}
        existing = {"capabilities": {"inputs": ["a", "y"], "outputs": [], "permissions": []}}
        result = self.checker.determine_relationship(new, existing)
        assert result["case"] == "CASE_5_TANGENTIAL"
        assert "a" in result["shared"]
        assert "x" in result["d_only"]
        assert "y" in result["x_only"]

    def test_case_llm_unknown_no_embedding(self):
        """LLM tool with missing embedding → CASE_LLM_UNKNOWN."""
        new = {
            "tool_type": "llm_powered",
            "behavior_spec": {"behavioral_embedding": [], "declared_behaviors": []},
        }
        existing = {
            "tool_type": "api_wrapper",
            "behavior_spec": {"behavioral_embedding": [], "declared_behaviors": []},
        }
        result = self.checker.determine_relationship(new, existing)
        assert result["case"] == "CASE_LLM_UNKNOWN"

    def test_case_llm_overlap(self):
        """LLM tools with high behavioral similarity → CASE_LLM_OVERLAP."""
        vec = np.random.default_rng(42).random(384).tolist()
        behaviors = ["Does thing A", "Does thing B"]
        new = {
            "tool_type": "llm_powered",
            "behavior_spec": {
                "behavioral_embedding": vec,
                "declared_behaviors": behaviors,
                "embedding_confidence": "verified",
            },
        }
        existing = {
            "tool_type": "llm_powered",
            "behavior_spec": {
                "behavioral_embedding": vec,  # identical embedding
                "declared_behaviors": behaviors,
                "embedding_confidence": "verified",
            },
        }
        result = self.checker.determine_relationship(new, existing)
        assert result["case"] == "CASE_LLM_OVERLAP"
        assert result["combined_score"] >= 0.82

    def test_case_llm_distinct(self):
        """LLM tools with low similarity → CASE_LLM_DISTINCT."""
        rng = np.random.default_rng(42)
        new = {
            "tool_type": "llm_powered",
            "behavior_spec": {
                "behavioral_embedding": rng.random(384).tolist(),
                "declared_behaviors": ["Writes poetry"],
                "embedding_confidence": "verified",
            },
        }
        rng2 = np.random.default_rng(99)
        existing = {
            "tool_type": "llm_powered",
            "behavior_spec": {
                "behavioral_embedding": rng2.random(384).tolist(),
                "declared_behaviors": ["Analyzes stocks"],
                "embedding_confidence": "verified",
            },
        }
        result = self.checker.determine_relationship(new, existing)
        assert result["case"] == "CASE_LLM_DISTINCT"

    def test_llm_tool_type_from_layer_6_behavior_spec(self):
        """layer_6 tool_type should trigger LLM guard even without top-level tool_type."""
        new = {
            "layer_6_behavior_spec": {
                "tool_type": "llm_powered",
                "behavioral_embedding": [0.1, 0.2],
                "declared_behaviors": ["Drafts replies"],
                "embedding_confidence": "auto",
            },
        }
        existing = {"layer_6_behavior_spec": {"tool_type": "api_wrapper"}}
        result = self.checker.determine_relationship(new, existing)
        assert result["case"] == "CASE_LLM_UNKNOWN"

    def test_empty_capabilities(self):
        """Tools with empty capabilities → CASE_4 (both are empty sets)."""
        new = {"capabilities": {"inputs": [], "outputs": [], "permissions": []}}
        existing = {"capabilities": {"inputs": [], "outputs": [], "permissions": []}}
        result = self.checker.determine_relationship(new, existing)
        assert result["case"] == "CASE_4_EXACT_MATCH"
