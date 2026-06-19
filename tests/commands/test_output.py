"""Tests for output formatting helpers."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from dku_cli import output
from dku_cli.main import app

runner = CliRunner()


# --- filter_fields ---


def test_filter_fields_none_returns_unchanged():
    data = [{"a": 1, "b": 2}, {"a": 3, "b": 4}]
    columns = ["a", "b"]
    filtered, cols = output.filter_fields(data, columns, None)
    assert filtered == data
    assert cols == columns


def test_filter_fields_empty_returns_unchanged():
    data = [{"a": 1, "b": 2}]
    columns = ["a", "b"]
    filtered, cols = output.filter_fields(data, columns, "")
    assert filtered == data
    assert cols == columns


def test_filter_fields_selects_requested():
    data = [{"a": 1, "b": 2, "c": 3}, {"a": 4, "b": 5, "c": 6}]
    filtered, cols = output.filter_fields(data, ["a", "b", "c"], "a, c")
    assert cols == ["a", "c"]
    assert filtered == [{"a": 1, "c": 3}, {"a": 4, "c": 6}]


def test_filter_fields_ignores_missing_keys():
    data = [{"a": 1, "b": 2}]
    filtered, cols = output.filter_fields(data, ["a", "b"], "a,missing")
    assert cols == ["a", "missing"]
    assert filtered == [{"a": 1}]


# --- JSON output ---


def test_render_json_is_indented(capsys):
    output.render(
        [{"a": 1, "b": 2}],
        ["a", "b"],
        output_format="json",
    )
    out = capsys.readouterr().out
    parsed = json.loads(out)
    assert parsed == [{"a": 1, "b": 2}]
    # --format json uses indentation.
    assert "\n  " in out


def test_render_raw_default_is_compact(capsys):
    output.render_raw({"a": 1, "b": 2})
    out = capsys.readouterr().out
    assert out.strip() == '{"a":1,"b":2}'
    assert ": " not in out


# --- --fields filtering through the CLI ---


def test_fields_filtering_via_cli(patch_client):
    # Legacy --fields name 'key' maps to the API noun 'projectKey'.
    result = runner.invoke(
        app,
        ["--format", "json", "project", "list", "--fields", "key"],
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed
    assert all(set(row.keys()) == {"projectKey"} for row in parsed)
