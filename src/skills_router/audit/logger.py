"""Audit log writer — JSON Lines file backend.

Records all WG decisions for compliance and history queries.
"""

from __future__ import annotations

import json
import os
from typing import Any

from skills_router.models.audit_log import AuditEntry


class AuditLogger:
    """Append-only audit logger backed by a JSON Lines file."""

    def __init__(self, log_path: str):
        self.log_path = log_path
        os.makedirs(os.path.dirname(log_path), exist_ok=True)

    def log(self, entry: AuditEntry) -> None:
        """Append an audit entry to the log file."""
        with open(self.log_path, "a") as f:
            f.write(json.dumps(entry.to_dict()) + "\n")

    def log_dict(self, data: dict) -> None:
        """Create and log an AuditEntry from a raw dict."""
        entry = AuditEntry.from_dict(data)
        self.log(entry)

    def query(
        self,
        tool_id: str | None = None,
        user_id: str | None = None,
        wg_case: str | None = None,
        limit: int = 100,
    ) -> list[dict]:
        """Query the audit log with optional filters.

        Returns most recent entries first.
        """
        if not os.path.exists(self.log_path):
            return []

        entries: list[dict] = []
        with open(self.log_path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue

                if tool_id and entry.get("tool_id") != tool_id:
                    continue
                if user_id and entry.get("user_id") != user_id:
                    continue
                if wg_case and entry.get("wg_case") != wg_case:
                    continue

                entries.append(entry)

        # Most recent first
        entries.reverse()
        return entries[:limit]

    def get_all(self) -> list[dict]:
        """Return all audit entries."""
        return self.query(limit=999999)

    def clear(self) -> None:
        """Clear the audit log (mainly for testing)."""
        if os.path.exists(self.log_path):
            try:
                os.remove(self.log_path)
            except PermissionError:
                with open(self.log_path, "w", encoding="utf-8"):
                    pass
