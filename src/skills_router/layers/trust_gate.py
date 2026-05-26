"""Layer 0 — Trust Gate.

Direct implementation of blueprint §4.  Evaluates a tool manifest's
trust factors and returns HARD_REJECT, SOFT_WARN, or PASS.
"""

from __future__ import annotations


class TrustGate:
    """Multi-factor trust scorer for tool manifests."""

    HARD_BLOCK_THRESHOLD = 0.30
    SOFT_WARN_THRESHOLD = 0.65

    def __init__(
        self,
        hard_block_threshold: float | None = None,
        soft_warn_threshold: float | None = None,
    ):
        if hard_block_threshold is not None:
            self.HARD_BLOCK_THRESHOLD = hard_block_threshold
        if soft_warn_threshold is not None:
            self.SOFT_WARN_THRESHOLD = soft_warn_threshold

    def evaluate(self, tool_manifest: dict) -> dict:
        """Score a manifest and return a verdict dict.

        Returns:
            {
                "verdict": "HARD_REJECT" | "SOFT_WARN" | "PASS",
                "score": float,
                "reason": str | None,      # only on non-PASS
                "user_override_allowed": bool | None,
            }
        """
        score, factors = self._calculate_trust(tool_manifest)

        if score < self.HARD_BLOCK_THRESHOLD:
            return {
                "verdict": "HARD_REJECT",
                "score": score,
                "factors": factors,
                "issues": self._issue_details(factors),
                "reason": self._explain(factors),
                "user_override_allowed": False,
            }
        elif score < self.SOFT_WARN_THRESHOLD:
            return {
                "verdict": "SOFT_WARN",
                "score": score,
                "factors": factors,
                "issues": self._issue_details(factors),
                "reason": self._explain(factors),
                "user_override_allowed": True,
            }
        else:
            return {"verdict": "PASS", "score": score, "factors": factors, "issues": {}}

    def _calculate_trust(self, manifest: dict) -> tuple[float, dict]:
        """Compute trust score from five weighted factors."""
        factors: dict[str, float] = {}

        # Factor 1: Publisher signature verification (max 0.35)
        sig = manifest.get("publisher_signature", {})
        factors["sig_verified"] = 0.35 if sig.get("verified") else 0.0

        # Factor 2: Install source reputation (max 0.25)
        src = manifest.get("install_source", "unknown")
        factors["source_score"] = {
            "official-registry": 0.25,
            "github": 0.15,
            "third-party": 0.05,
            "unknown": 0.0,
        }.get(src, 0.0)

        # Factor 3: CVE status (max 0.20)
        cves = _coerce_int(manifest.get("open_critical_cves", 0), default=999)
        factors["cve_score"] = 0.20 if cves == 0 else 0.0

        # Factor 4: Development activity (max 0.10)
        days = _coerce_int(manifest.get("last_commit_days_ago", 999), default=999)
        factors["activity_score"] = (
            0.10 if days < 90 else (0.05 if days < 365 else 0.0)
        )

        # Factor 5: Community sentiment (max 0.10)
        sentiment = min(
            max(
                _coerce_float(
                    manifest.get("community_sentiment_score", 0.5),
                    default=0.0,
                ),
                0.0,
            ),
            1.0,
        )
        factors["sentiment_score"] = round(sentiment * 0.10, 3)

        total = round(sum(factors.values()), 3)
        return total, factors

    def _explain(self, factors: dict) -> str:
        """Generate human-readable explanation of trust failures."""
        issues = [k for k, v in factors.items() if v == 0.0]
        return f"Trust failures: {', '.join(issues)}"

    def _issue_details(self, factors: dict) -> dict[str, str]:
        """Return concise, human-facing issue labels for zero-scoring factors."""
        labels = {
            "sig_verified": "Publisher signature is not verified",
            "source_score": "Install source has low or unknown reputation",
            "cve_score": "One or more critical CVEs are open",
            "activity_score": "Project activity is stale or unknown",
            "sentiment_score": "Community sentiment is very low or unavailable",
        }
        return {key: labels[key] for key, value in factors.items() if value == 0.0}


def _coerce_int(value, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _coerce_float(value, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
