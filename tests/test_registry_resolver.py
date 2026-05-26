"""Tests for RegistryResolver."""

from __future__ import annotations

import json
import os
import urllib.error
from unittest.mock import MagicMock, patch

import pytest

from skills_router.config import SkillsRouterConfig
from skills_router.layers.registry_resolver import (
    RegistryResolutionError,
    RegistryResolver,
)


def test_resolve_local_file(tmp_path):
    """Test resolving a local manifest file that exists."""
    config = SkillsRouterConfig(data_dir=str(tmp_path))
    resolver = RegistryResolver(config)

    manifest_data = {"tool_id": "test-tool", "name": "Test Tool", "version": "1.0.0"}
    local_file = tmp_path / "test_tool.json"
    with open(local_file, "w") as f:
        json.dump(manifest_data, f)

    result = resolver.resolve(str(local_file))
    assert result["tool_id"] == "test-tool"
    assert result["version"] == "1.0.0"


def test_resolve_invalid_local_file(tmp_path):
    """Test resolving a local manifest file that has invalid JSON."""
    config = SkillsRouterConfig(data_dir=str(tmp_path))
    resolver = RegistryResolver(config)

    local_file = tmp_path / "invalid.json"
    with open(local_file, "w") as f:
        f.write("{invalid-json}")

    with pytest.raises(RegistryResolutionError) as exc_info:
        resolver.resolve(str(local_file))
    assert "Failed to parse local manifest file" in str(exc_info.value)


@patch("urllib.request.urlopen")
def test_missing_path_like_manifest_does_not_fetch_remote(mock_urlopen, tmp_path):
    """A typo in a manifest path should fail as a path, not become a package lookup."""
    config = SkillsRouterConfig(data_dir=str(tmp_path))
    resolver = RegistryResolver(config)

    with pytest.raises(RegistryResolutionError) as exc_info:
        resolver.resolve(str(tmp_path / "missing.json"))

    assert "Local manifest file not found" in str(exc_info.value)
    mock_urlopen.assert_not_called()


def test_resolve_invalid_package_names(tmp_path):
    """Test validating package names before remote lookup."""
    config = SkillsRouterConfig(data_dir=str(tmp_path))
    resolver = RegistryResolver(config)

    invalid_names = [
        "some tool",
        "tool$name",
        "",
    ]
    for name in invalid_names:
        with pytest.raises(RegistryResolutionError) as exc_info:
            resolver.resolve(name)
        assert "Invalid package name or path" in str(exc_info.value)

    path_like_names = ["../test", "tool/name"]
    for name in path_like_names:
        with pytest.raises(RegistryResolutionError) as exc_info:
            resolver.resolve(name)
        assert "Local manifest file not found" in str(exc_info.value)


@patch("urllib.request.urlopen")
def test_resolve_remote_success(mock_urlopen, tmp_path):
    """Test fetching package successfully from remote registry and caching it."""
    config = SkillsRouterConfig(data_dir=str(tmp_path))
    resolver = RegistryResolver(config)

    manifest_data = {
        "tool_id": "weather-tool",
        "name": "Weather Tool",
        "version": "1.2.3",
    }

    # Mock urllib response
    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps(manifest_data).encode("utf-8")
    mock_response.__enter__.return_value = mock_response
    mock_urlopen.return_value = mock_response

    # Verify resolution
    result = resolver.resolve("weather-tool")
    assert result["tool_id"] == "weather-tool"
    assert result["version"] == "1.2.3"

    # Verify mock was called with correct registry URL
    mock_urlopen.assert_called_once()
    req = mock_urlopen.call_args[0][0]
    assert req.full_url == f"{config.registry_base_url}/weather-tool.json"

    # Verify it got saved to local cache
    cache_file = resolver._cache_file("weather-tool")
    assert cache_file.exists()
    with open(cache_file) as f:
        cached_data = json.load(f)
    assert cached_data["tool_id"] == "weather-tool"
    assert cached_data["layer_meta"]["resolved_source"] == "registry"
    assert cached_data["layer_meta"]["resolved_sha256"]


