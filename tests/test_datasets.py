"""Tests for dataset export safeguards."""

import pytest

from dataiku_mcp.tools.datasets import _escape_csv_formula


@pytest.mark.parametrize(
    "value",
    ["=1+1", "+1+1", "-1+1", "@SUM(A1:A2)", "\t=1+1", "\r=1+1", " =1+1"],
)
def test_escape_csv_formula_prefixes(value):
    assert _escape_csv_formula(value) == "'" + value


@pytest.mark.parametrize("value", ["plain text", "'already safe", 12, 1.5, None])
def test_escape_csv_formula_leaves_safe_values_unchanged(value):
    assert _escape_csv_formula(value) == value
