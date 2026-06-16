"""Tests for expanded CLI help output."""

from __future__ import annotations

import pytest


def test_build_parser_help_includes_command_details():
    from skills_router.cli import COMMAND_NAMES, build_parser

    parser = build_parser()

    help_text = parser.format_help()

    assert "Detailed command help:" in help_text
    assert "usage: skills-router install" in help_text
    assert "--scope" in help_text
    assert "usage: skills-router route" in help_text
    assert "--include-inactive" in help_text
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
    assert "usage: skills-router install" in out
    assert "--routing-mode" in out
    assert "Detailed command help:" not in out


def test_help_subcommand_without_topic_prints_full_help(capsys):
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
    assert "Detailed command help:" in out
    assert "usage: skills-router connect" in out


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