@patch("urllib.request.urlopen")
def test_resolve_remote_version_pin(mock_urlopen, tmp_path):
    """name@version should resolve to a versioned registry URL."""
    config = SkillsRouterConfig(data_dir=str(tmp_path))
    resolver = RegistryResolver(config)

    manifest_data = {
        "tool_id": "weather-tool",
        "name": "Weather Tool",
        "version": "1.2.3",
    }
    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps(manifest_data).encode("utf-8")
    mock_response.__enter__.return_value = mock_response
    mock_urlopen.return_value = mock_response

    result = resolver.resolve("weather-tool@1.2.3")

    req = mock_urlopen.call_args[0][0]
    assert req.full_url == f"{config.registry_base_url}/weather-tool/1.2.3.json"
    assert result["layer_meta"]["resolved_version"] == "1.2.3"


@patch("urllib.request.urlopen")
def test_resolve_github_owner_repo(mock_urlopen, tmp_path):
    """github:owner/repo should resolve a raw GitHub manifest."""
    config = SkillsRouterConfig(data_dir=str(tmp_path))
    config.github_manifest_paths = ["skills-router.json"]
    resolver = RegistryResolver(config)

    manifest_data = {
        "tool_id": "github-tool",
        "name": "GitHub Tool",
        "version": "0.1.0",
    }
    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps(manifest_data).encode("utf-8")
    mock_response.__enter__.return_value = mock_response
    mock_urlopen.return_value = mock_response

    result = resolver.resolve("github:owner/repo")

    req = mock_urlopen.call_args[0][0]
    assert req.full_url == (
        "https://raw.githubusercontent.com/owner/repo/main/skills-router.json"
    )
    assert result["layer_meta"]["resolved_source"] == "github"
    assert result["layer_meta"]["resolved_identifier"] == "owner/repo"


def test_resolve_invalid_github_spec(tmp_path):
    config = SkillsRouterConfig(data_dir=str(tmp_path))
    resolver = RegistryResolver(config)

    with pytest.raises(RegistryResolutionError) as exc_info:
        resolver.resolve("github:owner")

    assert "Invalid GitHub package spec" in str(exc_info.value)


@patch("urllib.request.urlopen")
def test_resolve_uses_cache(mock_urlopen, tmp_path):
    """Test that resolving checking cache directory bypasses remote fetch."""
    config = SkillsRouterConfig(data_dir=str(tmp_path))
    resolver = RegistryResolver(config)

    manifest_data = {
        "tool_id": "cached-tool",
        "name": "Cached Tool",
        "version": "0.9.0",
    }

    # Pre-populate cache
    cache_file = resolver._cache_file("cached-tool")
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    with open(cache_file, "w") as f:
        json.dump(manifest_data, f)

    # Verify resolution doesn't fetch url
    result = resolver.resolve("cached-tool")
    assert result["tool_id"] == "cached-tool"
    mock_urlopen.assert_not_called()


@patch("urllib.request.urlopen")
def test_resolve_remote_404(mock_urlopen, tmp_path):
    """Test resolving a non-existent package triggers HTTP 404 error."""
    config = SkillsRouterConfig(data_dir=str(tmp_path))
    resolver = RegistryResolver(config)

    # Mock HTTP 404 error
    mock_urlopen.side_effect = urllib.error.HTTPError(
        url="http://test.url",
        code=404,
        msg="Not Found",
        hdrs=MagicMock(),
        fp=MagicMock(),
    )

    with pytest.raises(RegistryResolutionError) as exc_info:
        resolver.resolve("missing-tool")
    assert "not found in registry" in str(exc_info.value)


@patch("urllib.request.urlopen")
def test_resolve_remote_invalid_json(mock_urlopen, tmp_path):
    """Test resolving when remote server returns invalid JSON."""
    config = SkillsRouterConfig(data_dir=str(tmp_path))
    resolver = RegistryResolver(config)

    # Mock response with bad JSON
    mock_response = MagicMock()
    mock_response.read.return_value = b"{bad-json}"
    mock_response.__enter__.return_value = mock_response
    mock_urlopen.return_value = mock_response

    with pytest.raises(RegistryResolutionError) as exc_info:
        resolver.resolve("bad-json-tool")
    assert "invalid JSON" in str(exc_info.value)


@patch("urllib.request.urlopen")
def test_resolve_rejects_insecure_non_local_registry(mock_urlopen, tmp_path):
    """Remote registry fetches should fail closed when HTTPS is not configured."""
    config = SkillsRouterConfig(data_dir=str(tmp_path))
    config.registry_base_url = "http://registry.example.com/packages"
    resolver = RegistryResolver(config)

    with pytest.raises(RegistryResolutionError) as exc_info:
        resolver.resolve("weather-tool")

    assert "must use HTTPS" in str(exc_info.value)
    mock_urlopen.assert_not_called()


