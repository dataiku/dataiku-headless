"""Tests for evaluation-store commands."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from dku_cli.main import app

runner = CliRunner()


def test_evaluation_store_list(patch_client):
    result = runner.invoke(
        app, ["evaluation-store", "list", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    assert "mes1" in result.output


def test_evaluation_store_list_json(patch_client):
    result = runner.invoke(
        app, ["evaluation-store", "list", "--project", "PROJ1", "-o", "json"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed[0]["id"] == "mes1"


def test_evaluation_store_create(patch_client):
    result = runner.invoke(
        app, ["evaluation-store", "create", "Churn Eval", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    assert "Created evaluation store" in result.output
    patch_client.get_project("PROJ1").create_model_evaluation_store.assert_called_once_with(
        "Churn Eval"
    )


def test_evaluation_store_create_if_not_exists(patch_client):
    proj = patch_client.get_project("PROJ1")
    proj.create_model_evaluation_store.side_effect = Exception("already exists")
    result = runner.invoke(
        app,
        ["evaluation-store", "create", "Churn Eval", "--if-not-exists", "--project", "PROJ1"],
    )
    assert result.exit_code == 0
    assert "already exists" in result.output


def test_evaluation_store_get(patch_client):
    result = runner.invoke(
        app, ["evaluation-store", "get", "mes1", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["id"] == "mes1"


def test_evaluation_store_evaluations(patch_client):
    result = runner.invoke(
        app, ["evaluation-store", "evaluations", "mes1", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    assert "eval1" in result.output


def test_evaluation_store_evaluations_json(patch_client):
    result = runner.invoke(
        app,
        ["evaluation-store", "evaluations", "mes1", "--project", "PROJ1", "-o", "json"],
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed[0]["evaluation_id"] == "eval1"


def test_evaluation_store_latest(patch_client):
    result = runner.invoke(
        app, ["evaluation-store", "latest", "mes1", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    assert "eval1" in result.output


def test_evaluation_store_latest_empty(patch_client):
    store = patch_client.get_project("PROJ1").get_model_evaluation_store("mes1")
    store.get_latest_model_evaluation.return_value = None
    result = runner.invoke(
        app, ["evaluation-store", "latest", "mes1", "--project", "PROJ1"]
    )
    assert result.exit_code != 0
    assert "No evaluations" in result.output


def test_evaluation_store_build(patch_client):
    result = runner.invoke(
        app, ["evaluation-store", "build", "mes1", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    assert "Build complete" in result.output


def test_evaluation_store_build_no_wait(patch_client):
    result = runner.invoke(
        app, ["evaluation-store", "build", "mes1", "--no-wait", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    assert "Build started" in result.output


def test_evaluation_store_delete(patch_client):
    result = runner.invoke(
        app, ["evaluation-store", "delete", "mes1", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    assert "Deleted evaluation store" in result.output
