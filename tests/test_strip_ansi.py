"""Tests for the shared ``strip_ansi`` test helper.

This guards the consolidated ANSI-strip helper that replaced ~9 per-file
``re.sub(r"\\x1b\\[[0-9;]*m", ...)`` duplicates across the test suite.
"""

from __future__ import annotations

from tests.helpers import strip_ansi


def test_strip_ansi_removes_sgr_codes():
    colored = "\x1b[1m\x1b[32mOK\x1b[0m done"
    assert strip_ansi(colored) == "OK done"


def test_strip_ansi_handles_compound_codes():
    # Rich often emits semicolon-joined SGR params, e.g. bold + 256-color.
    assert strip_ansi("\x1b[1;38;5;204mvalue\x1b[0m") == "value"


def test_strip_ansi_is_noop_on_plain_text():
    plain = "no escapes here"
    assert strip_ansi(plain) == plain


def test_strip_ansi_only_targets_sgr_terminator():
    # The original per-file pattern only matched the `m`-terminated SGR form,
    # so non-SGR sequences must pass through unchanged (semantics preserved).
    assert strip_ansi("\x1b[2Jcleared") == "\x1b[2Jcleared"
