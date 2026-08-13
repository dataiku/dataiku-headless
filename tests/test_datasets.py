"""Tests for dataset export safeguards."""

import pytest

from dataiku_mcp.tools.datasets import _serialize_csv_value


@pytest.mark.parametrize(
    "value",
    ["=1+1", "+1+1", "-1+1", "@SUM(A1:A2)", "\t=1+1", "\r=1+1", " =1+1"],
)
def test_csv_export_escapes_formula_prefixes_when_requested(value):
    assert _serialize_csv_value(value, spreadsheet_safe=True) == "'" + value


@pytest.mark.parametrize("value", ["plain text", "'already safe", 12, 1.5])
def test_csv_export_leaves_safe_values_unchanged(value):
    assert _serialize_csv_value(value, spreadsheet_safe=True) == value


def test_csv_export_serializes_null_as_empty_cell():
    assert _serialize_csv_value(None, spreadsheet_safe=True) == ""


def test_csv_export_preserves_raw_formula_text_by_default():
    assert _serialize_csv_value("=1+1", spreadsheet_safe=False) == "=1+1"


def test_csv_export_escapes_formula_text_when_requested():
    assert _serialize_csv_value("=1+1", spreadsheet_safe=True) == "'=1+1"
