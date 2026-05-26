"""Main pipeline orchestrator for skills-router.

Coordinates all layers to evaluate and install agent skill/plugin packages.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Callable

from skills_router.audit.logger import AuditLogger
from skills_router.config import SkillsRouterConfig
from skills_router.layers.capability_checker import CapabilityChecker
from skills_router.layers.dependency_resolver import DependencyConflictResolver
from skills_router.layers.health_check import HealthChecker
from skills_router.layers.manifest_parser import ManifestParser, ManifestParseError
from skills_router.layers.semantic_evaluator import SemanticEvaluator
from skills_router.layers.trust_gate import TrustGate
from skills_router.models.audit_log import AuditEntry
from skills_router.models.enums import WGCase, WGDecision
from skills_router.storage.base import AbstractBrainIndexStore
from skills_router.wg.prompt_engine import PromptEngine

logger = logging.getLogger(__name__)


class SkillsRouterOrchestrator:
    """The main pipeline coordinator.

    Runs tools through all layers:
    1. Parse manifest
    2. Trust Gate
    3. Dependency resolution
    4. Semantic evaluation
    5. Capability analysis (if overlap)
    6. BehaviorSpec check
    7. Workspace/Global prompt → user decision
    8. Install / cleanup / audit
    """

    def __init__(
        self,
        config: SkillsRouterConfig,
        store: AbstractBrainIndexStore,
        decision_callback: Callable[[str, list[str]], int] | None = None,
    ):
        self.config = config
        self.store = store
        self.parser = ManifestParser()
        self.trust_gate = TrustGate(
            hard_block_threshold=config.trust_hard_block_threshold,
            soft_warn_threshold=config.trust_soft_warn_threshold,
        )
        self.dep_resolver = DependencyConflictResolver()
        self.evaluator = SemanticEvaluator(
            model_name=config.embedding_model,
            similarity_threshold=config.similarity_threshold,
            max_results=config.semantic_result_limit,
        )
        self.capability_checker = CapabilityChecker(
            behavior_sim_threshold=config.behavior_sim_threshold,
        )
        self.health_checker = HealthChecker()
        self.prompt_engine = PromptEngine(
            max_items=config.prompt_list_limit,
            max_chars=config.prompt_char_limit,
        )
        self.audit_logger = AuditLogger(log_path=config.audit_log_path)

        # Callback for Workspace/Global decisions: receives (prompt_text, options) → chosen index
        # If None, fail closed to the safe option (usually cancel).
        self._decision_callback = decision_callback

    def install(
        self,
        manifest: str | dict,
        scope: str = "global",
        user_id: str = "cli-user",
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Run the full install pipeline.

        Args:
            manifest: Raw JSON string or parsed dict of the tool manifest.
            scope: Install scope (``"global"``, ``"workspace:<id>"``).
            user_id: ID of the user performing the install.
            dry_run: If true, evaluate all gates but do not mutate registry state.

        Returns:
            Result dict with keys: status, tool_id, wg_case, decision, details.
        """
        # --- Step 1: Parse manifest ------------------------------------------
        try:
            parsed = self.parser.parse(manifest)
        except ManifestParseError as e:
            return {"status": "ERROR", "error": f"Manifest parse error: {e}"}

        tool_id = parsed["tool_id"]
        tool_name = parsed.get("name", tool_id)
        tool_version = parsed.get("version", "0.0.0")

        logger.info(
            "Pipeline started",
            extra={"event": "pipeline_start", "tool_id": tool_id,
                   "tool_name": tool_name, "scope": scope, "user_id": user_id},
        )

        # Set install scope and timestamp
        parsed.setdefault("layer_meta", {})
        parsed["layer_meta"]["install_scope"] = scope
        if not parsed["layer_meta"].get("installed_at"):
            parsed["layer_meta"]["installed_at"] = datetime.now(
                timezone.utc
            ).isoformat()

        # --- Step 2: Trust Gate ----------------------------------------------
        trust_manifest = self.parser.build_trust_manifest(parsed)
        trust_result = self.trust_gate.evaluate(trust_manifest)

        logger.info(
            "Trust Gate: verdict=%s score=%.3f",
            trust_result["verdict"],
            trust_result["score"],
            extra={"event": "trust_gate", "tool_id": tool_id,
                   "verdict": trust_result["verdict"],
                   "score": trust_result["score"]},
        )

        if trust_result["verdict"] == "HARD_REJECT":
            if not dry_run:
                self._log_audit(
                    user_id, tool_id, tool_version, WGCase.CASE_TRUST_WARN,
                    WGDecision.CANCEL, trust_result.get("reason", ""), scope,
                    trust_result["score"],
                )
            return {
                "status": "HARD_REJECT",
                "tool_id": tool_id,
                "wg_case": "CASE_TRUST_WARN",
                "decision": "CANCEL",
                "details": trust_result,
            }

        if trust_result["verdict"] == "SOFT_WARN":
            # Show trust warning WG
            ctx = {
                "score": trust_result["score"],
                "factors": trust_result.get("issues", {}),
            }
            prompt, options = self.prompt_engine.render_full(
                "CASE_TRUST_WARN", ctx
            )
            decision_idx = self._get_decision(prompt, options)
            if decision_idx != 0:  # Not "Proceed anyway"
                if not dry_run:
                    self._log_audit(
                        user_id, tool_id, tool_version, WGCase.CASE_TRUST_WARN,
                        WGDecision.CANCEL, "User declined low-trust tool", scope,
                        trust_result["score"],
                    )
                return {
                    "status": "CANCELLED",
                    "tool_id": tool_id,
                    "wg_case": "CASE_TRUST_WARN",
                    "decision": "CANCEL",
                    "details": trust_result,
                }
            # User overrides — continue with pipeline
            logger.info("User overrode trust warning for %s", tool_id)

        # --- Step 3: Dependency Resolution -----------------------------------
        dep_graph = self.store.get_dep_graph()
        dep_result = self.dep_resolver.resolve(parsed, dep_graph)
        merge_dependencies = bool(parsed.get("dependencies"))

        logger.info(
            "Dependency check: status=%s",
            dep_result["status"],
            extra={"event": "dep_check", "tool_id": tool_id,
                   "status": dep_result["status"]},
        )

        if dep_result["status"] in ("CONFLICT_FOUND", "PARSE_ERROR"):
            conflicts = dep_result.get("hard_conflicts", [])
            conflict = conflicts[0] if conflicts else {}
            ctx = {
                "conflicts": conflicts,
                "package": conflict.get("package"),
                "version_d": conflict.get("new_tool_requires"),
                "version_locked": conflict.get("currently_locked"),
                "locked_by": ", ".join(conflict.get("locked_by_tools", [])),
                "parse_errors": dep_result.get("parse_errors", []),
            }
            prompt, options = self.prompt_engine.render_full(
                "CASE_DEP", ctx, parse_only=dep_result["status"] == "PARSE_ERROR"
            )
            decision_idx = self._get_decision(prompt, options)
            cancel_idx = len(options) - 1
            decision = WGDecision.APPROVE if decision_idx != cancel_idx else WGDecision.CANCEL
            if decision == WGDecision.APPROVE and decision_idx == 0:
                merge_dependencies = False

            if not dry_run:
                self._log_audit(
                    user_id, tool_id, tool_version, WGCase.CASE_DEP,
                    decision, self._dependency_reason(dep_result), scope,
                    trust_result["score"],
                )

            if decision == WGDecision.CANCEL:
                return {
                    "status": "CANCELLED",
                    "tool_id": tool_id,
                    "wg_case": "CASE_DEP",
                    "decision": "CANCEL",
                    "details": dep_result,
                }

        # --- Step 4: Semantic Evaluation -------------------------------------
        brain_index = self.store.get_all_tools()
        sem_result = self.evaluator.evaluate(
            parsed, scope, brain_index=brain_index
        )

        logger.info(
            "Semantic evaluation: status=%s",
            sem_result["status"],
            extra={"event": "semantic_eval", "tool_id": tool_id,
                   "status": sem_result["status"],
                   "top_score": sem_result["top_match"]["score"] if sem_result.get("top_match") else None},
        )

        # Store the generated vector for later persistence
        new_vec = sem_result.get("new_vec")
        if new_vec is not None:
            parsed["layer_2_vector_signature"] = new_vec.tolist()

        wg_case: str
        wg_ctx: dict
        options_kwargs: dict = {}

        if sem_result["status"] == "BRAND_NEW_SCOPE":
            # --- Case 1: Brand New -----------------------------------------------
            wg_case = "CASE_1"
            wg_ctx = self._build_case1_ctx(parsed, trust_result)
        else:
            # --- Step 5: Capability Analysis (overlap detected) ------------------
            top_match = sem_result["top_match"]
            existing_tool = self.store.get_tool(top_match["tool_id"])

            if existing_tool is None:
                # Fallback if existing tool is not found
                wg_case = "CASE_1"
                wg_ctx = self._build_case1_ctx(parsed, trust_result)
            else:
                # Check BehaviorSpec validity (v5: spec_superseded_by)
                bspec = parsed.get("layer_6_behavior_spec", {})
                ex_bspec = existing_tool.get("layer_6_behavior_spec", {})

                superseded = bspec.get("spec_superseded_by") is not None
                not_verified = bspec.get("embedding_confidence") != "verified"
                ex_superseded = ex_bspec.get("spec_superseded_by") is not None
                ex_not_verified = ex_bspec.get("embedding_confidence") != "verified"

                if (superseded and not_verified) or (ex_superseded and ex_not_verified):
                    # Route to CASE_LLM_UNKNOWN
                    wg_case = "CASE_LLM_UNKNOWN"
                    wg_ctx = {
                        "tool_name": parsed.get("name", tool_id),
                        "new_tool_name": parsed.get("name", tool_id),
                        "new_confidence": bspec.get("embedding_confidence", "missing"),
                        "existing_tool_name": existing_tool.get("name", ""),
                        "existing_confidence": ex_bspec.get("embedding_confidence", "missing"),
                    }
                else:
                    # Run capability analysis
                    cap_result = self.capability_checker.determine_relationship(
                        parsed, existing_tool,
                    )
                    wg_case, wg_ctx, options_kwargs = self._map_capability_result(
                        cap_result, parsed, existing_tool, trust_result,
                    )

        # --- Step 6: Workspace/Global Prompt ---------------------------------
        prompt, options = self.prompt_engine.render_full(
            wg_case, wg_ctx, **options_kwargs
        )
        decision_idx = self._get_decision(prompt, options)

        # Map index to decision
        if decision_idx == len(options) - 1:
            decision = WGDecision.CANCEL
        elif wg_case == "CASE_TRUST_WARN" and decision_idx == 0:
            decision = WGDecision.OVERRIDE
        else:
            decision = WGDecision.APPROVE

        decision_summary = self._build_decision_summary(
            wg_case,
            decision,
            options[decision_idx],
            trust_result,
            dep_result,
            sem_result,
        )

        if dry_run:
            return {
                "status": (
                    "DRY_RUN_APPROVED"
                    if decision != WGDecision.CANCEL
                    else "DRY_RUN_CANCELLED"
                ),
                "tool_id": tool_id,
                "wg_case": wg_case,
                "decision": (
                    decision.value if isinstance(decision, WGDecision) else decision
                ),
                "recovery_action": None,
                "decision_summary": decision_summary,
                "details": {
                    "dry_run": True,
                    "trust": trust_result,
                    "dependencies": dep_result,
                    "semantic": {k: v for k, v in sem_result.items() if k != "new_vec"},
                },
            }

        # --- Step 7: Execute Decision ----------------------------------------
        recovery_action = None

        if decision in (WGDecision.APPROVE, WGDecision.OVERRIDE):
            # Save tool to store
            self.store.save_tool(parsed)

            # Merge dependencies
            if merge_dependencies:
                self.store.merge_deps_for_tool(tool_id, parsed["dependencies"])

            # Post-install health check
            health = self.health_checker.check(parsed)
            if health["status"] == "FAIL":
                logger.warning(
                    "Health check failed for %s; cleaning Skills Router state",
                    tool_id,
                    extra={"event": "health_check_fail", "tool_id": tool_id},
                )
                self.store.delete_tool(tool_id)
                self.store.remove_deps_for_tool(tool_id)
                decision = WGDecision.CANCEL
                recovery_action = "removed_registry_entry_and_dependencies"

            logger.info(
                "Tool installed successfully",
                extra={"event": "install_success", "tool_id": tool_id,
                       "wg_case": wg_case},
            )
        else:
            logger.info(
                "Installation cancelled",
                extra={"event": "install_cancel", "tool_id": tool_id,
                       "wg_case": wg_case},
            )

        # --- Step 8: Audit Log -----------------------------------------------
        self._log_audit(
            user_id, tool_id, tool_version,
            WGCase(wg_case) if wg_case in WGCase.__members__ else wg_case,
            decision, options[decision_idx] if decision_idx < len(options) else "",
            scope, trust_result["score"],
        )

        return {
            "status": "INSTALLED" if decision != WGDecision.CANCEL else "CANCELLED",
            "tool_id": tool_id,
            "wg_case": wg_case,
            "decision": decision.value if isinstance(decision, WGDecision) else decision,
            "recovery_action": recovery_action,
            "decision_summary": decision_summary,
            "details": {
                "trust": trust_result,
                "dependencies": dep_result,
                "semantic": {k: v for k, v in sem_result.items() if k != "new_vec"},
            },
        }

    def list_tools(self, scope: str | None = None) -> list[dict]:
        """List installed tools, optionally filtered by scope."""
        tools = self.store.get_all_tools()
        if scope:
            tools = [
                t for t in tools
                if t.get("layer_meta", {}).get("install_scope") == scope
            ]
        return [
            {
                "tool_id": t["tool_id"],
                "name": t.get("name", ""),
                "version": t.get("version", ""),
                "scope": t.get("layer_meta", {}).get("install_scope", "global"),
                "trust_score": t.get("layer_5_provenance", {}).get("trust_score", 0),
            }
            for t in tools
        ]

    def inspect_tool(self, tool_id: str) -> dict | None:
        """Get the full Brain Index entry for a tool."""
        return self.store.get_tool(tool_id)

    # -- Internal helpers -----------------------------------------------------

    def _get_decision(self, prompt: str, options: list[str]) -> int:
        """Get user decision via callback or fail-closed default.

        Guards against invalid callback responses or raised exceptions,
        defaulting to the safest option (typically cancel/last option).
        """
        if self._decision_callback:
            try:
                choice = self._decision_callback(prompt, options)
                if not isinstance(choice, int) or choice < 0 or choice >= len(options):
                    logger.error(
                        "Decision callback returned invalid option index: %r (options count: %d). "
                        "Defaulting to safe option.",
                        choice,
                        len(options),
                    )
                    return max(0, len(options) - 1)
                return choice
            except Exception as e:
                logger.exception(
                    "Decision callback raised exception: %s. Defaulting to safe option.", e
                )
                return max(0, len(options) - 1)
        logger.warning(
            "No decision callback configured. Defaulting to safe option."
        )
        return max(0, len(options) - 1)

    @staticmethod
    def _build_case1_ctx(tool: dict, trust_result: dict) -> dict:
        """Build the WG context dict for CASE_1 (brand new scope)."""
        caps = tool.get("layer_3_capabilities", tool.get("capabilities", {}))
        return {
            "domain_tags": ", ".join(tool.get("layer_1_domain_tags", [])),
            "output_desc": ", ".join(caps.get("outputs", [])),
            "input_desc": ", ".join(caps.get("inputs", [])),
            "permissions": ", ".join(caps.get("permissions", [])),
            "trust_score": trust_result["score"],
            "publisher": tool.get("layer_5_provenance", {}).get(
                "publisher_id", "Unknown"
            ),
        }

    def _map_capability_result(
        self,
        cap_result: dict,
        new_tool: dict,
        existing_tool: dict,
        trust_result: dict,
    ) -> tuple[str, dict, dict]:
        """Map a CapabilityChecker result to WG case, context, and options kwargs."""
        case = cap_result["case"]
        options_kwargs: dict = {}

        if case == "CASE_4_EXACT_MATCH":
            wg_case = "CASE_4"
            wg_ctx = {
                "preferred_tool": "N/A (no scraper data yet)",
                "preference_reason": "Phase 3 web scraper not yet implemented",
                "dep_diff": "N/A",
                "d_updated_days": "?",
                "c_updated_days": "?",
                "d_trust": trust_result["score"],
                "c_trust": existing_tool.get("layer_5_provenance", {}).get("trust_score", "?"),
                "c_workflows": existing_tool.get("layer_meta", {}).get("dependent_workflows", []),
            }
        elif case == "CASE_2_PARTIAL_OVERLAP":
            wg_case = "CASE_2"
            wg_ctx = {
                "new_features": cap_result.get("new_features_in_d", []),
                "delta_permissions": "N/A",
                "perf_delta": "?",
                "perf_direction": "N/A",
                "d_community": "?",
                "a_community": "?",
                "a_workflows": existing_tool.get("layer_meta", {}).get("dependent_workflows", []),
            }
            extensible = existing_tool.get(
                "layer_3_capabilities", existing_tool.get("capabilities", {})
            ).get("extensible", False)
            options_kwargs = {"extensible": extensible}
        elif case == "CASE_3_PARENT_CHILD":
            wg_case = "CASE_3"
            wg_ctx = {
                "b_extra_features": cap_result.get("features_missing_in_d", []),
                "perf_delta": "?",
                "specialization": "specific task",
                "dep_footprint": "N/A",
                "d_trust": trust_result["score"],
                "b_trust": existing_tool.get("layer_5_provenance", {}).get("trust_score", "?"),
            }
        elif case == "CASE_5_TANGENTIAL":
            wg_case = "CASE_5"
            wg_ctx = {
                "shared": cap_result.get("shared", []),
                "d_only": cap_result.get("d_only", []),
                "x_only": cap_result.get("x_only", []),
            }
        elif case == "CASE_LLM_OVERLAP":
            wg_case = "CASE_LLM_OVERLAP"
            wg_ctx = {
                "combined_score": cap_result.get("combined_score", "?"),
                "shared_behaviors": cap_result.get("shared_behaviors", []),
                "new_only_behaviors": cap_result.get("new_only_behaviors", []),
            }
        elif case == "CASE_LLM_DISTINCT":
            # LLM tools are distinct → treat as brand new
            wg_case = "CASE_1"
            wg_ctx = self._build_case1_ctx(new_tool, trust_result)
        elif case == "CASE_LLM_UNKNOWN":
            wg_case = "CASE_LLM_UNKNOWN"
            wg_ctx = {
                "tool_name": new_tool.get("name", new_tool.get("tool_id", "")),
                "new_tool_name": new_tool.get("name", ""),
                "new_confidence": new_tool.get("layer_6_behavior_spec", {}).get(
                    "embedding_confidence", "missing"
                ),
                "existing_tool_name": existing_tool.get("name", ""),
                "existing_confidence": existing_tool.get("layer_6_behavior_spec", {}).get(
                    "embedding_confidence", "missing"
                ),
            }
        else:
            # Fallback
            wg_case = "CASE_1"
            wg_ctx = {}

        return wg_case, wg_ctx, options_kwargs

    @staticmethod
    def _dependency_reason(dep_result: dict) -> str:
        conflicts = dep_result.get("hard_conflicts", [])
        parse_errors = dep_result.get("parse_errors", [])
        parts = []
        if conflicts:
            parts.append("Conflicts: " + ", ".join(c["package"] for c in conflicts[:3]))
        if parse_errors:
            parts.append("Parse errors: " + ", ".join(p["package"] for p in parse_errors[:3]))
        return "; ".join(parts) or dep_result.get("status", "")

    @staticmethod
    def _build_decision_summary(
        wg_case: str,
        decision,
        selected_option: str,
        trust_result: dict,
        dep_result: dict,
        sem_result: dict,
    ) -> dict:
        top_match = sem_result.get("top_match") or {}
        return {
            "case": wg_case,
            "decision": decision.value if hasattr(decision, "value") else str(decision),
            "selected_option": selected_option,
            "trust_score": trust_result.get("score"),
            "dependency_status": dep_result.get("status"),
            "top_match": {
                "tool_id": top_match.get("tool_id"),
                "name": top_match.get("name"),
                "score": top_match.get("score"),
            } if top_match else None,
        }

    def _log_audit(
        self,
        user_id: str,
        tool_id: str,
        tool_version: str,
        wg_case,
        decision,
        reason: str,
        scope: str,
        trust_score: float,
    ) -> None:
        """Write an audit entry."""
        entry = AuditEntry(
            user_id=user_id,
            tool_id=tool_id,
            tool_version=tool_version,
            wg_case=wg_case.value if hasattr(wg_case, "value") else str(wg_case),
            decision=decision.value if hasattr(decision, "value") else str(decision),
            reason=reason,
            install_scope=scope,
            trust_score_at_install=trust_score,
        )
        self.audit_logger.log(entry)
