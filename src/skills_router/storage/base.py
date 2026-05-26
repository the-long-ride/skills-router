"""Abstract storage interface for the Brain Index."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

import numpy as np


class AbstractBrainIndexStore(ABC):
    """Interface for Brain Index persistence.

    Implementations must handle tool records, dependency graphs,
    and vector similarity search.
    """

    # -- Tool CRUD ------------------------------------------------------------

    @abstractmethod
    def save_tool(self, tool_record: dict) -> None:
        """Persist a tool record (upsert by tool_id)."""

    @abstractmethod
    def get_tool(self, tool_id: str) -> dict | None:
        """Retrieve a tool record by ID. Returns None if not found."""

    @abstractmethod
    def get_all_tools(self) -> list[dict]:
        """Return all stored tool records."""

    @abstractmethod
    def delete_tool(self, tool_id: str) -> bool:
        """Remove a tool record. Returns True if it existed."""

    # -- Trust updates --------------------------------------------------------

    @abstractmethod
    def update_trust(self, tool_id: str, new_score: float) -> None:
        """Update the trust score and last-evaluated timestamp for a tool."""

    # -- Vector search --------------------------------------------------------

    @abstractmethod
    def search_similar(
        self,
        vec: np.ndarray,
        scope: str,
        exclude_id: str,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Find tools with similar capability vectors within scope.

        Returns list of dicts with keys: tool_id, name, score.
        """

    # -- Dependency graph -----------------------------------------------------

    @abstractmethod
    def get_dep_graph(self) -> dict:
        """Return the installed dependency graph.

        Format: {pkg: {"locked_version": str, "required_by": [tool_ids]}}
        """

    @abstractmethod
    def update_dep_graph(self, graph: dict) -> None:
        """Replace the dependency graph."""

    @abstractmethod
    def merge_deps_for_tool(self, tool_id: str, deps: dict[str, str]) -> None:
        """Merge a tool's dependencies into the global graph."""

    @abstractmethod
    def remove_deps_for_tool(self, tool_id: str) -> None:
        """Remove a tool's contributions from the dependency graph."""
