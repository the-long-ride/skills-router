"""In-memory Brain Index store with optional JSON file persistence.

Used for MVP (< 500 tools per blueprint §2).
"""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from typing import Any

import numpy as np

from skills_router.storage.base import AbstractBrainIndexStore


class MemoryBrainIndexStore(AbstractBrainIndexStore):
    """Dict-backed store with optional save/load to JSON files."""

    def __init__(
        self,
        brain_index_path: str | None = None,
        dep_graph_path: str | None = None,
    ):
        self._lock = threading.Lock()
        self._tools: dict[str, dict] = {}
        self._dep_graph: dict[str, dict] = {}
        self._brain_index_path = brain_index_path
        self._dep_graph_path = dep_graph_path

        # Load from disk if files exist
        if brain_index_path and os.path.exists(brain_index_path):
            self._load_brain_index(brain_index_path)
        if dep_graph_path and os.path.exists(dep_graph_path):
            self._load_dep_graph(dep_graph_path)

    # -- Tool CRUD ------------------------------------------------------------

    def save_tool(self, tool_record: dict) -> None:
        with self._lock:
            tool_id = tool_record["tool_id"]
            self._tools[tool_id] = tool_record
            self._persist_brain_index()

    def get_tool(self, tool_id: str) -> dict | None:
        with self._lock:
            return self._tools.get(tool_id)

    def get_all_tools(self) -> list[dict]:
        with self._lock:
            return list(self._tools.values())

    def delete_tool(self, tool_id: str) -> bool:
        with self._lock:
            if tool_id in self._tools:
                del self._tools[tool_id]
                self._persist_brain_index()
                return True
            return False

    # -- Trust updates --------------------------------------------------------

    def update_trust(self, tool_id: str, new_score: float) -> None:
        with self._lock:
            tool = self._tools.get(tool_id)
            if tool:
                prov = tool.setdefault("layer_5_provenance", {})
                prov["trust_score"] = new_score
                prov["trust_score_last_evaluated"] = datetime.now(
                    timezone.utc
                ).isoformat()
                self._persist_brain_index()

    # -- Vector search (in-memory cosine) -------------------------------------

    def search_similar(
        self,
        vec: np.ndarray,
        scope: str,
        exclude_id: str,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        results = []
        for tool in self._tools.values():
            if tool["tool_id"] == exclude_id:
                continue
            tool_scope = tool.get("layer_meta", {}).get("install_scope", "global")
            if tool_scope not in ("global", scope):
                continue
            stored_vec = tool.get("layer_2_vector_signature", [])
            if not stored_vec:
                continue
            try:
                stored_arr = np.array(stored_vec, dtype=float)
            except (TypeError, ValueError):
                continue
            if stored_arr.ndim != 1 or stored_arr.shape != vec.shape:
                continue
            score = self._cosine(vec, stored_arr)
            results.append({
                "tool_id": tool["tool_id"],
                "name": tool.get("name", ""),
                "score": round(score, 4),
            })
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:limit]

    @staticmethod
    def _cosine(a: np.ndarray, b: np.ndarray) -> float:
        na, nb = np.linalg.norm(a), np.linalg.norm(b)
        if na == 0 or nb == 0:
            return 0.0
        return float(np.dot(a, b) / (na * nb))

    # -- Dependency graph -----------------------------------------------------

    def get_dep_graph(self) -> dict:
        with self._lock:
            return dict(self._dep_graph)

    def update_dep_graph(self, graph: dict) -> None:
        with self._lock:
            self._dep_graph = dict(graph)
            self._persist_dep_graph()

    def merge_deps_for_tool(self, tool_id: str, deps: dict[str, str]) -> None:
        with self._lock:
            for pkg, spec in deps.items():
                if pkg not in self._dep_graph:
                    locked = spec.replace(">=", "").replace("==", "").strip()
                    self._dep_graph[pkg] = {
                        "locked_version": locked,
                        "required_by": [tool_id],
                    }
                else:
                    if tool_id not in self._dep_graph[pkg]["required_by"]:
                        self._dep_graph[pkg]["required_by"].append(tool_id)
            self._persist_dep_graph()

    def remove_deps_for_tool(self, tool_id: str) -> None:
        with self._lock:
            to_delete = []
            for pkg, info in self._dep_graph.items():
                if tool_id in info["required_by"]:
                    info["required_by"].remove(tool_id)
                if not info["required_by"]:
                    to_delete.append(pkg)
            for pkg in to_delete:
                del self._dep_graph[pkg]
            self._persist_dep_graph()

    # -- Persistence ----------------------------------------------------------

    def _persist_brain_index(self) -> None:
        if self._brain_index_path:
            os.makedirs(os.path.dirname(self._brain_index_path), exist_ok=True)
            # Convert numpy arrays to lists for JSON serialization
            serializable = {}
            for tid, tool in self._tools.items():
                serializable[tid] = self._make_serializable(tool)
            with open(self._brain_index_path, "w") as f:
                json.dump(serializable, f, indent=2)

    def _persist_dep_graph(self) -> None:
        if self._dep_graph_path:
            os.makedirs(os.path.dirname(self._dep_graph_path), exist_ok=True)
            with open(self._dep_graph_path, "w") as f:
                json.dump(self._dep_graph, f, indent=2)

    def _load_brain_index(self, path: str) -> None:
        with open(path) as f:
            self._tools = json.load(f)

    def _load_dep_graph(self, path: str) -> None:
        with open(path) as f:
            self._dep_graph = json.load(f)

    @staticmethod
    def _make_serializable(obj: Any) -> Any:
        """Recursively convert numpy types to Python natives."""
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            return float(obj)
        if isinstance(obj, dict):
            return {k: MemoryBrainIndexStore._make_serializable(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [MemoryBrainIndexStore._make_serializable(v) for v in obj]
        return obj