@patch("urllib.request.urlopen")
def test_resolve_rejects_oversized_manifest(mock_urlopen, tmp_path):
    """Remote manifests are bounded to avoid unbounded memory reads."""
    config = SkillsRouterConfig(data_dir=str(tmp_path))
    config.registry_max_manifest_bytes = 8
    resolver = RegistryResolver(config)

    mock_response = MagicMock()
    mock_response.read.return_value = b'{"tool": "too-large"}'
    mock_response.__enter__.return_value = mock_response
    mock_urlopen.return_value = mock_response

    with pytest.raises(RegistryResolutionError) as exc_info:
        resolver.resolve("large-tool")

    assert "exceeds" in str(exc_info.value)


@patch("urllib.request.urlopen")
def test_resolve_rejects_non_json_content_type(mock_urlopen, tmp_path):
    """HTML error pages should not be treated as registry manifests."""
    config = SkillsRouterConfig(data_dir=str(tmp_path))
    resolver = RegistryResolver(config)

    mock_response = MagicMock()
    mock_response.headers = {"Content-Type": "text/html"}
    mock_response.read.return_value = b"<html></html>"
    mock_response.__enter__.return_value = mock_response
    mock_urlopen.return_value = mock_response

    with pytest.raises(RegistryResolutionError) as exc_info:
        resolver.resolve("html-tool")

    assert "unsupported content type" in str(exc_info.value)


@patch("urllib.request.urlopen")
def test_resolve_rejects_non_object_manifest(mock_urlopen, tmp_path):
    """Registry manifests must be JSON objects, not arrays or scalar values."""
    config = SkillsRouterConfig(data_dir=str(tmp_path))
    resolver = RegistryResolver(config)

    mock_response = MagicMock()
    mock_response.read.return_value = b'["not", "a", "manifest"]'
    mock_response.__enter__.return_value = mock_response
    mock_urlopen.return_value = mock_response

    with pytest.raises(RegistryResolutionError) as exc_info:
        resolver.resolve("array-tool")

    assert "non-object manifest" in str(exc_info.value)


@patch("urllib.request.urlopen")
def test_cache_is_scoped_by_registry_base_url(mock_urlopen, tmp_path):
    """Cached package names from one registry should not shadow another registry."""
    config_a = SkillsRouterConfig(data_dir=str(tmp_path))
    resolver_a = RegistryResolver(config_a)
    cache_file_a = resolver_a._cache_file("weather-tool")
    cache_file_a.parent.mkdir(parents=True, exist_ok=True)
    with open(cache_file_a, "w") as f:
        json.dump({"tool_id": "from-a", "name": "A", "version": "1.0.0"}, f)

    config_b = SkillsRouterConfig(data_dir=str(tmp_path))
    config_b.registry_base_url = "https://alt-registry.example.com/packages"
    resolver_b = RegistryResolver(config_b)

    manifest_data = {"tool_id": "from-b", "name": "B", "version": "2.0.0"}
    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps(manifest_data).encode("utf-8")
    mock_response.__enter__.return_value = mock_response
    mock_urlopen.return_value = mock_response

    result = resolver_b.resolve("weather-tool")

    assert result["tool_id"] == "from-b"
    mock_urlopen.assert_called_once()


@patch("urllib.request.urlopen")
def test_expired_cache_fetches_fresh_manifest(mock_urlopen, tmp_path):
    """Expired cache entries should not hide registry updates or removals."""
    config = SkillsRouterConfig(data_dir=str(tmp_path))
    config.registry_cache_ttl_seconds = 1
    resolver = RegistryResolver(config)

    cache_file = resolver._cache_file("weather-tool")
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    with open(cache_file, "w") as f:
        json.dump({"tool_id": "stale", "name": "Stale", "version": "1.0.0"}, f)
    old_time = 1_700_000_000
    os.utime(cache_file, (old_time, old_time))

    manifest_data = {"tool_id": "fresh", "name": "Fresh", "version": "2.0.0"}
    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps(manifest_data).encode("utf-8")
    mock_response.__enter__.return_value = mock_response
    mock_urlopen.return_value = mock_response

    result = resolver.resolve("weather-tool")

    assert result["tool_id"] == "fresh"
    mock_urlopen.assert_called_once()
