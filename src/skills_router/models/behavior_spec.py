"""BehaviorSpec v1.2 contract — matches blueprint §13."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ScopeBoundary:
    """What the tool does and does not do."""

    does: list[str] = field(default_factory=list)
    does_not: list[str] = field(default_factory=list)
    requires_human_approval_before: list[str] = field(default_factory=list)


@dataclass
class BehaviorSpec:
    """BehaviorSpec v1.2 — behavioral contract for a tool.

    Key v5 addition: ``spec_superseded_by`` — when set on a non-verified spec,
    the pipeline treats the embedding as invalid and routes to CASE_LLM_UNKNOWN.
    """

    behavior_spec_version: str = "1.2"
    tool_id: str = ""
    tool_type: str = "api_wrapper"  # "api_wrapper" | "llm_powered"

    declared_behaviors: list[str] = field(default_factory=list)
    known_nondeterminism: str = ""

    scope_boundary: ScopeBoundary = field(default_factory=ScopeBoundary)

    behavioral_embedding: list[float] = field(default_factory=list)
    embedding_confidence: str = "missing"  # "verified" | "auto" | "missing"
    spec_superseded_by: str | None = None  # v5: optional tool_id

    tested_input_output_pairs: list[dict[str, Any]] = field(default_factory=list)
    evaluation_instructions: str = ""

    @property
    def is_embedding_valid(self) -> bool:
        """Check if the behavioral embedding is usable.

        Returns False if:
        - embedding_confidence is "missing"
        - spec_superseded_by is set AND embedding_confidence is NOT "verified"
        """
        if self.embedding_confidence == "missing":
            return False
        if self.spec_superseded_by and self.embedding_confidence != "verified":
            return False
        return True

    def to_dict(self) -> dict:
        return {
            "behavior_spec_version": self.behavior_spec_version,
            "tool_id": self.tool_id,
            "tool_type": self.tool_type,
            "declared_behaviors": list(self.declared_behaviors),
            "known_nondeterminism": self.known_nondeterminism,
            "scope_boundary": {
                "does": list(self.scope_boundary.does),
                "does_not": list(self.scope_boundary.does_not),
                "requires_human_approval_before": list(
                    self.scope_boundary.requires_human_approval_before
                ),
            },
            "behavioral_embedding": list(self.behavioral_embedding),
            "embedding_confidence": self.embedding_confidence,
            "spec_superseded_by": self.spec_superseded_by,
            "tested_input_output_pairs": list(self.tested_input_output_pairs),
            "evaluation_instructions": self.evaluation_instructions,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "BehaviorSpec":
        sb_data = data.get("scope_boundary", {})
        scope_boundary = ScopeBoundary(
            does=sb_data.get("does", []),
            does_not=sb_data.get("does_not", []),
            requires_human_approval_before=sb_data.get(
                "requires_human_approval_before", []
            ),
        )
        return cls(
            behavior_spec_version=data.get("behavior_spec_version", "1.2"),
            tool_id=data.get("tool_id", ""),
            tool_type=data.get("tool_type", "api_wrapper"),
            declared_behaviors=data.get("declared_behaviors", []),
            known_nondeterminism=data.get("known_nondeterminism", ""),
            scope_boundary=scope_boundary,
            behavioral_embedding=data.get("behavioral_embedding", []),
            embedding_confidence=data.get("embedding_confidence", "missing"),
            spec_superseded_by=data.get("spec_superseded_by"),
            tested_input_output_pairs=data.get("tested_input_output_pairs", []),
            evaluation_instructions=data.get("evaluation_instructions", ""),
        )
