"""Tests for evaluation-store commands."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from dku_cli.main import app

runner = CliRunner()


# ── list ─────────────────────────────────────────────────────────────


def test_evaluation_store_list(patch_client):
    result = runner.invoke(app, ["evaluation-store", "list", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "mes1" in result.output
    patch_client.get_project("PROJ1").list_evaluation_stores.assert_called_once_with(
        flavor=None
    )


def test_evaluation_store_list_json(patch_client):
    result = runner.invoke(
        app, ["--format", "json", "evaluation-store", "list", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed[0]["id"] == "mes1"
    assert parsed[0]["flavor"] == "TABULAR"
    assert parsed[0]["name"] == "Churn Eval Store"


def test_evaluation_store_list_with_flavor(patch_client):
    result = runner.invoke(
        app, ["evaluation-store", "list", "--flavor", "LLM", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    patch_client.get_project("PROJ1").list_evaluation_stores.assert_called_once_with(
        flavor="LLM"
    )


def test_evaluation_store_list_invalid_flavor(patch_client):
    result = runner.invoke(
        app, ["evaluation-store", "list", "--flavor", "BOGUS", "--project", "PROJ1"]
    )
    assert result.exit_code == 2
    assert "Invalid value" in result.output


# ── create ───────────────────────────────────────────────────────────


def test_evaluation_store_create(patch_client):
    """Default flavor is TABULAR."""
    result = runner.invoke(
        app, ["evaluation-store", "create", "Churn Eval", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    assert "Created TABULAR evaluation store" in result.output
    patch_client.get_project("PROJ1").create_evaluation_store.assert_called_once_with(
        "Churn Eval", flavor="TABULAR"
    )


def test_evaluation_store_create_llm_flavor(patch_client):
    result = runner.invoke(
        app,
        [
            "evaluation-store",
            "create",
            "RAG Eval",
            "--flavor",
            "LLM",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "Created LLM evaluation store" in result.output
    patch_client.get_project("PROJ1").create_evaluation_store.assert_called_once_with(
        "RAG Eval", flavor="LLM"
    )


def test_evaluation_store_create_agent_flavor(patch_client):
    result = runner.invoke(
        app,
        [
            "evaluation-store",
            "create",
            "Agent Eval",
            "--flavor",
            "AGENT",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "Created AGENT evaluation store" in result.output
    patch_client.get_project("PROJ1").create_evaluation_store.assert_called_once_with(
        "Agent Eval", flavor="AGENT"
    )


def test_evaluation_store_create_invalid_flavor(patch_client):
    result = runner.invoke(
        app,
        [
            "evaluation-store",
            "create",
            "Bad Store",
            "--flavor",
            "NOPE",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 2
    assert "Invalid value" in result.output


def test_evaluation_store_create_if_not_exists(patch_client):
    proj = patch_client.get_project("PROJ1")
    proj.create_evaluation_store.side_effect = Exception("already exists")
    result = runner.invoke(
        app,
        [
            "evaluation-store",
            "create",
            "Churn Eval",
            "--if-not-exists",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "already exists" in result.output


# ── get ──────────────────────────────────────────────────────────────


def test_evaluation_store_get(patch_client):
    result = runner.invoke(
        app, ["evaluation-store", "get", "mes1", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["id"] == "mes1"


# ── evaluations ──────────────────────────────────────────────────────


def test_evaluation_store_evaluations(patch_client):
    result = runner.invoke(
        app, ["evaluation-store", "evaluations", "mes1", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    assert "eval1" in result.output


def test_evaluation_store_evaluations_json(patch_client):
    result = runner.invoke(
        app,
        [
            "--format",
            "json",
            "evaluation-store",
            "evaluations",
            "mes1",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed[0]["evaluation_id"] == "eval1"


# ── latest ───────────────────────────────────────────────────────────


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


# ── build ────────────────────────────────────────────────────────────


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


def test_evaluation_store_build_failed_surfaces_log_excerpt(patch_client):
    """A FAILED build should pull the activity log and surface the relevant lines."""
    proj = patch_client.get_project("PROJ1")
    store = proj.get_model_evaluation_store("mes1")
    job = store.build.return_value
    job.get_status.return_value = {"baseStatus": {"state": "FAILED"}}
    job.get_log.return_value = (
        "INFO: Starting evaluation\n"
        "INFO: Loading custom metric\n"
        "Traceback (most recent call last):\n"
        '  File "<custom_metric>", line 1\n'
        '    """\n'
        "       ^\n"
        "SyntaxError: unexpected character after line continuation character\n"
    )

    result = runner.invoke(
        app, ["evaluation-store", "build", "mes1", "--project", "PROJ1"]
    )
    assert result.exit_code != 0
    assert "Build failed" in result.output
    # Log excerpt is surfaced inline.
    assert "SyntaxError" in result.output
    # The """ JSON-escape hint fires for this canonical error.
    assert "''' triple-strings" in result.output


def test_evaluation_store_build_failed_no_log_still_useful(patch_client):
    """Even without log text, the user still gets the job ID and a `dku job log` hint."""
    proj = patch_client.get_project("PROJ1")
    store = proj.get_model_evaluation_store("mes1")
    job = store.build.return_value
    job.get_status.return_value = {"baseStatus": {"state": "FAILED"}}
    job.get_log.return_value = ""

    result = runner.invoke(
        app, ["evaluation-store", "build", "mes1", "--project", "PROJ1"]
    )
    assert result.exit_code != 0
    assert "Build failed" in result.output
    assert "job_mes_build" in result.output
    assert "dku job log" in result.output


# ── delete ───────────────────────────────────────────────────────────


def test_evaluation_store_delete(patch_client):
    result = runner.invoke(
        app, ["evaluation-store", "delete", "mes1", "--project", "PROJ1", "--yes"]
    )
    assert result.exit_code == 0
    assert "Deleted evaluation store" in result.output
