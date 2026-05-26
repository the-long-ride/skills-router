"""Skills Router lockfile support.

The lockfile records the exact manifest source used for an installed tool so
local agents can reproduce installs across workspaces.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class SkillsRouterLockfile:
    """Read and write ``skills-router.lock.json``."""

    def __init__(self, path: str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def upsert(self, tool_record: dict[str, Any], requested: str, scope: str) -> None:
        """Record an installed tool and its resolved source."""
        data = self.read()
        tools = data.setdefault("tools", {})
        tool_id = tool_record["tool_id"]
        meta = tool_record.get("layer_meta", {})
        tools[tool_id] = {
            "tool_id": tool_id,
            "name": tool_record.get("name", ""),
            "version": tool_record.get("version", ""),
            "requested": requested,
            "scope": scope,
            "resolved_source": meta.get("resolved_source", "local"),
            "resolved_identifier": meta.get("resolved_identifier", requested),
            "resolved_version": meta.get("resolved_version", tool_record.get("version", "")),
            "resolved_url": meta.get("resolved_url", ""),
            "resolved_sha256": meta.get("resolved_sha256", ""),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        self.write(data)

    def remove(self, tool_id: str) -> None:
        data = self.read()
        tools = data.setdefault("tools", {})
        if tool_id in tools:
            del tools[tool_id]
            self.write(data)

    def read(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"version": 1, "tools": {}}
        with open(self.path, encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return {"version": 1, "tools": {}}
        data.setdefault("version", 1)
        data.setdefault("tools", {})
        return data

    def write(self, data: dict[str, Any]) -> None:
        tmp_path = self.path.with_name(f".{self.path.name}.tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, sort_keys=True)
        try:
            os.replace(tmp_path, self.path)
        except PermissionError:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, sort_keys=True)
            try:
                tmp_path.unlink()
            except OSError:
                pass
