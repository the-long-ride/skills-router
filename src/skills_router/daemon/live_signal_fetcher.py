"""LiveSignalFetcher — New in v5.

Direct implementation of blueprint §12.  Per-source circuit breaker with
exponential-backoff retry.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class CircuitBreaker:
    """Per-source circuit breaker.

    Opens after ``failure_threshold`` consecutive failures.
    Resets (half-open) after ``reset_seconds``.
    """

    failure_threshold: int = 3
    reset_seconds: int = 300
    _failures: int = field(default=0, init=False, repr=False)
    _opened_at: float = field(default=0.0, init=False, repr=False)

    @property
    def is_open(self) -> bool:
        if self._failures >= self.failure_threshold:
            if time.monotonic() - self._opened_at < self.reset_seconds:
                return True
            # Half-open: allow one probe
            self._failures = 0
        return False

    def record_failure(self) -> None:
        self._failures += 1
        self._opened_at = time.monotonic()

    def record_success(self) -> None:
        self._failures = 0

    @property
    def failure_count(self) -> int:
        return self._failures


class LiveSignalFetcher:
    """Fetches live trust signals with circuit breakers and backoff retry.

    Concrete implementations override the ``_fetch_*`` methods;
    stubs are provided for MVP.
    """

    MAX_RETRIES = 3
    BACKOFF_BASE = 2  # seconds; delay = BACKOFF_BASE ** attempt

    def __init__(
        self,
        max_retries: int | None = None,
        backoff_base: int | None = None,
        failure_threshold: int = 3,
        reset_seconds: int = 300,
    ):
        self.max_retries = max(1, max_retries or self.MAX_RETRIES)
        self.backoff_base = max(1, backoff_base or self.BACKOFF_BASE)
        self._cb: dict[str, CircuitBreaker] = {
            "cve": CircuitBreaker(failure_threshold=failure_threshold, reset_seconds=reset_seconds),
            "commit": CircuitBreaker(failure_threshold=failure_threshold, reset_seconds=reset_seconds),
            "sentiment": CircuitBreaker(failure_threshold=failure_threshold, reset_seconds=reset_seconds),
        }

    def fetch(self, tool: dict) -> dict:
        """Fetch live trust signals for a tool.

        Returns a dict in the format expected by ``TrustGate.evaluate()``.
        """
        prov = tool.get("layer_5_provenance", {})
        return {
            "publisher_signature": {
                "verified": prov.get("signature_verified", False),
            },
            "install_source": prov.get("install_source", "unknown"),
            "open_critical_cves": self._safe_fetch(
                "cve", self._fetch_cve_count, tool.get("tool_id", "")
            ),
            "last_commit_days_ago": self._safe_fetch(
                "commit", self._fetch_commit_age, prov.get("publisher_id", "")
            ),
            "community_sentiment_score": self._safe_fetch(
                "sentiment", self._fetch_sentiment, tool.get("tool_id", "")
            ),
        }

    def _safe_fetch(self, source: str, fn, *args):
        """Wrap a fetch call with circuit breaker and backoff."""
        cb = self._cb[source]
        if cb.is_open:
            logger.warning(
                "Circuit open for source=%s; skipping fetch", source
            )
            return self._default(source)

        for attempt in range(self.max_retries):
            try:
                result = fn(*args)
                cb.record_success()
                return result
            except Exception as exc:
                cb.record_failure()
                logger.warning(
                    "Fetch failed source=%s attempt=%d: %s",
                    source, attempt, exc,
                )
                if attempt < self.max_retries - 1:
                    time.sleep(self.backoff_base ** attempt)

        return self._default(source)

    def _default(self, source: str):
        """Return conservative defaults when fetches fail."""
        return {"cve": 1, "commit": 999, "sentiment": 0.0}.get(source, None)

    # -- Override in production -----------------------------------------------

    def _fetch_cve_count(self, tool_id: str) -> int:
        """Stub: returns 0. Override with real CVE API."""
        return 0

    def _fetch_commit_age(self, pub_id: str) -> int:
        """Stub: returns 0. Override with real GitHub/Git API."""
        return 0

    def _fetch_sentiment(self, tool_id: str) -> float:
        """Stub: returns 0.8. Override with real sentiment scraper."""
        return 0.8
