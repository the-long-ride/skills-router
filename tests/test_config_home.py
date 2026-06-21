"""Tests for home directory resolution in SkillsRouterConfig."""

from __future__ import annotations

import os
import tempfile

import pytest


@pytest.fixture
def clean_home_env(monkeypatch):
    """Remove SKILLS_ROUTER_HOME env var and ~/.skills-router-home influence."""
    monkeypatch.delenv("SKILLS_ROUTER_HOME", raising=False)
    yield


def test_default_home_is_dot_skills_router(clean_home_env, monkeypatch, tmp_path):
    """When no env var or home file exists, data_dir defaults to ~/.skills-router."""
    from skills_router.config import SkillsRouterConfig

    home_dir = tmp_path / "fake-home"
    home_dir.mkdir()
    monkeypatch.setattr("skills_router.config.Path.home", lambda: home_dir)

    config = SkillsRouterConfig()
    expected = str(home_dir / ".skills-router")
    assert config.data_dir == expected


def test_env_var_overrides_default(clean_home_env, monkeypatch, tmp_path):
    """SKILLS_ROUTER_HOME env var takes highest priority."""
    from skills_router.config import SkillsRouterConfig

    custom_home = tmp_path / "custom-skills-home"
    custom_home.mkdir()
    monkeypatch.setenv("SKILLS_ROUTER_HOME", str(custom_home))

    config = SkillsRouterConfig()
    assert config.data_dir == str(custom_home)


def test_home_file_overrides_default(clean_home_env, monkeypatch, tmp_path):
    """~/.skills-router-home file sets the home directory."""
    from skills_router.config import SkillsRouterConfig

    home_dir = tmp_path / "fake-home"
    home_dir.mkdir()
    custom_home = tmp_path / "from-file-home"
    custom_home.mkdir()

    home_file = home_dir / ".skills-router-home"
    home_file.write_text(str(custom_home))

    monkeypatch.setattr("skills_router.config.Path.home", lambda: home_dir)

    config = SkillsRouterConfig()
    assert config.data_dir == str(custom_home)


def test_env_var_beats_home_file(clean_home_env, monkeypatch, tmp_path):
    """SKILLS_ROUTER_HOME env var beats ~/.skills-router-home file."""
    from skills_router.config import SkillsRouterConfig

    home_dir = tmp_path / "fake-home"
    home_dir.mkdir()
    env_home = tmp_path / "env-home"
    env_home.mkdir()
    file_home = tmp_path / "file-home"
    file_home.mkdir()

    home_file = home_dir / ".skills-router-home"
    home_file.write_text(str(file_home))

    monkeypatch.setattr("skills_router.config.Path.home", lambda: home_dir)
    monkeypatch.setenv("SKILLS_ROUTER_HOME", str(env_home))

    config = SkillsRouterConfig()
    assert config.data_dir == str(env_home)


def test_data_dir_cli_arg_beats_all(clean_home_env, monkeypatch, tmp_path):
    """--data-dir CLI arg beats env var and home file."""
    from skills_router.config import SkillsRouterConfig

    home_dir = tmp_path / "fake-home"
    home_dir.mkdir()
    cli_home = tmp_path / "cli-home"
    cli_home.mkdir()
    env_home = tmp_path / "env-home"
    env_home.mkdir()

    home_file = home_dir / ".skills-router-home"
    home_file.write_text(str(tmp_path / "file-home"))

    monkeypatch.setattr("skills_router.config.Path.home", lambda: home_dir)
    monkeypatch.setenv("SKILLS_ROUTER_HOME", str(env_home))

    config = SkillsRouterConfig(data_dir=str(cli_home))
    assert config.data_dir == str(cli_home)


def test_home_file_nonexistent_path_uses_default(clean_home_env, monkeypatch, tmp_path):
    """If the path in home file doesn't exist, still use it (let caller handle)."""
    from skills_router.config import SkillsRouterConfig

    home_dir = tmp_path / "fake-home"
    home_dir.mkdir()
    nonexistent = tmp_path / "does-not-exist-yet"

    home_file = home_dir / ".skills-router-home"
    home_file.write_text(str(nonexistent))

    monkeypatch.setattr("skills_router.config.Path.home", lambda: home_dir)

    config = SkillsRouterConfig()
    assert config.data_dir == str(nonexistent)


def test_home_file_empty_uses_default(clean_home_env, monkeypatch, tmp_path):
    """Empty home file falls back to default."""
    from skills_router.config import SkillsRouterConfig

    home_dir = tmp_path / "fake-home"
    home_dir.mkdir()

    home_file = home_dir / ".skills-router-home"
    home_file.write_text("")

    monkeypatch.setattr("skills_router.config.Path.home", lambda: home_dir)

    config = SkillsRouterConfig()
    expected = str(home_dir / ".skills-router")
    assert config.data_dir == expected


def test_home_file_whitespace_only_uses_default(clean_home_env, monkeypatch, tmp_path):
    """Whitespace-only home file falls back to default."""
    from skills_router.config import SkillsRouterConfig

    home_dir = tmp_path / "fake-home"
    home_dir.mkdir()

    home_file = home_dir / ".skills-router-home"
    home_file.write_text("   \n  ")

    monkeypatch.setattr("skills_router.config.Path.home", lambda: home_dir)

    config = SkillsRouterConfig()
    expected = str(home_dir / ".skills-router")
    assert config.data_dir == expected
