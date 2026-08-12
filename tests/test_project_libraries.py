"""Tests for project-library regex search safeguards."""

import pytest
import regex

from dataiku_mcp.tools.project_libraries import _search_regex


def test_regex_search_returns_matches():
    assert _search_regex(regex.compile(r"value=\d+"), "value=42") is True


def test_regex_search_times_out_for_catastrophic_backtracking():
    pattern = regex.compile(r"(a+)+$")

    with pytest.raises(ValueError, match="Regex search timed out"):
        _search_regex(pattern, "a" * 10_000 + "!")
