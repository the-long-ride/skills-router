"""Layer 1.5 — Dependency Conflict Resolver (v5).

Direct implementation of blueprint §5.  Unparseable specifiers are now
collected in a dedicated ``parse_errors`` list.
"""

from __future__ import annotations

from packaging.specifiers import SpecifierSet
from packaging.version import Version


class DependencyConflictResolver:
    """Detects version conflicts between a new tool's deps and installed deps."""

    def resolve(self, new_tool: dict, installed_dep_graph: dict) -> dict:
        """Check new_tool's dependencies against the installed graph.

        Args:
            new_tool: Parsed manifest dict (must have ``dependencies``).
            installed_dep_graph: ``{pkg: {"locked_version": str, "required_by": [str]}}``

        Returns:
            Result dict with status, action, and optionally conflicts/warnings/parse_errors.
        """
        new_deps = new_tool.get("dependencies", {})
        conflicts: list[dict] = []
        warnings: list[dict] = []
        parse_errors: list[dict] = []  # v5: surfaced to caller, not silently dropped

        for pkg, spec_str in new_deps.items():
            try:
                spec = SpecifierSet(str(spec_str))
            except Exception as e:
                parse_errors.append({
                    "package": pkg,
                    "specifier": spec_str,
                    "error": str(e),
                })
                continue

            if pkg not in installed_dep_graph:
                continue

            try:
                locked_ver = Version(str(installed_dep_graph[pkg]["locked_version"]))
                required_by = installed_dep_graph[pkg]["required_by"]
                if locked_ver not in spec:
                    conflicts.append({
                        "package": pkg,
                        "new_tool_requires": spec_str,
                        "currently_locked": str(locked_ver),
                        "locked_by_tools": required_by,
                        "severity": "HARD",
                    })
                elif str(locked_ver) != spec_str.replace("==", "").strip():
                    warnings.append({
                        "package": pkg,
                        "note": (
                            f"Acceptable but not pinned identically. "
                            f"Locked={locked_ver}, Requested={spec_str}"
                        ),
                        "severity": "SOFT",
                    })
            except Exception as e:
                parse_errors.append({
                    "package": pkg,
                    "specifier": spec_str,
                    "error": str(e),
                })

        if conflicts:
            return {
                "status": "CONFLICT_FOUND",
                "action": "ROUTE_TO_DEP_WG",
                "hard_conflicts": conflicts,
                "soft_warnings": warnings,
                "parse_errors": parse_errors,
            }

        if parse_errors:
            return {
                "status": "PARSE_ERROR",
                "action": "ROUTE_TO_DEP_WG",
                "hard_conflicts": [],
                "soft_warnings": warnings,
                "parse_errors": parse_errors,
            }

        return {
            "status": "CLEAN",
            "action": "PROCEED_TO_EMBEDDER",
            "soft_warnings": warnings,
            "parse_errors": parse_errors,
        }
