"""pgvector Brain Index store.

Optional PostgreSQL/pgvector implementation for larger registries. The default
local backend remains ``MemoryBrainIndexStore``.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import numpy as np

from skills_router.storage.base import AbstractBrainIndexStore


class PgVectorBrainIndexStore(AbstractBrainIndexStore):
    """pgvector-backed Brain Index store."""

    def __init__(self, dsn: str, connect=None):
        if not dsn:
            raise ValueError("pgvector backend requires pgvector_dsn")
        if connect is None:
            try:
                import psycopg2
            except ImportError as exc:
                raise RuntimeError(
                    "pgvector backend requires the 'psycopg2-binary' package. "
                    "Install with: pip install -e '.[pgvector]'"
                ) from exc
            connect = psycopg2.connect

        self.dsn = dsn
        self.conn = connect(dsn)
        self.conn.autocommit = True
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        with self.conn.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS brain_index (
                    tool_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    version TEXT NOT NULL,
                    install_scope TEXT NOT NULL,
                    agent_id TEXT,
                    metadata JSONB NOT NULL,
                    capability_vec vector(384),
                    behavior_vec vector(384),
                    installed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS brain_index_capability_vec_idx
                ON brain_index USING ivfflat (capability_vec vector_cosine_ops)
                WITH (lists = 100)
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS dep_graph_state (
                    id BOOLEAN PRIMARY KEY DEFAULT TRUE,
                    graph JSONB NOT NULL,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    CONSTRAINT dep_graph_state_singleton CHECK (id)
                )
                """
            )

    def save_tool(self, tool_record: dict) -> None:
        meta = tool_record.get("layer_meta", {})
        vec = _vector_literal(tool_record.get("layer_2_vector_signature"))
        with self.conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO brain_index (
                    tool_id, name, version, install_scope, agent_id,
                    metadata, capability_vec, updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s::vector, now())
                ON CONFLICT (tool_id) DO UPDATE SET
                    name = EXCLUDED.name,
                    version = EXCLUDED.version,
                    install_scope = EXCLUDED.install_scope,
                    agent_id = EXCLUDED.agent_id,
                    metadata = EXCLUDED.metadata,
                    capability_vec = EXCLUDED.capability_vec,
                    updated_at = now()
                """,
                (
                    tool_record["tool_id"],
                    tool_record.get("name", ""),
                    tool_record.get("version", ""),
                    meta.get("install_scope", "global"),
                    meta.get("agent_id"),
                    json.dumps(tool_record),
                    vec,
                ),
            )

    def get_tool(self, tool_id: str) -> dict | None:
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT metadata FROM brain_index WHERE tool_id = %s",
                (tool_id,),
            )
            row = cur.fetchone()
        return _jsonb(row[0]) if row else None

    def get_all_tools(self) -> list[dict]:
        with self.conn.cursor() as cur:
            cur.execute("SELECT metadata FROM brain_index ORDER BY tool_id")
            rows = cur.fetchall()
        return [_jsonb(row[0]) for row in rows]

    def delete_tool(self, tool_id: str) -> bool:
        with self.conn.cursor() as cur:
            cur.execute("DELETE FROM brain_index WHERE tool_id = %s", (tool_id,))
            return cur.rowcount > 0

    def update_trust(self, tool_id: str, new_score: float) -> None:
        tool = self.get_tool(tool_id)
        if not tool:
            return
        prov = tool.setdefault("layer_5_provenance", {})
        prov["trust_score"] = new_score
        prov["trust_score_last_evaluated"] = datetime.now(timezone.utc).isoformat()
        self.save_tool(tool)

    def search_similar(
        self,
        vec: np.ndarray,
        scope: str,
        exclude_id: str,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        vector = _vector_literal(vec)
        with self.conn.cursor() as cur:
            cur.execute(
                """
                SELECT tool_id, name, 1 - (capability_vec <=> %s::vector) AS score
                FROM brain_index
                WHERE install_scope IN (%s, %s)
                  AND tool_id != %s
                  AND capability_vec IS NOT NULL
                ORDER BY capability_vec <=> %s::vector
                LIMIT %s
                """,
                (vector, "global", scope, exclude_id, vector, limit),
            )
            rows = cur.fetchall()
        return [
            {"tool_id": row[0], "name": row[1], "score": round(float(row[2]), 4)}
            for row in rows
        ]

    def get_dep_graph(self) -> dict:
        with self.conn.cursor() as cur:
            cur.execute("SELECT graph FROM dep_graph_state WHERE id = TRUE")
            row = cur.fetchone()
        return _jsonb(row[0]) if row else {}

    def update_dep_graph(self, graph: dict) -> None:
        with self.conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO dep_graph_state (id, graph, updated_at)
                VALUES (TRUE, %s::jsonb, now())
                ON CONFLICT (id) DO UPDATE SET
                    graph = EXCLUDED.graph,
                    updated_at = now()
                """,
                (json.dumps(graph),),
            )

    def merge_deps_for_tool(self, tool_id: str, deps: dict[str, str]) -> None:
        graph = self.get_dep_graph()
        for pkg, spec in deps.items():
            if pkg not in graph:
                graph[pkg] = {
                    "locked_version": spec.replace(">=", "").replace("==", "").strip(),
                    "required_by": [tool_id],
                }
            elif tool_id not in graph[pkg]["required_by"]:
                graph[pkg]["required_by"].append(tool_id)
        self.update_dep_graph(graph)

    def remove_deps_for_tool(self, tool_id: str) -> None:
        graph = self.get_dep_graph()
        for pkg in list(graph):
            info = graph[pkg]
            if tool_id in info.get("required_by", []):
                info["required_by"].remove(tool_id)
            if not info.get("required_by"):
                del graph[pkg]
        self.update_dep_graph(graph)


def _jsonb(value) -> dict:
    if isinstance(value, str):
        return json.loads(value)
    return dict(value)


def _vector_literal(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, np.ndarray):
        arr = value.astype(float).tolist()
    else:
        try:
            arr = [float(v) for v in value]
        except (TypeError, ValueError):
            return None
    if len(arr) != 384:
        return None
    return "[" + ",".join(str(v) for v in arr) + "]"
