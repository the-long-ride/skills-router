"""Tests for SkillsRouterLockfile."""

from skills_router.layers.lockfile import SkillsRouterLockfile


def test_lockfile_upsert_and_remove(tmp_path):
    lockfile = SkillsRouterLockfile(str(tmp_path / "skills-router.lock.json"))
    tool = {
        "tool_id": "weather-tool",
        "name": "Weather",
        "version": "1.2.3",
        "layer_meta": {
            "resolved_source": "registry",
            "resolved_identifier": "weather-tool",
            "resolved_version": "1.2.3",
            "resolved_url": "https://registry.example/weather-tool/1.2.3.json",
            "resolved_sha256": "abc123",
        },
    }

    lockfile.upsert(tool, requested="weather-tool@1.2.3", scope="global")
    data = lockfile.read()

    assert data["tools"]["weather-tool"]["resolved_sha256"] == "abc123"
    assert data["tools"]["weather-tool"]["requested"] == "weather-tool@1.2.3"

    lockfile.remove("weather-tool")
    assert "weather-tool" not in lockfile.read()["tools"]
