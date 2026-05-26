"""Audit log entry model — matches blueprint §9 schema (v5)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class AuditEntry:
    """A single audit log record.

    ``wg_case`` uses the full v5 enum including ``CASE_TRUST_DEGRADED``.
    """

    user_id: str = ""
    tool_id: str = ""
    tool_version: str = ""
    wg_case: str = ""          # WGCase enum value
    decision: str = ""         # WGDecision enum value
    reason: str | None = None
    install_scope: str = ""    # e.g. "global", "workspace:ws-42"
    trust_score_at_install: float = 0.0

    # Auto-generated
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict:
        """Serialize to a JSON-compatible dict."""
        return {
            "event_id": self.event_id,
            "timestamp": self.timestamp,
            "user_id": self.user_id,
            "tool_id": self.tool_id,
            "tool_version": self.tool_version,
            "wg_case": self.wg_case,
            "decision": self.decision,
            "reason": self.reason,
            "install_scope": self.install_scope,
            "trust_score_at_install": self.trust_score_at_install,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "AuditEntry":
        """Create an AuditEntry from a dict (e.g., loaded from JSON)."""
        return cls(
            event_id=data.get("event_id", str(uuid.uuid4())),
            timestamp=data.get("timestamp", datetime.now(timezone.utc).isoformat()),
            user_id=data.get("user_id", ""),
            tool_id=data.get("tool_id", ""),
            tool_version=data.get("tool_version", ""),
            wg_case=data.get("wg_case", ""),
            decision=data.get("decision", ""),
            reason=data.get("reason"),
            install_scope=data.get("install_scope", ""),
            trust_score_at_install=data.get("trust_score_at_install", 0.0),
        )
