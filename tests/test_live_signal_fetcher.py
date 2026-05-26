"""Tests for LiveSignalFetcher and CircuitBreaker."""

import time
import pytest
from skills_router.daemon.live_signal_fetcher import CircuitBreaker, LiveSignalFetcher


class TestCircuitBreaker:
    """Test circuit breaker state transitions."""

    def test_starts_closed(self):
        cb = CircuitBreaker(failure_threshold=3)
        assert not cb.is_open

    def test_opens_after_threshold(self):
        cb = CircuitBreaker(failure_threshold=2, reset_seconds=300)
        cb.record_failure()
        assert not cb.is_open
        cb.record_failure()
        assert cb.is_open

    def test_success_resets(self):
        cb = CircuitBreaker(failure_threshold=2)
        cb.record_failure()
        cb.record_failure()
        assert cb.is_open
        # Can't directly reset while open until reset_seconds pass
        # But after reset_seconds, is_open resets failures (half-open)

    def test_half_open_after_timeout(self):
        cb = CircuitBreaker(failure_threshold=1, reset_seconds=0)
        cb.record_failure()
        # reset_seconds=0 → immediately half-open
        time.sleep(0.01)
        assert not cb.is_open  # half-open: failures reset
        assert cb.failure_count == 0

    def test_record_success_clears(self):
        cb = CircuitBreaker(failure_threshold=3)
        cb.record_failure()
        cb.record_failure()
        cb.record_success()
        assert cb.failure_count == 0
        assert not cb.is_open


class TestLiveSignalFetcher:
    """Test the fetcher with default stubs."""

    def setup_method(self):
        self.fetcher = LiveSignalFetcher()

    def test_fetch_returns_valid_manifest(self):
        tool = {
            "tool_id": "test-tool",
            "layer_5_provenance": {
                "signature_verified": True,
                "install_source": "official-registry",
                "publisher_id": "pub-1",
            },
        }
        result = self.fetcher.fetch(tool)
        assert result["publisher_signature"]["verified"] is True
        assert result["install_source"] == "official-registry"
        assert isinstance(result["open_critical_cves"], int)
        assert isinstance(result["last_commit_days_ago"], int)
        assert isinstance(result["community_sentiment_score"], float)

    def test_circuit_opens_on_repeated_failures(self):
        """Force failures and verify circuit opens."""

        class FailingFetcher(LiveSignalFetcher):
            def _fetch_cve_count(self, tool_id):
                raise ConnectionError("API down")

        fetcher = FailingFetcher()
        fetcher.BACKOFF_BASE = 0  # no delay in tests
        tool = {"tool_id": "t", "layer_5_provenance": {}}
        result = fetcher.fetch(tool)
        # Should have fallen back to default after retries
        assert result["open_critical_cves"] == 1
        # Circuit should now be open
        assert fetcher._cb["cve"].is_open

    def test_defaults_on_missing_provenance(self):
        """Missing provenance should use safe defaults."""
        result = self.fetcher.fetch({"tool_id": "t"})
        assert result["publisher_signature"]["verified"] is False
        assert result["install_source"] == "unknown"
