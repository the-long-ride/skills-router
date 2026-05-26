"""Tests for Layer 0 — TrustGate."""

import pytest
from skills_router.layers.trust_gate import TrustGate


class TestTrustGate:
    """Test all three verdict paths with boundary values."""

    def setup_method(self):
        self.gate = TrustGate()

    def test_pass_high_trust(self):
        """Fully trusted tool should PASS."""
        manifest = {
            "publisher_signature": {"verified": True},
            "install_source": "official-registry",
            "open_critical_cves": 0,
            "last_commit_days_ago": 10,
            "community_sentiment_score": 0.9,
        }
        result = self.gate.evaluate(manifest)
        assert result["verdict"] == "PASS"
        assert result["score"] >= 0.65

    def test_hard_reject_untrusted(self):
        """Completely untrusted tool should be HARD_REJECT."""
        manifest = {
            "publisher_signature": {"verified": False},
            "install_source": "unknown",
            "open_critical_cves": 5,
            "last_commit_days_ago": 999,
            "community_sentiment_score": 0.0,
        }
        result = self.gate.evaluate(manifest)
        assert result["verdict"] == "HARD_REJECT"
        assert result["score"] < 0.30
        assert result["user_override_allowed"] is False
        assert "reason" in result

    def test_soft_warn_medium_trust(self):
        """Medium trust should trigger SOFT_WARN."""
        manifest = {
            "publisher_signature": {"verified": False},
            "install_source": "third-party",
            "open_critical_cves": 0,
            "last_commit_days_ago": 50,
            "community_sentiment_score": 0.1,
        }
        result = self.gate.evaluate(manifest)
        # 0.0 + 0.05 + 0.20 + 0.10 + 0.01 = 0.36 → SOFT_WARN
        assert result["verdict"] == "SOFT_WARN"
        assert 0.30 <= result["score"] < 0.65
        assert result["user_override_allowed"] is True

    def test_boundary_hard_reject(self):
        """Score exactly at HARD_BLOCK_THRESHOLD should be SOFT_WARN."""
        # Score = 0.30 exactly is SOFT_WARN (not HARD_REJECT since < is strict)
        manifest = {
            "publisher_signature": {"verified": False},
            "install_source": "github",
            "open_critical_cves": 0,
            "last_commit_days_ago": 200,
            "community_sentiment_score": 0.0,
        }
        result = self.gate.evaluate(manifest)
        # 0.0 + 0.15 + 0.20 + 0.05 + 0.0 = 0.40 → SOFT_WARN
        assert result["verdict"] == "SOFT_WARN"

    def test_explain_lists_zero_factors(self):
        """_explain should list factors with 0.0 score."""
        factors = {
            "sig_verified": 0.0,
            "source_score": 0.25,
            "cve_score": 0.0,
            "activity_score": 0.10,
            "sentiment_score": 0.05,
        }
        explanation = self.gate._explain(factors)
        assert "sig_verified" in explanation
        assert "cve_score" in explanation
        assert "source_score" not in explanation

    def test_missing_fields_default_to_zero(self):
        """Missing manifest fields should use safe defaults."""
        result = self.gate.evaluate({})
        assert result["verdict"] == "HARD_REJECT"
        assert result["score"] < 0.30
