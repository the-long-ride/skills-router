"""Shared test fixtures for skills-router."""

from __future__ import annotations

import os
import tempfile

import pytest

from skills_router.config import SkillsRouterConfig
from skills_router.storage.memory_store import MemoryBrainIndexStore


@pytest.fixture
def tmp_data_dir(tmp_path):
    """Create a temporary data directory for tests."""
    data_dir = str(tmp_path / "skills-router-test")
    os.makedirs(data_dir, exist_ok=True)
    return data_dir


@pytest.fixture
def config(tmp_data_dir):
    """Create a test config pointing to tmp_data_dir."""
    return SkillsRouterConfig(data_dir=tmp_data_dir)


@pytest.fixture
def store(config):
    """Create a memory store backed by test config paths."""
    return MemoryBrainIndexStore(
        brain_index_path=config.brain_index_path,
        dep_graph_path=config.dep_graph_path,
    )


@pytest.fixture
def weather_manifest():
    """Sample weather tool manifest."""
    return {
        "tool_id": "global-meteo-suite",
        "name": "GlobalMeteo Suite",
        "version": "2.1.0",
        "dependencies": {
            "requests": ">=2.25.0",
            "numpy": "==1.21.0",
        },
        "layer_1_domain_tags": ["Data:API", "Weather", "Location"],
        "layer_3_capabilities": {
            "inputs": ["coordinates: float", "zipcode: string"],
            "outputs": ["temperature: float", "radar_image: bytes", "forecast: dict"],
            "permissions": ["network: outbound_https", "system: read_env_vars"],
            "extensible": False,
        },
        "layer_4_telemetry": {
            "virtual_env_isolated": True,
            "average_execution_ms": 1450,
            "last_known_stable_state_hash": "a8f9c21def",
            "health_check_endpoint": "/healthz",
        },
        "layer_5_provenance": {
            "publisher_id": "meteo-org",
            "signature_hash": "sha256:3f2a...",
            "signature_verified": True,
            "trust_score": 0.91,
            "trust_factors": {
                "publisher_known": True,
                "github_stars": 4200,
                "last_commit_days_ago": 12,
                "open_critical_cves": 0,
                "community_sentiment_score": 0.84,
            },
            "install_source": "official-registry",
            "published_at": "2024-01-10T00:00:00Z",
            "trust_score_last_evaluated": "2024-01-15T10:00:00Z",
        },
        "layer_6_behavior_spec": {
            "tool_type": "api_wrapper",
            "declared_behaviors": [
                "Returns structured weather JSON",
                "Does not store user location data",
            ],
            "known_nondeterminism": "",
            "behavioral_embedding": [],
            "embedding_confidence": "verified",
            "spec_superseded_by": None,
            "tested_input_output_pairs": [],
        },
        "layer_meta": {
            "dependent_workflows": ["daily-brief-agent"],
            "install_scope": "global",
            "agent_id": None,
            "installed_at": "2024-01-15T09:00:00Z",
            "version_pin_strategy": "minor",
        },
    }


@pytest.fixture
def duplicate_weather_manifest():
    """Near-duplicate weather tool for overlap testing."""
    return {
        "tool_id": "weather-pro-plus",
        "name": "WeatherPro Plus",
        "version": "3.0.0",
        "dependencies": {
            "requests": ">=2.28.0",
            "numpy": ">=1.21.0",
        },
        "layer_1_domain_tags": ["Data:API", "Weather", "Location", "Alerts"],
        "layer_3_capabilities": {
            "inputs": ["coordinates: float", "zipcode: string", "alert_region: string"],
            "outputs": [
                "temperature: float", "radar_image: bytes",
                "forecast: dict", "severe_alerts: list",
            ],
            "permissions": [
                "network: outbound_https", "system: read_env_vars",
                "notifications: push",
            ],
            "extensible": True,
        },
        "layer_5_provenance": {
            "publisher_id": "weatherpro-inc",
            "signature_verified": True,
            "trust_score": 0.85,
            "trust_factors": {
                "last_commit_days_ago": 5,
                "open_critical_cves": 0,
                "community_sentiment_score": 0.79,
            },
            "install_source": "official-registry",
        },
        "layer_6_behavior_spec": {
            "tool_type": "api_wrapper",
            "declared_behaviors": [],
            "behavioral_embedding": [],
            "embedding_confidence": "verified",
        },
        "layer_meta": {
            "install_scope": "global",
        },
    }


@pytest.fixture
def untrusted_manifest():
    """Manifest with low trust score."""
    return {
        "tool_id": "sketchy-tool",
        "name": "Sketchy Tool",
        "version": "0.1.0",
        "layer_5_provenance": {
            "signature_verified": False,
            "trust_score": 0.10,
            "trust_factors": {
                "open_critical_cves": 3,
                "last_commit_days_ago": 500,
                "community_sentiment_score": 0.1,
            },
            "install_source": "unknown",
        },
    }
