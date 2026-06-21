"""Tests for skills-router choose-home and move-home CLI commands."""

from __future__ import annotations

import json
import os
import sys

import pytest


@pytest.fixture
def _clean_cwd(monkeypatch, tmp_path):
    """Set cwd to a temp dir so ~/.skills-router-home patching is isolated."""
    monkeypatch.chdir(tmp_path)


@pytest.fixture(autouse=True)
def _disable_console_wrap():
    """Disable Rich console word-wrap so long paths are not broken."""
    from skills_router import cli
    old_width = cli.console.width
    cli.console.width = 200
    cli.console.no_color = True
    yield
    cli.console.width = old_width


@pytest.fixture
def _setup_patched_home(monkeypatch, tmp_path):
    """Patch Path.home() to return a temp directory."""
    home_dir = tmp_path / "fake-home"
    home_dir.mkdir()
    monkeypatch.setattr("skills_router.config.Path.home", lambda: home_dir)
    monkeypatch.delenv("SKILLS_ROUTER_HOME", raising=False)
    return home_dir


def _run_cli(args: list[str]) -> tuple[int, str]:
    """Run skills-router CLI with given args and capture stdout."""
    from io import StringIO
    from skills_router.cli import main

    old_stdout = sys.stdout
    old_argv = sys.argv
    try:
        captured = StringIO()
        sys.stdout = captured
        sys.argv = ["skills-router"] + args
        rc = 0
        try:
            main()
        except SystemExit as e:
            rc = e.code if isinstance(e.code, int) else 0
        return rc, captured.getvalue()
    finally:
        sys.stdout = old_stdout
        sys.argv = old_argv


# ---------------------------------------------------------------------------
# choose-home tests
# ---------------------------------------------------------------------------


def test_choose_home_writes_home_file(tmp_path, _setup_patched_home):
    """choose-home <path> writes ~/.skills-router-home with the target path."""
    home_dir = _setup_patched_home
    target = tmp_path / "my-skills-home"

    rc, out = _run_cli(["choose-home", str(target)])

    assert rc == 0
    assert "Home set to:" in out
    assert os.path.normpath(str(target)) in out.replace("\n", " ")

    home_file = home_dir / ".skills-router-home"
    assert home_file.is_file()
    assert home_file.read_text().strip() == str(target)


def test_choose_home_creates_target_dir(tmp_path, _setup_patched_home):
    """choose-home creates the target directory if it does not exist."""
    home_dir = _setup_patched_home
    target = tmp_path / "brand-new-home"

    rc, out = _run_cli(["choose-home", str(target)])

    assert rc == 0
    assert target.is_dir()

    home_file = home_dir / ".skills-router-home"
    assert str(target) in home_file.read_text()


def test_choose_home_json_output(tmp_path, _setup_patched_home):
    """choose-home --json produces machine-readable output."""
    target = tmp_path / "json-home"

    rc, out = _run_cli(["choose-home", str(target), "--json"])

    assert rc == 0
    result = json.loads(out)
    assert result["status"] == "OK"
    assert result["home"] == str(target)


def test_choose_home_no_args_prints_current_home(tmp_path, _setup_patched_home):
    """choose-home without arguments prints the current home path."""
    home_dir = _setup_patched_home
    default_home = str(home_dir / ".skills-router")

    rc, out = _run_cli(["choose-home"])

    assert rc == 0
    assert os.path.normpath(default_home) in out.replace("\n", " ")


def test_choose_home_no_args_json_prints_current(tmp_path, _setup_patched_home):
    """choose-home --json without path prints current home as JSON."""
    home_dir = _setup_patched_home
    default_home = str(home_dir / ".skills-router")

    rc, out = _run_cli(["choose-home", "--json"])

    assert rc == 0
    result = json.loads(out)
    assert result["status"] == "OK"
    assert result["home"] == default_home


def test_choose_home_appears_in_help():
    """choose-home appears in top-level help output."""
    rc, out = _run_cli(["-h"])
    assert "choose-home" in out


# ---------------------------------------------------------------------------
# move-home tests
# ---------------------------------------------------------------------------


