"""Tests for notebook commands."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from dku_cli.main import app

runner = CliRunner()


def test_notebook_list_all(patch_client):
    result = runner.invoke(app, ["notebook", "list", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "my_notebook" in result.output
    assert "my_sql_notebook" in result.output


def test_notebook_list_jupyter_only(patch_client):
    result = runner.invoke(
        app, ["notebook", "list", "--project", "PROJ1", "--type", "jupyter"]
    )
    assert result.exit_code == 0
    assert "my_notebook" in result.output
    assert "my_sql_notebook" not in result.output


def test_notebook_list_sql_only(patch_client):
    result = runner.invoke(
        app, ["notebook", "list", "--project", "PROJ1", "--type", "sql", "-o", "json"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert len(parsed) >= 1
    assert all(item["type"] == "sql" for item in parsed)


def test_notebook_list_json(patch_client):
    result = runner.invoke(
        app, ["notebook", "list", "--project", "PROJ1", "-o", "json"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert len(parsed) == 2
    types = {item["type"] for item in parsed}
    assert types == {"jupyter", "sql"}


def test_notebook_get(patch_client):
    result = runner.invoke(
        app, ["notebook", "get", "my_notebook", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    proj = patch_client.get_project("PROJ1")
    proj.get_jupyter_notebook.assert_called_with("my_notebook")


def test_notebook_get_json(patch_client):
    result = runner.invoke(
        app, ["notebook", "get", "my_notebook", "--project", "PROJ1", "-o", "json"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert "cells" in parsed
    assert "metadata" in parsed


def test_notebook_create(patch_client):
    result = runner.invoke(app, ["notebook", "create", "new_nb", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "Created" in result.output
    assert "new_nb" in result.output
    proj = patch_client.get_project("PROJ1")
    proj.create_jupyter_notebook.assert_called_once()
    call_args = proj.create_jupyter_notebook.call_args
    assert call_args[0][0] == "new_nb"
    assert call_args[0][1]["nbformat"] == 4


def test_notebook_delete(patch_client):
    result = runner.invoke(
        app, ["notebook", "delete", "my_notebook", "--project", "PROJ1", "--yes"]
    )
    assert result.exit_code == 0
    assert "Deleted" in result.output
    proj = patch_client.get_project("PROJ1")
    nb = proj.get_jupyter_notebook("my_notebook")
    nb.delete.assert_called_once()


def test_notebook_sessions(patch_client):
    result = runner.invoke(app, ["notebook", "sessions", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "my_notebook" in result.output
    assert "k1" in result.output
    assert "s1" in result.output


def test_notebook_sessions_json(patch_client):
    result = runner.invoke(
        app, ["notebook", "sessions", "--project", "PROJ1", "-o", "json"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert len(parsed) == 1
    assert parsed[0]["kernel_id"] == "k1"


def test_notebook_stop(patch_client):
    result = runner.invoke(
        app, ["notebook", "stop", "my_notebook", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    assert "Stopped" in result.output
    proj = patch_client.get_project("PROJ1")
    nb = proj.get_jupyter_notebook("my_notebook")
    nb.unload.assert_called_once_with()


def test_notebook_stop_with_session(patch_client):
    result = runner.invoke(
        app,
        ["notebook", "stop", "my_notebook", "--session", "s1", "--project", "PROJ1"],
    )
    assert result.exit_code == 0
    proj = patch_client.get_project("PROJ1")
    nb = proj.get_jupyter_notebook("my_notebook")
    nb.unload.assert_called_once_with(session_id="s1")


def test_notebook_clear_outputs(patch_client):
    result = runner.invoke(
        app,
        [
            "notebook",
            "clear-outputs",
            "my_notebook",
            "--project",
            "PROJ1",
            "--yes",
        ],
    )
    assert result.exit_code == 0
    assert "Cleared" in result.output
    proj = patch_client.get_project("PROJ1")
    nb = proj.get_jupyter_notebook("my_notebook")
    nb.clear_outputs.assert_called_once()


def test_notebook_history(patch_client):
    result = runner.invoke(
        app, ["notebook", "history", "my_sql_notebook", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    proj = patch_client.get_project("PROJ1")
    proj.get_sql_notebook.assert_called_with("my_sql_notebook")


def test_notebook_history_json(patch_client):
    result = runner.invoke(
        app,
        ["notebook", "history", "my_sql_notebook", "--project", "PROJ1", "-o", "json"],
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert "queries" in parsed
