"""Layer 2 — Semantic Evaluator (v5).

Direct implementation of blueprint §6.  Random fallback is seeded
deterministically from ``tool_id`` for stable test results.
"""

from __future__ import annotations

import hashlib

import numpy as np

try:
    from sentence_transformers import SentenceTransformer  # type: ignore[import-untyped]
    HAS_ST = True
except ImportError:
    HAS_ST = False


class SemanticEvaluator:
    """MiniLM-based vector embedder with cosine overlap detection."""

    SIMILARITY_THRESHOLD = 0.85

    def __init__(
        self,
        model_name: str = "all-MiniLM-L6-v2",
        db_conn=None,
        similarity_threshold: float | None = None,
        max_results: int = 20,
    ):
        self.model = SentenceTransformer(model_name) if HAS_ST else None
        self.db_conn = db_conn
        self.max_results = max(1, max_results)
        if similarity_threshold is not None:
            self.SIMILARITY_THRESHOLD = similarity_threshold

    def create_signature(self, tool: dict) -> str:
        """Build a text signature from a tool's metadata for embedding."""
        caps = tool.get("layer_3_capabilities", tool.get("capabilities", {}))
        bspec = tool.get("layer_6_behavior_spec", tool.get("behavior_spec", {}))
        boundary = bspec.get("scope_boundary", {})

        domain = _normalised_join(tool.get("layer_1_domain_tags", tool.get("domain_tags", [])))
        inputs = _normalised_join(caps.get("inputs", []))
        outputs = _normalised_join(caps.get("outputs", []))
        permissions = _normalised_join(caps.get("permissions", []))
        behaviours = _normalised_join(bspec.get("declared_behaviors", []))
        does_not = _normalised_join(boundary.get("does_not", []))
        approvals = _normalised_join(boundary.get("requires_human_approval_before", []))

        return (
            f"Tool Name: {tool.get('name', '')}. "
            f"Domain: {domain}. "
            f"Inputs: {inputs}. "
            f"Outputs: {outputs}. "
            f"Permissions: {permissions}. "
            f"Behaviors: {behaviours}. "
            f"Does not: {does_not}. "
            f"Human approval before: {approvals}."
        )

    def embed(self, text: str, tool_id: str = "") -> np.ndarray:
        """Generate a 384-dim embedding.

        v5: random fallback is seeded from tool_id for deterministic
        in-memory/test behaviour across process restarts.
        """
        if self.model:
            return self.model.encode(text)
        seed = _stable_seed(tool_id or text)
        rng = np.random.default_rng(seed)
        return rng.random(384)

    def cosine(self, a: np.ndarray, b: np.ndarray) -> float:
        """Cosine similarity between two vectors."""
        na, nb = np.linalg.norm(a), np.linalg.norm(b)
        return float(np.dot(a, b) / (na * nb)) if na and nb else 0.0

    def evaluate(
        self,
        new_tool: dict,
        scope: str,
        brain_index: list | None = None,
    ) -> dict:
        """Run semantic overlap detection against the brain index.

        Args:
            new_tool: Parsed manifest dict.
            scope:    Install scope string (e.g. ``"global"``).
            brain_index: In-memory tool list (used when db_conn is None).

        Returns:
            Dict with status, action, top_match, and all_scores.
        """
        new_vec = self.embed(
            self.create_signature(new_tool),
            new_tool.get("tool_id", ""),
        )

        if self.db_conn:
            results = self._query_pgvector(new_vec, new_tool["tool_id"], scope)
        else:
            results = self._in_memory(
                new_vec,
                new_tool.get("tool_id", ""),
                brain_index or [],
                scope,
            )

        top = results[0] if results else None
        overlap = top is not None and top["score"] >= self.SIMILARITY_THRESHOLD

        return {
            "status": "OVERLAP_DETECTED" if overlap else "BRAND_NEW_SCOPE",
            "action": "PROCEED_TO_AST" if overlap else "PROCEED_TO_CASE_1",
            "top_match": top,
            "all_scores": results,
            "new_vec": new_vec,
        }

    def _query_pgvector(
        self, vec: np.ndarray, tool_id: str, scope: str
    ) -> list[dict]:
        """Query pgvector for similar tools (Phase 2)."""
        base_scope = "global"
        with self.db_conn.cursor() as cur:
            cur.execute(
                """
                SELECT tool_id, name,
                       1 - (capability_vec <=> %s::vector) AS similarity
                FROM brain_index
                WHERE install_scope IN (%s, %s)
                  AND tool_id != %s
                ORDER BY similarity DESC
                                LIMIT %s
                """,
                                (vec.tolist(), base_scope, scope, tool_id, self.max_results),
            )
            return [
                {"tool_id": r[0], "name": r[1], "score": round(r[2], 4)}
                for r in cur.fetchall()
            ]

    def _in_memory(
        self, new_vec: np.ndarray, new_tool_id: str, brain_index: list,
        scope: str = "global",
    ) -> list[dict]:
        """Brute-force cosine search over in-memory tool list.

        v5 fixes:
        - Scope filtering: only compares against tools in 'global' or matching scope
        - Uses stored vectors when available instead of re-embedding every tool
        """
        scored = []
        for t in brain_index:
            if t.get("tool_id") == new_tool_id:
                continue
            # Scope filtering (matches pgvector SQL in blueprint §2)
            tool_scope = t.get("layer_meta", {}).get("install_scope", "global")
            if tool_scope not in ("global", scope):
                continue
            # Prefer stored vector, fall back to re-embedding
            stored_vec = t.get("layer_2_vector_signature", [])
            t_vec = _coerce_vector(stored_vec, expected_dim=new_vec.shape[0])
            if t_vec is None:
                if stored_vec:
                    # Bad or stale vectors should not crash decision-making.
                    continue
                sig = self.create_signature(t)
                t_vec = self.embed(sig, t.get("tool_id", ""))
            score = round(self.cosine(new_vec, t_vec), 4)
            scored.append({
                "tool_id": t["tool_id"],
                "name": t.get("name", ""),
                "score": score,
            })
        return sorted(scored, key=lambda x: x["score"], reverse=True)[: self.max_results]


def _stable_seed(value: str) -> int:
    """Return a stable 32-bit seed for deterministic fallback embeddings."""
    digest = hashlib.blake2b(value.encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(digest, "big") % (2**32)


def _normalised_join(values) -> str:
    """Build a stable text fragment for embedding signatures."""
    normalised = {
        " ".join(str(value).strip().split())
        for value in (values or [])
        if str(value).strip()
    }
    return ", ".join(sorted(normalised, key=str.lower))


def _coerce_vector(value, expected_dim: int) -> np.ndarray | None:
    """Convert stored vectors defensively, rejecting malformed dimensions."""
    if value is None:
        return None
    try:
        arr = np.array(value, dtype=float)
    except (TypeError, ValueError):
        return None
    if arr.ndim != 1 or arr.size != expected_dim:
        return None
    return arr
