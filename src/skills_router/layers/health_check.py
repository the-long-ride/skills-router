"""Layer 5 — Post-install health checks."""

from __future__ import annotations

from collections.abc import Callable
from urllib.parse import urlparse


class HealthChecker:
    """Validate post-install health metadata and optional endpoint probes."""

    def __init__(
        self,
        endpoint_probe: Callable[[str, dict], tuple[bool, str]] | None = None,
    ):
        self._endpoint_probe = endpoint_probe

    def check(self, tool_record: dict) -> dict:
        """Run health check on an installed tool.

        Args:
            tool_record: The full Brain Index entry dict.

        Returns:
            {"status": "PASS" | "FAIL", "details": str}
        """
        endpoint = (
            tool_record.get("layer_4_telemetry", {})
            .get("health_check_endpoint", "/healthz")
        )
        endpoint_ok, endpoint_reason = self._validate_endpoint(endpoint)
        if not endpoint_ok:
            return {"status": "FAIL", "details": endpoint_reason}

        tested_pairs = (
            tool_record.get("layer_6_behavior_spec", {})
            .get("tested_input_output_pairs", [])
        )
        pairs_ok, pairs_reason = self._validate_test_pairs(tested_pairs)
        if not pairs_ok:
            return {"status": "FAIL", "details": pairs_reason}

        details = (
            "Static health checks passed "
            f"(endpoint: {endpoint}, test_pairs: {len(tested_pairs)})."
        )

        if self._endpoint_probe is not None:
            probe_ok, probe_reason = self._endpoint_probe(endpoint, tool_record)
            if not probe_ok:
                return {"status": "FAIL", "details": f"Endpoint probe failed: {probe_reason}"}
            details = f"{details} Endpoint probe passed: {probe_reason}"

        return {
            "status": "PASS",
            "details": details,
        }

    @staticmethod
    def _validate_endpoint(endpoint: object) -> tuple[bool, str]:
        if not isinstance(endpoint, str):
            return False, "Invalid health_check_endpoint: expected a string."

        endpoint_value = endpoint.strip()
        if not endpoint_value:
            return False, "Invalid health_check_endpoint: value cannot be empty."

        if endpoint_value.startswith("/"):
            return True, "ok"

        parsed = urlparse(endpoint_value)
        if parsed.scheme in ("http", "https") and parsed.netloc:
            return True, "ok"

        return (
            False,
            "Invalid health_check_endpoint: use '/path' or an absolute http(s) URL.",
        )

    @staticmethod
    def _validate_test_pairs(pairs: object) -> tuple[bool, str]:
        if not isinstance(pairs, list):
            return False, "Invalid tested_input_output_pairs: expected a list."

        for idx, pair in enumerate(pairs):
            if not isinstance(pair, dict):
                return (
                    False,
                    f"Invalid tested_input_output_pairs[{idx}]: expected an object.",
                )

            if "input" not in pair:
                return (
                    False,
                    f"Invalid tested_input_output_pairs[{idx}]: missing 'input'.",
                )

            has_expectation = any(
                key in pair
                for key in (
                    "expected_output",
                    "expected_output_schema",
                    "expected_error",
                    "assertions",
                )
            )
            if not has_expectation:
                return (
                    False,
                    "Invalid tested_input_output_pairs"
                    f"[{idx}]: missing expected_output/expected_output_schema/"
                    "expected_error/assertions.",
                )

            if "assertions" in pair and not isinstance(pair["assertions"], list):
                return (
                    False,
                    f"Invalid tested_input_output_pairs[{idx}]: "
                    "'assertions' must be a list when provided.",
                )

        return True, "ok"
