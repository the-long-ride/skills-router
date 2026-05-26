"""Tests for Layer 2 — SemanticEvaluator."""

import numpy as np
import pytest
from skills_router.layers.semantic_evaluator import SemanticEvaluator, _stable_seed


class TestSemanticEvaluator:
    """Test embedding, cosine similarity, and overlap detection."""

    def setup_method(self):
        self.evaluator = SemanticEvaluator()  # Uses random fallback (no model)

    def test_deterministic_seed(self):
        """v5: Same tool_id should produce identical embeddings across calls."""
        vec1 = self.evaluator.embed("test text", tool_id="my-tool")
        vec2 = self.evaluator.embed("test text", tool_id="my-tool")
        np.testing.assert_array_equal(vec1, vec2)

    def test_different_tool_ids_differ(self):
        """Different tool_ids should produce different embeddings."""
        vec1 = self.evaluator.embed("test text", tool_id="tool-a")
        vec2 = self.evaluator.embed("test text", tool_id="tool-b")
        assert not np.array_equal(vec1, vec2)

    def test_seed_value_is_stable(self):
        """Fallback seed should not depend on Python's per-process hash salt."""
        assert _stable_seed("my-tool") == _stable_seed("my-tool")
        assert _stable_seed("my-tool") != _stable_seed("other-tool")

    def test_embedding_dimension(self):
        """Embeddings should be 384-dimensional."""
        vec = self.evaluator.embed("hello", tool_id="test")
        assert vec.shape == (384,)

    def test_cosine_identical_vectors(self):
        """Cosine similarity of identical vectors should be 1.0."""
        vec = np.array([1.0, 2.0, 3.0])
        assert self.evaluator.cosine(vec, vec) == pytest.approx(1.0)

    def test_cosine_orthogonal_vectors(self):
        """Cosine similarity of orthogonal vectors should be 0.0."""
        a = np.array([1.0, 0.0])
        b = np.array([0.0, 1.0])
        assert self.evaluator.cosine(a, b) == pytest.approx(0.0)

    def test_cosine_zero_vector(self):
        """Cosine with zero vector should be 0.0."""
        a = np.array([1.0, 2.0])
        b = np.zeros(2)
        assert self.evaluator.cosine(a, b) == 0.0

    def test_create_signature(self):
        """Signature should include tool name, domain, inputs, outputs."""
        tool = {
            "name": "TestTool",
            "layer_1_domain_tags": ["Weather", "API"],
            "layer_3_capabilities": {
                "inputs": ["zipcode: string"],
                "outputs": ["temp: float"],
            },
        }
        sig = self.evaluator.create_signature(tool)
        assert "TestTool" in sig
        assert "Weather" in sig
        assert "zipcode" in sig
        assert "temp" in sig

    def test_evaluate_brand_new(self):
        """Tool with no existing matches → BRAND_NEW_SCOPE."""
        new_tool = {
            "tool_id": "new-tool",
            "name": "New Tool",
            "layer_1_domain_tags": ["Unique"],
            "layer_3_capabilities": {"inputs": ["x"], "outputs": ["y"]},
        }
        result = self.evaluator.evaluate(new_tool, scope="global", brain_index=[])
        assert result["status"] == "BRAND_NEW_SCOPE"
        assert result["action"] == "PROCEED_TO_CASE_1"

    def test_evaluate_self_excluded(self):
        """Same tool_id in brain_index should be excluded from results."""
        tool = {
            "tool_id": "tool-a",
            "name": "Tool A",
            "layer_1_domain_tags": ["Test"],
            "layer_3_capabilities": {"inputs": ["a"], "outputs": ["b"]},
        }
        result = self.evaluator.evaluate(tool, scope="global", brain_index=[tool])
        # Self excluded → no matches
        assert result["status"] == "BRAND_NEW_SCOPE"
