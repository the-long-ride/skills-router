"""Tests for HealthChecker validation behavior."""

from skills_router.layers.health_check import HealthChecker


def test_health_check_passes_for_valid_record():
    checker = HealthChecker()
    tool = {
        "layer_4_telemetry": {"health_check_endpoint": "/healthz"},
        "layer_6_behavior_spec": {
            "tested_input_output_pairs": [
                {"input": {"query": "ok"}, "expected_output": {"status": "ok"}}
            ]
        },
    }
    result = checker.check(tool)
    assert result["status"] == "PASS"


def test_health_check_accepts_expected_output_schema():
    checker = HealthChecker()
    tool = {
        "layer_4_telemetry": {"health_check_endpoint": "/healthz"},
        "layer_6_behavior_spec": {
            "tested_input_output_pairs": [
                {
                    "input": {"zipcode": "10001"},
                    "expected_output_schema": {
                        "temperature": "float",
                        "forecast": "string",
                    },
                }
            ]
        },
    }
    result = checker.check(tool)
    assert result["status"] == "PASS"


def test_health_check_fails_for_invalid_endpoint():
    checker = HealthChecker()
    tool = {
        "layer_4_telemetry": {"health_check_endpoint": "ftp://bad-endpoint"},
        "layer_6_behavior_spec": {"tested_input_output_pairs": []},
    }
    result = checker.check(tool)
    assert result["status"] == "FAIL"
    assert "health_check_endpoint" in result["details"]


def test_health_check_fails_for_non_list_test_pairs():
    checker = HealthChecker()
    tool = {
        "layer_4_telemetry": {"health_check_endpoint": "/healthz"},
        "layer_6_behavior_spec": {"tested_input_output_pairs": {"input": 1}},
    }
    result = checker.check(tool)
    assert result["status"] == "FAIL"
    assert "tested_input_output_pairs" in result["details"]


def test_health_check_fails_for_pair_without_input():
    checker = HealthChecker()
    tool = {
        "layer_4_telemetry": {"health_check_endpoint": "/healthz"},
        "layer_6_behavior_spec": {
            "tested_input_output_pairs": [{"expected_output": {"ok": True}}]
        },
    }
    result = checker.check(tool)
    assert result["status"] == "FAIL"
    assert "missing 'input'" in result["details"]


def test_health_check_fails_for_pair_without_expectation():
    checker = HealthChecker()
    tool = {
        "layer_4_telemetry": {"health_check_endpoint": "/healthz"},
        "layer_6_behavior_spec": {"tested_input_output_pairs": [{"input": {"x": 1}}]},
    }
    result = checker.check(tool)
    assert result["status"] == "FAIL"
    assert "missing expected_output/expected_output_schema" in result["details"]


def test_health_check_uses_endpoint_probe():
    checker = HealthChecker(endpoint_probe=lambda endpoint, _tool: (endpoint == "/ok", "probe"))
    tool = {
        "layer_4_telemetry": {"health_check_endpoint": "/bad"},
        "layer_6_behavior_spec": {"tested_input_output_pairs": []},
    }
    result = checker.check(tool)
    assert result["status"] == "FAIL"
    assert "Endpoint probe failed" in result["details"]
