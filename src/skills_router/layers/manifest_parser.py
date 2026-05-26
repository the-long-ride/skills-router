"""Layer 1 — JSON Manifest Parser.

Validates and normalises raw tool manifests before they enter the pipeline.
"""

from __future__ import annotations

import re
from typing import Any

from packaging.version import Version, InvalidVersion

# Valid tool_id: lowercase alphanumeric, hyphens, max 128 chars
_TOOL_ID_RE = re.compile(r"^[a-z0-9][a-z0-9\-]{0,126}[a-z0-9]$")

# Required top-level fields in a tool manifest
REQUIRED_FIELDS = {"tool_id", "name", "version"}

# Fields that should be dicts
DICT_FIELDS = {
    "dependencies",
    "layer_3_capabilities",
    "layer_4_telemetry",
    "layer_5_provenance",
    "layer_6_behavior_spec",
    "layer_meta",
}

# Fields that should be lists
LIST_FIELDS = {"layer_1_domain_tags"}


class ManifestParseError(ValueError):
    """Raised when a manifest fails validation."""


class ManifestParser:
    """Validates and normalises raw tool manifests."""

    def parse(self, raw: str | dict) -> dict:
        """Parse and validate a tool manifest.

        Args:
            raw: Either a JSON string or an already-parsed dict.

        Returns:
            Normalised manifest dict ready for pipeline consumption.

        Raises:
            ManifestParseError: If validation fails.
        """
        import json

        if isinstance(raw, str):
            try:
                data = json.loads(raw)
            except json.JSONDecodeError as e:
                raise ManifestParseError(f"Invalid JSON: {e}") from e
        elif isinstance(raw, dict):
            data = dict(raw)
        else:
            raise ManifestParseError(
                f"Expected str or dict, got {type(raw).__name__}"
            )

        self._validate(data)
        return self._normalise(data)

    def _validate(self, data: dict) -> None:
        """Check required fields and types."""
        missing = REQUIRED_FIELDS - set(data.keys())
        if missing:
            raise ManifestParseError(f"Missing required fields: {missing}")

        # Validate tool_id format
        tool_id = data["tool_id"]
        if not isinstance(tool_id, str) or not _TOOL_ID_RE.match(tool_id):
            raise ManifestParseError(
                f"Invalid tool_id '{tool_id}': must be 2-128 chars, "
                f"lowercase alphanumeric and hyphens only, "
                f"starting and ending with alphanumeric"
            )

        # Validate version is valid semver / PEP 440
        version = data["version"]
        try:
            Version(version)
        except InvalidVersion:
            raise ManifestParseError(
                f"Invalid version '{version}': must be PEP 440 compliant "
                f"(e.g. '1.0.0', '2.1.0rc1')"
            )

        # Dependency specifier validity is checked by DependencyConflictResolver
        # so parse errors can be surfaced in a human-readable WG decision.
        deps = data.get("dependencies", {})
        if deps is not None and not isinstance(deps, dict):
            raise ManifestParseError(
                f"Field 'dependencies' must be a dict, got {type(deps).__name__}"
            )

        for field_name in DICT_FIELDS:
            if field_name in data and not isinstance(data[field_name], dict):
                raise ManifestParseError(
                    f"Field '{field_name}' must be a dict, "
                    f"got {type(data[field_name]).__name__}"
                )

        for field_name in LIST_FIELDS:
            if field_name in data and not isinstance(data[field_name], list):
                raise ManifestParseError(
                    f"Field '{field_name}' must be a list, "
                    f"got {type(data[field_name]).__name__}"
                )

    def _normalise(self, data: dict) -> dict:
        """Fill in defaults for optional layers."""
        data.setdefault("dependencies", {})
        data.setdefault("layer_1_domain_tags", [])
        data.setdefault("layer_2_vector_signature", [])
        data.setdefault("layer_3_capabilities", {
            "inputs": [],
            "outputs": [],
            "permissions": [],
            "extensible": False,
        })
        data.setdefault("layer_4_telemetry", {
            "virtual_env_isolated": False,
            "average_execution_ms": 0,
            "last_known_stable_state_hash": "",
            "health_check_endpoint": "/healthz",
            "last_health_check_passed": None,
        })
        data.setdefault("layer_5_provenance", {
            "publisher_id": "",
            "signature_hash": "",
            "signature_verified": False,
            "trust_score": 0.0,
            "trust_factors": {},
            "install_source": "unknown",
            "published_at": "",
            "trust_score_last_evaluated": "",
        })
        data.setdefault("layer_6_behavior_spec", {
            "tool_type": "api_wrapper",
            "declared_behaviors": [],
            "known_nondeterminism": "",
            "behavioral_embedding": [],
            "embedding_confidence": "missing",
            "spec_superseded_by": None,
            "tested_input_output_pairs": [],
        })
        data.setdefault("layer_meta", {
            "dependent_workflows": [],
            "install_scope": "global",
            "agent_id": None,
            "installed_at": "",
            "version_pin_strategy": "minor",
        })

        # Normalise capabilities sub-fields
        caps = data["layer_3_capabilities"]
        caps.setdefault("inputs", [])
        caps.setdefault("outputs", [])
        caps.setdefault("permissions", [])
        caps.setdefault("extensible", False)

        return data

    def build_trust_manifest(self, data: dict) -> dict:
        """Extract fields needed by TrustGate.evaluate() from a parsed manifest.

        Maps the multi-layer schema to the flat manifest format TrustGate expects.
        """
        prov = data.get("layer_5_provenance", {})
        tf = prov.get("trust_factors", {})
        return {
            "publisher_signature": {
                "verified": prov.get("signature_verified", False),
            },
            "install_source": prov.get("install_source", "unknown"),
            "open_critical_cves": tf.get("open_critical_cves", 0),
            "last_commit_days_ago": tf.get("last_commit_days_ago", 999),
            "community_sentiment_score": tf.get("community_sentiment_score", 0.5),
        }
