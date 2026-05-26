"""Shared enums for skills-router pipeline."""

from enum import Enum


class WGCase(str, Enum):
    """Workspace/Global case identifiers — matches audit log schema §9."""

    CASE_1 = "CASE_1"                        # Brand New Scope
    CASE_2 = "CASE_2"                        # Partial Overlap
    CASE_3 = "CASE_3"                        # Parent/Child
    CASE_4 = "CASE_4"                        # Exact Match
    CASE_5 = "CASE_5"                        # Tangential Overlap
    CASE_DEP = "CASE_DEP"                    # Dependency Conflict
    CASE_TRUST_WARN = "CASE_TRUST_WARN"      # Low Trust Score
    CASE_TRUST_DEGRADED = "CASE_TRUST_DEGRADED"  # Trust Degraded Post-Install (v5)
    CASE_LLM_OVERLAP = "CASE_LLM_OVERLAP"    # LLM Behavioral Overlap
    CASE_LLM_UNKNOWN = "CASE_LLM_UNKNOWN"    # No Behavioral Embedding


class WGDecision(str, Enum):
    """User decisions in a Workspace/Global step."""

    APPROVE = "APPROVE"
    CANCEL = "CANCEL"
    OVERRIDE = "OVERRIDE"


class TrustVerdict(str, Enum):
    """Trust Gate evaluation outcomes."""

    HARD_REJECT = "HARD_REJECT"
    SOFT_WARN = "SOFT_WARN"
    PASS = "PASS"


class InstallScope(str, Enum):
    """Tool installation scope."""

    GLOBAL = "global"
    WORKSPACE = "workspace"
    AGENT = "agent"


class EmbeddingConfidence(str, Enum):
    """BehaviorSpec embedding confidence levels."""

    VERIFIED = "verified"
    AUTO = "auto"
    MISSING = "missing"
