"""Tests for macro commands."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from dku_cli.main import app

runner = CliRunner()


def test_macro_list(patch_client):
    result = runner.invoke(app, ["macro", "list", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "My Macro" in result.output


def test_macro_list_json(patch_client):
    result = runner.invoke(
        app, ["--format", "json", "macro", "list", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed[0]["id"] == "pyrunnable_test_run-macro"


def test_macro_run(patch_client):
    result = runner.invoke(app, ["macro", "run", "macro1", "--project", "PROJ1"])
    assert result.exit_code == 0


def _macro_mock(patch_client, result_type="HTML"):
    macro = patch_client.get_project("PROJ1").get_macro.return_value
    macro.run.return_value = "runnables:PROJ1:macro1:0"
    macro.get_definition.return_value = {"resultType": result_type}
    return macro


def test_macro_run_prints_run_id_and_result_hint(patch_client):
    _macro_mock(patch_client)
    result = runner.invoke(
        app, ["macro", "run", "macro1", "--wait", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    assert "runnables:PROJ1:macro1:0" in result.output
    assert "dku macro result macro1" in result.output


def test_macro_run_print_result_implies_wait(patch_client):
    macro = _macro_mock(patch_client)
    macro.get_result.return_value = "<h1>done</h1>"
    result = runner.invoke(
        app, ["macro", "run", "macro1", "--print-result", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    macro.run.assert_called_once_with({}, wait=True)
    macro.get_result.assert_called_once_with(
        "runnables:PROJ1:macro1:0", as_type="string"
    )
    assert "<h1>done</h1>" in result.output


def test_macro_result_html(patch_client):
    macro = _macro_mock(patch_client)
    macro.get_result.return_value = "<p>hello</p>"
    result = runner.invoke(
        app, ["macro", "result", "macro1", "run42", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    macro.get_result.assert_called_once_with("run42", as_type="string")
    assert "<p>hello</p>" in result.output


def test_macro_result_json_result_table(patch_client):
    macro = _macro_mock(patch_client, result_type="RESULT_TABLE")
    macro.get_result.return_value = {"records": [["a"], ["b"]]}
    result = runner.invoke(
        app, ["macro", "result", "macro1", "run42", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    macro.get_result.assert_called_once_with("run42", as_type="json")
    parsed = json.loads(result.output)
    assert parsed["records"] == [["a"], ["b"]]


def test_macro_result_decodes_bytes(patch_client):
    macro = _macro_mock(patch_client)
    macro.get_result.return_value = b"plain text"
    result = runner.invoke(
        app, ["macro", "result", "macro1", "run42", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    assert "plain text" in result.output
