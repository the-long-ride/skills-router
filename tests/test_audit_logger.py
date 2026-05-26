"""Tests for Audit Logger."""

import os
import pytest
from skills_router.audit.logger import AuditLogger
from skills_router.models.audit_log import AuditEntry


class TestAuditLogger:
    """Test log write and query operations."""

    @pytest.fixture
    def logger(self, tmp_path):
        path = str(tmp_path / "audit.jsonl")
        return AuditLogger(log_path=path)

    def test_log_and_query(self, logger):
        """Log an entry and query it back."""
        entry = AuditEntry(
            user_id="user-1",
            tool_id="tool-a",
            tool_version="1.0.0",
            wg_case="CASE_1",
            decision="APPROVE",
            install_scope="global",
            trust_score_at_install=0.85,
        )
        logger.log(entry)
        results = logger.query(tool_id="tool-a")
        assert len(results) == 1
        assert results[0]["tool_id"] == "tool-a"
        assert results[0]["wg_case"] == "CASE_1"

    def test_query_by_user(self, logger):
        """Query should filter by user_id."""
        logger.log(AuditEntry(user_id="alice", tool_id="t1", wg_case="CASE_1", decision="APPROVE"))
        logger.log(AuditEntry(user_id="bob", tool_id="t2", wg_case="CASE_2", decision="CANCEL"))

        alice_entries = logger.query(user_id="alice")
        assert len(alice_entries) == 1
        assert alice_entries[0]["user_id"] == "alice"

    def test_query_by_wg_case(self, logger):
        """Query should filter by wg_case."""
        logger.log(AuditEntry(tool_id="t1", wg_case="CASE_1", decision="APPROVE"))
        logger.log(AuditEntry(tool_id="t2", wg_case="CASE_TRUST_DEGRADED", decision="CANCEL"))

        results = logger.query(wg_case="CASE_TRUST_DEGRADED")
        assert len(results) == 1
        assert results[0]["wg_case"] == "CASE_TRUST_DEGRADED"

    def test_query_limit(self, logger):
        """Query should respect limit."""
        for i in range(10):
            logger.log(AuditEntry(tool_id=f"t-{i}", wg_case="CASE_1", decision="APPROVE"))
        results = logger.query(limit=3)
        assert len(results) == 3

    def test_query_empty_log(self, logger):
        """Query on empty log should return empty list."""
        results = logger.query()
        assert results == []

    def test_log_dict(self, logger):
        """log_dict should create an entry from a raw dict."""
        logger.log_dict({
            "user_id": "test",
            "tool_id": "tool-x",
            "wg_case": "CASE_DEP",
            "decision": "CANCEL",
        })
        results = logger.query(tool_id="tool-x")
        assert len(results) == 1

    def test_clear(self, logger):
        """clear should remove all entries."""
        logger.log(AuditEntry(tool_id="t1", wg_case="CASE_1", decision="APPROVE"))
        logger.clear()
        results = logger.query()
        assert results == []

    def test_audit_entry_auto_fields(self):
        """AuditEntry should auto-generate event_id and timestamp."""
        entry = AuditEntry(tool_id="test")
        assert entry.event_id  # not empty
        assert entry.timestamp  # not empty
        assert "-" in entry.event_id  # UUID format
