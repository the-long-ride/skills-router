"""Brain Index schema v5 — dataclass representation of a tool record.

Mirrors the full JSON schema from blueprint §3, with nested dataclasses
for each layer.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class Capabilities:
    """Layer 3 — tool capability surface."""

    inputs: list[str] = field(default_factory=list)
    outputs: list[str] = field(default_factory=list)
    permissions: list[str] = field(default_factory=list)
    extensible: bool = False


@dataclass
class Telemetry:
    """Layer 4 — sandbox telemetry."""

    virtual_env_isolated: bool = False
    average_execution_ms: int = 0
    last_known_stable_state_hash: str = ""
    health_check_endpoint: str = "/healthz"
    last_health_check_passed: str | None = None


@dataclass
class TrustFactors:
    """Sub-fields of provenance trust scoring."""

    publisher_known: bool = False
    github_stars: int = 0
    last_commit_days_ago: int = 999
    open_critical_cves: int = 0
    community_sentiment_score: float = 0.5


@dataclass
class Provenance:
    """Layer 5 — publisher provenance and trust."""

    publisher_id: str = ""
    signature_hash: str = ""
    signature_verified: bool = False
    trust_score: float = 0.0
    trust_factors: TrustFactors = field(default_factory=TrustFactors)
    install_source: str = "unknown"
    published_at: str = ""
    trust_score_last_evaluated: str = ""


@dataclass
class BehaviorSpecData:
    """Layer 6 — behavioral specification (BehaviorSpec v1.2)."""

    tool_type: str = "api_wrapper"
    declared_behaviors: list[str] = field(default_factory=list)
    known_nondeterminism: str = ""
    behavioral_embedding: list[float] = field(default_factory=list)
    embedding_confidence: str = "missing"  # verified | auto | missing
    spec_superseded_by: str | None = None  # v5: optional tool_id
    tested_input_output_pairs: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class LayerMeta:
    """Metadata about installation context."""

    dependent_workflows: list[str] = field(default_factory=list)
    install_scope: str = "global"
    agent_id: str | None = None
    installed_at: str = ""
    version_pin_strategy: str = "minor"


@dataclass
class BrainIndexEntry:
    """Complete Brain Index record for a single tool.

    Corresponds to the schema in blueprint v5 §3.
    """

    tool_id: str = ""
    name: str = ""
    version: str = ""
    dependencies: dict[str, str] = field(default_factory=dict)

    # Layers
    layer_1_domain_tags: list[str] = field(default_factory=list)
    layer_2_vector_signature: list[float] = field(default_factory=list)
    layer_3_capabilities: Capabilities = field(default_factory=Capabilities)
    layer_4_telemetry: Telemetry = field(default_factory=Telemetry)
    layer_5_provenance: Provenance = field(default_factory=Provenance)
    layer_6_behavior_spec: BehaviorSpecData = field(default_factory=BehaviorSpecData)
    layer_meta: LayerMeta = field(default_factory=LayerMeta)

    @classmethod
    def from_manifest(cls, data: dict) -> "BrainIndexEntry":
        """Create a BrainIndexEntry from a raw manifest dict."""
        caps_data = data.get("layer_3_capabilities", data.get("capabilities", {}))
        caps = Capabilities(
            inputs=caps_data.get("inputs", []),
            outputs=caps_data.get("outputs", []),
            permissions=caps_data.get("permissions", []),
            extensible=caps_data.get("extensible", False),
        )

        tel_data = data.get("layer_4_telemetry", {})
        telemetry = Telemetry(
            virtual_env_isolated=tel_data.get("virtual_env_isolated", False),
            average_execution_ms=tel_data.get("average_execution_ms", 0),
            last_known_stable_state_hash=tel_data.get("last_known_stable_state_hash", ""),
            health_check_endpoint=tel_data.get("health_check_endpoint", "/healthz"),
            last_health_check_passed=tel_data.get("last_health_check_passed"),
        )

        prov_data = data.get("layer_5_provenance", {})
        tf_data = prov_data.get("trust_factors", {})
        trust_factors = TrustFactors(
            publisher_known=tf_data.get("publisher_known", False),
            github_stars=tf_data.get("github_stars", 0),
            last_commit_days_ago=tf_data.get("last_commit_days_ago", 999),
            open_critical_cves=tf_data.get("open_critical_cves", 0),
            community_sentiment_score=tf_data.get("community_sentiment_score", 0.5),
        )
        provenance = Provenance(
            publisher_id=prov_data.get("publisher_id", ""),
            signature_hash=prov_data.get("signature_hash", ""),
            signature_verified=prov_data.get("signature_verified", False),
            trust_score=prov_data.get("trust_score", 0.0),
            trust_factors=trust_factors,
            install_source=prov_data.get("install_source", "unknown"),
            published_at=prov_data.get("published_at", ""),
            trust_score_last_evaluated=prov_data.get("trust_score_last_evaluated", ""),
        )

        bspec_data = data.get("layer_6_behavior_spec", {})
        behavior_spec = BehaviorSpecData(
            tool_type=bspec_data.get("tool_type", "api_wrapper"),
            declared_behaviors=bspec_data.get("declared_behaviors", []),
            known_nondeterminism=bspec_data.get("known_nondeterminism", ""),
            behavioral_embedding=bspec_data.get("behavioral_embedding", []),
            embedding_confidence=bspec_data.get("embedding_confidence", "missing"),
            spec_superseded_by=bspec_data.get("spec_superseded_by"),
            tested_input_output_pairs=bspec_data.get("tested_input_output_pairs", []),
        )

        meta_data = data.get("layer_meta", {})
        layer_meta = LayerMeta(
            dependent_workflows=meta_data.get("dependent_workflows", []),
            install_scope=meta_data.get("install_scope", "global"),
            agent_id=meta_data.get("agent_id"),
            installed_at=meta_data.get(
                "installed_at",
                datetime.utcnow().isoformat() + "Z",
            ),
            version_pin_strategy=meta_data.get("version_pin_strategy", "minor"),
        )

        return cls(
            tool_id=data.get("tool_id", ""),
            name=data.get("name", ""),
            version=data.get("version", ""),
            dependencies=data.get("dependencies", {}),
            layer_1_domain_tags=data.get("layer_1_domain_tags", []),
            layer_2_vector_signature=data.get("layer_2_vector_signature", []),
            layer_3_capabilities=caps,
            layer_4_telemetry=telemetry,
            layer_5_provenance=provenance,
            layer_6_behavior_spec=behavior_spec,
            layer_meta=layer_meta,
        )

    def to_dict(self) -> dict:
        """Serialize to a JSON-compatible dict."""
        return {
            "tool_id": self.tool_id,
            "name": self.name,
            "version": self.version,
            "dependencies": copy.deepcopy(self.dependencies),
            "layer_1_domain_tags": list(self.layer_1_domain_tags),
            "layer_2_vector_signature": list(self.layer_2_vector_signature),
            "layer_3_capabilities": {
                "inputs": list(self.layer_3_capabilities.inputs),
                "outputs": list(self.layer_3_capabilities.outputs),
                "permissions": list(self.layer_3_capabilities.permissions),
                "extensible": self.layer_3_capabilities.extensible,
            },
            "layer_4_telemetry": {
                "virtual_env_isolated": self.layer_4_telemetry.virtual_env_isolated,
                "average_execution_ms": self.layer_4_telemetry.average_execution_ms,
                "last_known_stable_state_hash": self.layer_4_telemetry.last_known_stable_state_hash,
                "health_check_endpoint": self.layer_4_telemetry.health_check_endpoint,
                "last_health_check_passed": self.layer_4_telemetry.last_health_check_passed,
            },
            "layer_5_provenance": {
                "publisher_id": self.layer_5_provenance.publisher_id,
                "signature_hash": self.layer_5_provenance.signature_hash,
                "signature_verified": self.layer_5_provenance.signature_verified,
                "trust_score": self.layer_5_provenance.trust_score,
                "trust_factors": {
                    "publisher_known": self.layer_5_provenance.trust_factors.publisher_known,
                    "github_stars": self.layer_5_provenance.trust_factors.github_stars,
                    "last_commit_days_ago": self.layer_5_provenance.trust_factors.last_commit_days_ago,
                    "open_critical_cves": self.layer_5_provenance.trust_factors.open_critical_cves,
                    "community_sentiment_score": self.layer_5_provenance.trust_factors.community_sentiment_score,
                },
                "install_source": self.layer_5_provenance.install_source,
                "published_at": self.layer_5_provenance.published_at,
                "trust_score_last_evaluated": self.layer_5_provenance.trust_score_last_evaluated,
            },
            "layer_6_behavior_spec": {
                "tool_type": self.layer_6_behavior_spec.tool_type,
                "declared_behaviors": list(self.layer_6_behavior_spec.declared_behaviors),
                "known_nondeterminism": self.layer_6_behavior_spec.known_nondeterminism,
                "behavioral_embedding": list(self.layer_6_behavior_spec.behavioral_embedding),
                "embedding_confidence": self.layer_6_behavior_spec.embedding_confidence,
                "spec_superseded_by": self.layer_6_behavior_spec.spec_superseded_by,
                "tested_input_output_pairs": copy.deepcopy(
                    self.layer_6_behavior_spec.tested_input_output_pairs
                ),
            },
            "layer_meta": {
                "dependent_workflows": list(self.layer_meta.dependent_workflows),
                "install_scope": self.layer_meta.install_scope,
                "agent_id": self.layer_meta.agent_id,
                "installed_at": self.layer_meta.installed_at,
                "version_pin_strategy": self.layer_meta.version_pin_strategy,
            },
        }
