"""Tests for `--format ids` — one identifier per line, built to pipe."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from dku_cli.main import app
from dku_cli.output import render, render_raw, set_output_format

runner = CliRunner()


def test_render_ids_prints_first_column_no_header(capsys):
    set_output_format("ids")
    render(
        [{"name": "a", "type": "csv"}, {"name": "b", "type": "sql"}],
        ["name", "type"],
    )
    assert capsys.readouterr().out == "a\nb\n"


def test_render_ids_empty_list_prints_nothing(capsys):
    set_output_format("ids")
    render([], ["name"])
    assert capsys.readouterr().out == ""


def test_render_raw_under_ids_stays_compact_json(capsys):
    set_output_format("ids")
    render_raw({"key": "value", "n": 1})
    out = capsys.readouterr().out
    assert json.loads(out) == {"key": "value", "n": 1}
    assert "\n" not in out.strip()


def test_format_ids_list_pipes_clean(patch_client):
    result = runner.invoke(
        app, ["--format", "ids", "dataset", "list", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    lines = result.output.splitlines()
    assert "ds1" in lines
    # no header row, no info/success noise — every line is an identifier
    assert "name" not in lines
    assert "◆" not in result.output


def test_format_table_rejected_lists_valid_formats(patch_client):
    result = runner.invoke(app, ["--format", "table", "dataset", "list"])
    assert result.exit_code == 2
    assert "ids" in result.output