def test_move_home_copies_all_data(tmp_path, _setup_patched_home):
    """move-home copies all files from old home to new home."""
    home_dir = _setup_patched_home
    old_home = tmp_path / "old-skills-home"
    old_home.mkdir(parents=True)

    # Create some data files in old home
    (old_home / "brain_index.json").write_text('{"tools": []}')
    (old_home / "dep_graph.json").write_text('{"deps": {}}')
    (old_home / "audit.jsonl").write_text('{"entry": 1}\n')
    (old_home / "registry_cache").mkdir()
    (old_home / "registry_cache" / "cached.txt").write_text("cached-data")

    # Set the home file to point to old_home
    home_file = home_dir / ".skills-router-home"
    home_file.write_text(str(old_home))

    new_home = tmp_path / "new-skills-home"

    rc, out = _run_cli(["move-home", str(new_home)])

    assert rc == 0
    assert "Home moved" in out
    assert os.path.normpath(str(new_home)) in out.replace("\n", " ")

    # Check files were copied
    assert (new_home / "brain_index.json").is_file()
    assert (new_home / "dep_graph.json").is_file()
    assert (new_home / "audit.jsonl").is_file()
    assert (new_home / "registry_cache").is_dir()
    assert (new_home / "registry_cache" / "cached.txt").is_file()

    # Check home file was updated
    assert home_file.read_text().strip() == str(new_home)


def test_move_home_updates_home_file(tmp_path, _setup_patched_home):
    """move-home updates ~/.skills-router-home to point to new path."""
    home_dir = _setup_patched_home
    old_home = tmp_path / "from-home"
    old_home.mkdir(parents=True)
    (old_home / "test.txt").write_text("hello")

    home_file = home_dir / ".skills-router-home"
    home_file.write_text(str(old_home))

    new_home = tmp_path / "to-home"

    _run_cli(["move-home", str(new_home)])

    assert home_file.read_text().strip() == str(new_home)


def test_move_home_same_path_is_noop(tmp_path, _setup_patched_home):
    """move-home to the same path prints a warning and exits cleanly."""
    home_dir = _setup_patched_home
    same = tmp_path / "same-home"
    same.mkdir(parents=True)
    (same / "test.txt").write_text("data")

    home_file = home_dir / ".skills-router-home"
    home_file.write_text(str(same))

    rc, out = _run_cli(["move-home", str(same)])

    assert rc == 0
    assert "already" in out.lower() or "same" in out.lower()


def test_move_home_dry_run_previews(tmp_path, _setup_patched_home):
    """move-home --dry-run previews without modifying files."""
    home_dir = _setup_patched_home
    old_home = tmp_path / "dry-old-home"
    old_home.mkdir(parents=True)
    (old_home / "brain_index.json").write_text('{"tools": []}')

    home_file = home_dir / ".skills-router-home"
    home_file.write_text(str(old_home))

    new_home = tmp_path / "dry-new-home"

    rc, out = _run_cli(["move-home", str(new_home), "--dry-run"])

    assert rc == 0
    # new home should NOT exist (dry run)
    assert not new_home.exists()
    # home file should NOT be updated
    assert home_file.read_text().strip() == str(old_home)
    # output should indicate dry run
    assert "dry" in out.lower() or "preview" in out.lower()


def test_move_home_json_output(tmp_path, _setup_patched_home):
    """move-home --json produces machine-readable output."""
    home_dir = _setup_patched_home
    old_home = tmp_path / "json-old-home"
    old_home.mkdir(parents=True)
    (old_home / "test.txt").write_text("data")

    home_file = home_dir / ".skills-router-home"
    home_file.write_text(str(old_home))

    new_home = tmp_path / "json-new-home"

    rc, out = _run_cli(["move-home", str(new_home), "--json"])

    assert rc == 0
    result = json.loads(out)
    assert result["status"] == "OK"
    assert result["new_home"] == str(new_home)
    assert "moved_count" in result


def test_move_home_json_dry_run(tmp_path, _setup_patched_home):
    """move-home --dry-run --json shows would-be moves."""
    home_dir = _setup_patched_home
    old_home = tmp_path / "json-dry-old"
    old_home.mkdir(parents=True)
    (old_home / "test.txt").write_text("data")

    home_file = home_dir / ".skills-router-home"
    home_file.write_text(str(old_home))

    new_home = tmp_path / "json-dry-new"

    rc, out = _run_cli(["move-home", str(new_home), "--dry-run", "--json"])

    assert rc == 0
    result = json.loads(out)
    assert result["status"] == "DRY_RUN"
    assert result["new_home"] == str(new_home)


def test_move_home_appears_in_help():
    """move-home appears in top-level help output."""
    rc, out = _run_cli(["-h"])
    assert "move-home" in out
