"""Layer 3 — Capability Checker.

Direct implementation of blueprint §7.  Uses set theory for API-wrapper
tools and behavioral embedding comparison for LLM-powered tools.
"""

from __future__ import annotations

import numpy as np


class CapabilityChecker:
    """Determines the relationship between a new tool and an existing tool."""

    BEHAVIOR_SIM_THRESHOLD = 0.82

    def __init__(self, behavior_sim_threshold: float | None = None):
        if behavior_sim_threshold is not None:
            self.BEHAVIOR_SIM_THRESHOLD = behavior_sim_threshold

    def determine_relationship(
        self, new_tool: dict, existing_tool: dict
    ) -> dict:
        """Classify the overlap between two tools.

        Returns a dict with a ``case`` key indicating the relationship.
        """
        new_type = _tool_type(new_tool)
        existing_type = _tool_type(existing_tool)

        # Route to behavioral comparison if either tool is LLM-powered
        if "llm_powered" in (new_type, existing_type):
            return self._behavioral_compare(new_tool, existing_tool)

        return self._set_theory_compare(
            new_tool.get("capabilities", new_tool.get("layer_3_capabilities", {})),
            existing_tool.get("capabilities", existing_tool.get("layer_3_capabilities", {})),
        )

    def _extract_set(self, caps: dict) -> set[str]:
        """Extract a unified set of capabilities from a tool's capability dict."""
        return (
            _normalised_set(caps.get("inputs", []))
            | _normalised_set(caps.get("outputs", []))
            | _normalised_set(caps.get("permissions", []))
        )

    def _set_theory_compare(
        self, caps_new: dict, caps_existing: dict
    ) -> dict:
        """Compare two tools using set operations on their capability surfaces."""
        d = self._extract_set(caps_new)
        x = self._extract_set(caps_existing)

        if d == x:
            return {
                "case": "CASE_4_EXACT_MATCH",
                "d_unique": [],
                "x_unique": [],
            }
        elif x.issubset(d):
            return {
                "case": "CASE_2_PARTIAL_OVERLAP",
                "new_features_in_d": sorted(d - x),
            }
        elif d.issubset(x):
            return {
                "case": "CASE_3_PARENT_CHILD",
                "features_missing_in_d": sorted(x - d),
            }
        else:
            shared = d & x
            return {
                "case": "CASE_5_TANGENTIAL",
                "shared": sorted(shared),
                "d_only": sorted(d - shared),
                "x_only": sorted(x - shared),
            }

    def _behavioral_compare(
        self, new_tool: dict, existing_tool: dict
    ) -> dict:
        """Compare two LLM-powered tools using behavioral embeddings."""
        new_bspec = new_tool.get(
            "behavior_spec",
            new_tool.get("layer_6_behavior_spec", {}),
        )
        ex_bspec = existing_tool.get(
            "behavior_spec",
            existing_tool.get("layer_6_behavior_spec", {}),
        )

        new_valid, new_reason = _behavior_spec_is_usable(new_bspec)
        ex_valid, ex_reason = _behavior_spec_is_usable(ex_bspec)
        if not new_valid or not ex_valid:
            return {
                "case": "CASE_LLM_UNKNOWN",
                "message": "One or both LLM BehaviorSpecs are not verified and usable.",
                "new_reason": new_reason,
                "existing_reason": ex_reason,
            }

        new_vec = np.array(new_bspec.get("behavioral_embedding", []), dtype=float)
        ex_vec = np.array(ex_bspec.get("behavioral_embedding", []), dtype=float)

        if (
            new_vec.size == 0
            or ex_vec.size == 0
            or new_vec.shape != ex_vec.shape
            or np.linalg.norm(new_vec) == 0
            or np.linalg.norm(ex_vec) == 0
        ):
            return {
                "case": "CASE_LLM_UNKNOWN",
                "message": (
                    "One or both tools are LLM-powered but have no behavioral "
                    "embedding. Cannot determine overlap automatically. "
                    "Escalate to user."
                ),
            }

        sim = float(
            np.dot(new_vec, ex_vec)
            / (np.linalg.norm(new_vec) * np.linalg.norm(ex_vec))
        )

        new_behaviors = _behavior_terms(new_bspec)
        ex_behaviors = _behavior_terms(ex_bspec)
        behavior_overlap = len(new_behaviors & ex_behaviors) / max(
            len(new_behaviors | ex_behaviors), 1
        )
        combined_score = round(0.7 * sim + 0.3 * behavior_overlap, 4)

        if combined_score >= self.BEHAVIOR_SIM_THRESHOLD:
            return {
                "case": "CASE_LLM_OVERLAP",
                "combined_score": combined_score,
                "shared_behaviors": sorted(new_behaviors & ex_behaviors),
                "new_only_behaviors": sorted(new_behaviors - ex_behaviors),
            }
        else:
            return {
                "case": "CASE_LLM_DISTINCT",
                "combined_score": combined_score,
                "note": (
                    "LLM tools appear semantically distinct — "
                    "likely safe to install."
                ),
            }


def _tool_type(tool: dict) -> str:
    bspec = tool.get("layer_6_behavior_spec", tool.get("behavior_spec", {}))
    return tool.get("tool_type") or bspec.get("tool_type", "api_wrapper")


def _normalised_set(values) -> set[str]:
    return {
        " ".join(str(value).strip().lower().split())
        for value in (values or [])
        if str(value).strip()
    }


def _behavior_terms(bspec: dict) -> set[str]:
    boundary = bspec.get("scope_boundary", {})
    return (
        _normalised_set(bspec.get("declared_behaviors", []))
        | _normalised_set(boundary.get("does", []))
        | _normalised_set(boundary.get("does_not", []))
        | _normalised_set(boundary.get("requires_human_approval_before", []))
    )


def _behavior_spec_is_usable(bspec: dict) -> tuple[bool, str]:
    confidence = bspec.get("embedding_confidence", "missing")
    if confidence != "verified":
        return False, f"embedding_confidence={confidence}"
    if bspec.get("spec_superseded_by"):
        return False, f"superseded_by={bspec['spec_superseded_by']}"
    if not bspec.get("behavioral_embedding"):
        return False, "missing behavioral_embedding"
    return True, "verified"
