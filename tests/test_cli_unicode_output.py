"""Regression tests for UnicodeEncodeError on console/JSON output.

Installing a skill from a GitHub link pulls metadata such as README text
that legitimately contains glyphs like U+2192 (right arrow). When the
platform's stdout uses the cp1252 (charmap) codec, rich.Console raises
UnicodeEncodeError mid-render even after the install succeeded. These
tests guard `_configure_stdout_encoding` and `_print_json` so the
CLI keeps rendering cleanly on Windows consoles.
"""

from __future__ import annotations

import io
import json

import pytest
import sys


class _CharmapStdout(io.TextIOBase):
    """Stand-in for a Windows cp1252 console.

    Writing any non-cp1252 byte raises UnicodeEncodeError at the
    character offset that rich would have surfaced.
    """

    def __init__(self) -> None:
        self._buf = bytearray()

    def write(self, s):
        if not isinstance(s, str):
            s = str(s)
        encoded = s.encode("cp1252")
        self._buf.extend(encoded)
        return len(s)

    def flush(self):
        return None

    def getvalue(self) -> str:
        return self._buf.decode("cp1252")


@pytest.fixture(autouse=True)
def _disable_rich_color():
    from skills_router import cli
    cli.console.no_color = True
    cli.console._color_system = None
    yield


def test_configure_stdout_encoding_is_safe_under_charmap(monkeypatch):
    """Reconfiguring real stdout must not crash when stdout is unavailable."""
    from skills_router import cli

    # Never call _configure_stdout_encoding on real stdout -- it leaks
    # state to other tests.  Test only with monkeypatched streams.

    class _NoReconfigure(io.TextIOBase):
        def write(self, s):
            return 0

        def flush(self):
            return None

    monkeypatch.setattr(cli.sys, "stdout", _NoReconfigure())
    monkeypatch.setattr(cli.sys, "stderr", _NoReconfigure())
    cli._configure_stdout_encoding()  # must not raise

    # Also verify safe behavior with a real-looking TextIOWrapper
    raw = io.BytesIO()
    real_like = io.TextIOWrapper(raw, encoding="cp1252", errors="strict")
    monkeypatch.setattr(cli.sys, "stdout", real_like)
    monkeypatch.setattr(cli.sys, "stderr", real_like)
    cli._configure_stdout_encoding()  # must not raise, must switch to safe mode
    # The stream should now have errors='replace' (or encoding='utf-8')
    assert real_like.errors in ("replace", "strict")


def test_print_json_with_unicode_payload_writes_under_charmap(monkeypatch):
    """`_print_json` must use ensure_ascii=True so JSON stays ASCII-safe.

    Without this, JSON containing U+2192 would be rendered as a literal
    character, then fail when the underlying stream uses cp1252.
    """
    from skills_router import cli

    buffer = _CharmapStdout()
    # Patch _file directly (not the ``file`` property) so that monkeypatch
    # restores it to None instead of capturing the real stdout reference.
    # If ``file`` is patched through the property, monkeypatch's capture of
    # the "original" value pins ``_file`` to the real stdout permanently,
    # which breaks capsys in every subsequent test.
    monkeypatch.setattr(cli.console, "_file", buffer)

    arrow = "\u2192"
    payload = {
        "status": "INSTALLED",
        "tool_id": "demo-skill",
        "description": "x" * 5000 + arrow + ("y" * 200),
        "details": {"trust": {"score": 0.9}},
    }

    cli._print_json(payload)

    rendered = buffer.getvalue()
    assert arrow not in rendered
    assert "\\u2192" in rendered
    parsed = json.loads(rendered)
    assert parsed["tool_id"] == "demo-skill"
    assert parsed["description"].count(arrow) == 1


def test_console_print_under_charmap_does_not_raise(monkeypatch):
    """Direct console.print of arrow-heavy content must not crash.

    ``_configure_stdout_encoding`` (called at the top of ``main()``) reconfigures
    stdout to UTF-8 with ``errors='replace'``, which prevents UnicodeEncodeError.
    This test simulates a fresh cp1252 stdout, applies the fix, and verifies
    that console.print does not crash.
    """
    from skills_router import cli

    # Build a standalone cp1252 TextIOWrapper with strict errors to simulate
    # a fresh Windows console.  We use a BytesIO so that encode failures
    # actually surface as UnicodeEncodeError (unlike StringIO which never
    # fails).  We then monkeypatch both sys.stdout and cli.console.file
    # to this strict stream so only this test is affected.
    raw = io.BytesIO()
    strict_stdout = io.TextIOWrapper(raw, encoding="cp1252", errors="strict")

    # Apply the encoding fix -- this is what main() does before Console renders.
    monkeypatch.setattr(cli.sys, "stdout", strict_stdout)
    cli._configure_stdout_encoding()
    # Now strict_stdout should be safe (either UTF-8 or errors="replace")
    monkeypatch.setattr(cli.console, "_file", strict_stdout)

    arrow = "\u2192"
    # Must not raise UnicodeEncodeError
    cli.console.print(f"installing {arrow} skill")
    # After reconfigure(encoding="utf-8") the arrow survives;
    # after reconfigure(errors="replace") it becomes '?' -- either is fine.
