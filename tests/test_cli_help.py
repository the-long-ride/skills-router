"""Tests for compact top-level CLI help output."""

from __future__ import annotations

import pytest


def test_build_parser_help_is_compact_summary():
    from skills_router.cli import COMMAND_NAMES, build_parser

    parser = build_parser()

    help_text = parser.format_help()

    assert "Commands:" in help_text
    assert "Use: skills-router <command> -h for details." in help_text
    assert "usage: skills-router install" not in help_text
    assert "--include-inactive" not in help_text
    for command_name in COMMAND_NAMES:
        assert command_name in help_text


def test_help_subcommand_prints_command_specific_help(capsys):
    from skills_router.cli import main

    with pytest.raises(SystemExit) as excinfo:
        main_args = ["skills-router", "help", "install"]
        import sys

        old_argv = sys.argv
        sys.argv = main_args
        try:
            main()
        finally:
            sys.argv = old_argv

    assert excinfo.value.code == 0
    out = capsys.readouterr().out
    assert "Usage:" in out
    assert "skills-router install" in out
    assert "Arguments:" in out
    assert "Options:" in out
    assert "Examples:" in out
    assert "--routing-mode" in out
    assert "Detailed command help:" not in out
    assert "positional arguments:" not in out


def test_route_subcommand_help_uses_structured_sections():
    from skills_router.cli import build_parser

    parser = build_parser()

    help_text = parser._subparsers_action.choices["route"].format_help()

    assert "Usage:" in help_text
    assert "Arguments:" in help_text
    assert "Options:" in help_text
    assert "Examples:" in help_text
    assert "text" in help_text
    assert "--include-inactive" in help_text
    assert "skills-router route" in help_text
    assert "positional arguments:" not in help_text


def test_help_subcommand_without_topic_prints_compact_top_level_help(capsys):
    from skills_router.cli import main

    with pytest.raises(SystemExit) as excinfo:
        main_args = ["skills-router", "help"]
        import sys

        old_argv = sys.argv
        sys.argv = main_args
        try:
            main()
        finally:
            sys.argv = old_argv

    assert excinfo.value.code == 0
    out = capsys.readouterr().out
    assert "Commands:" in out
    assert "Use: skills-router <command> -h for details." in out
    assert "usage: skills-router connect" not in out


def test_version_flag_prints_package_version(capsys):
    from skills_router import __version__
    from skills_router.cli import main

    with pytest.raises(SystemExit) as excinfo:
        main_args = ["skills-router", "--version"]
        import sys

        old_argv = sys.argv
        sys.argv = main_args
        try:
            main()
        finally:
            sys.argv = old_argv

    assert excinfo.value.code == 0
    out = capsys.readouterr().out.strip()
    assert out == f"skills-router {__version__}"
