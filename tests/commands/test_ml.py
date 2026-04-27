"""Tests for ml commands."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from dku_cli.main import app

runner = CliRunner()


# --- create-prediction ---


def test_ml_create_prediction(patch_client):
    result = runner.invoke(
        app,
        ["ml", "create-prediction", "customers", "churn", "--project", "PROJ1"],
    )
    assert result.exit_code == 0
    assert "ML task ready" in result.output
    patch_client.get_project("PROJ1").create_prediction_ml_task.assert_called_once_with(
        "customers",
        "churn",
        ml_backend_type="PY_MEMORY",
        guess_policy="DEFAULT",
        prediction_type=None,
        wait_guess_complete=True,
    )


def test_ml_create_prediction_json(patch_client):
    result = runner.invoke(
        app,
        [
            "ml",
            "create-prediction",
            "customers",
            "churn",
            "--project",
            "PROJ1",
            "-o",
            "json",
        ],
    )
    assert result.exit_code == 0
    assert '"analysis_id"' in result.output
    assert '"a1"' in result.output
    assert '"t1"' in result.output


def test_ml_create_prediction_with_type(patch_client):
    result = runner.invoke(
        app,
        [
            "ml",
            "create-prediction",
            "customers",
            "churn",
            "--type",
            "BINARY_CLASSIFICATION",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    patch_client.get_project("PROJ1").create_prediction_ml_task.assert_called_once_with(
        "customers",
        "churn",
        ml_backend_type="PY_MEMORY",
        guess_policy="DEFAULT",
        prediction_type="BINARY_CLASSIFICATION",
        wait_guess_complete=True,
    )


# --- create-clustering ---


def test_ml_create_clustering(patch_client):
    result = runner.invoke(
        app,
        ["ml", "create-clustering", "customers", "--project", "PROJ1"],
    )
    assert result.exit_code == 0
    assert "ML task ready" in result.output
    patch_client.get_project("PROJ1").create_clustering_ml_task.assert_called_once_with(
        "customers",
        ml_backend_type="PY_MEMORY",
        guess_policy="KMEANS",
        wait_guess_complete=True,
    )


# --- create-timeseries ---


def test_ml_create_timeseries(patch_client):
    result = runner.invoke(
        app,
        [
            "ml",
            "create-timeseries",
            "sales",
            "revenue",
            "date_col",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    patch_client.get_project(
        "PROJ1"
    ).create_timeseries_forecasting_ml_task.assert_called_once_with(
        "sales",
        "revenue",
        "date_col",
        timeseries_identifiers=None,
        guess_policy="TIMESERIES_DEFAULT",
        wait_guess_complete=True,
    )


def test_ml_create_timeseries_with_identifiers(patch_client):
    result = runner.invoke(
        app,
        [
            "ml",
            "create-timeseries",
            "sales",
            "revenue",
            "date_col",
            "--identifier",
            "store_id",
            "--identifier",
            "region",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    patch_client.get_project(
        "PROJ1"
    ).create_timeseries_forecasting_ml_task.assert_called_once_with(
        "sales",
        "revenue",
        "date_col",
        timeseries_identifiers=["store_id", "region"],
        guess_policy="TIMESERIES_DEFAULT",
        wait_guess_complete=True,
    )


# --- create-causal ---


def test_ml_create_causal(patch_client):
    result = runner.invoke(
        app,
        [
            "ml",
            "create-causal",
            "experiment",
            "outcome",
            "treatment_flag",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    patch_client.get_project(
        "PROJ1"
    ).create_causal_prediction_ml_task.assert_called_once_with(
        "experiment",
        "outcome",
        "treatment_flag",
        prediction_type=None,
        wait_guess_complete=True,
    )


# --- list ---


def test_ml_list(patch_client):
    result = runner.invoke(app, ["ml", "list", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "a1" in result.output
    assert "PREDICTION" in result.output


def test_ml_list_json(patch_client):
    result = runner.invoke(app, ["ml", "list", "--project", "PROJ1", "-o", "json"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed[0]["analysis_id"] == "a1"
    assert parsed[0]["mltask_id"] == "t1"


# --- status ---


def test_ml_status(patch_client):
    result = runner.invoke(app, ["ml", "status", "a1", "t1", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "False" in result.output  # guessing: False


def test_ml_status_json(patch_client):
    result = runner.invoke(
        app, ["ml", "status", "a1", "t1", "--project", "PROJ1", "-o", "json"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["guessing"] is False


# --- train ---


def test_ml_train(patch_client):
    result = runner.invoke(app, ["ml", "train", "a1", "t1", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "Trained 1 model(s)" in result.output
    patch_client.get_project("PROJ1").get_ml_task("a1", "t1").train.assert_called_once()


def test_ml_train_json(patch_client):
    result = runner.invoke(
        app, ["ml", "train", "a1", "t1", "--project", "PROJ1", "-o", "json"]
    )
    assert result.exit_code == 0
    assert '"count": 1' in result.output
    assert '"model_ids"' in result.output


def test_ml_train_no_wait(patch_client):
    result = runner.invoke(
        app, ["ml", "train", "a1", "t1", "--no-wait", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    assert "Training started" in result.output
    patch_client.get_project("PROJ1").get_ml_task(
        "a1", "t1"
    ).start_train.assert_called_once()


# --- models ---


def test_ml_models(patch_client):
    result = runner.invoke(app, ["ml", "models", "a1", "t1", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "RandomForest" in result.output


def test_ml_models_json(patch_client):
    result = runner.invoke(
        app, ["ml", "models", "a1", "t1", "--project", "PROJ1", "-o", "json"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed[0]["algorithm"] == "RandomForest"


# --- details ---


def test_ml_details(patch_client):
    result = runner.invoke(
        app, ["ml", "details", "a1", "t1", "model1", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    assert "auc" in result.output


def test_ml_details_json(patch_client):
    result = runner.invoke(
        app, ["ml", "details", "a1", "t1", "model1", "--project", "PROJ1", "-o", "json"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["auc"] == 0.92


# --- deploy ---


def test_ml_deploy(patch_client):
    result = runner.invoke(
        app,
        [
            "ml",
            "deploy",
            "a1",
            "t1",
            "model1",
            "--name",
            "ChurnModel",
            "--train-dataset",
            "customers",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "Deployed to flow" in result.output
    assert "sm1" in result.output


def test_ml_deploy_json(patch_client):
    result = runner.invoke(
        app,
        [
            "ml",
            "deploy",
            "a1",
            "t1",
            "model1",
            "--name",
            "ChurnModel",
            "--train-dataset",
            "customers",
            "--project",
            "PROJ1",
            "-o",
            "json",
        ],
    )
    assert result.exit_code == 0
    assert '"savedModelId"' in result.output
    assert '"sm1"' in result.output
    assert '"train_recipe1"' in result.output


# --- redeploy ---


def test_ml_redeploy(patch_client):
    result = runner.invoke(
        app,
        [
            "ml",
            "redeploy",
            "a1",
            "t1",
            "model1",
            "--saved-model-id",
            "sm1",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "Redeployed" in result.output


def test_ml_redeploy_missing_target(patch_client):
    result = runner.invoke(
        app,
        ["ml", "redeploy", "a1", "t1", "model1", "--project", "PROJ1"],
    )
    assert result.exit_code != 0
    assert "saved-model-id" in result.output or "recipe-name" in result.output


# --- settings ---


def test_ml_settings(patch_client):
    result = runner.invoke(app, ["ml", "settings", "a1", "t1", "--project", "PROJ1"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["taskType"] == "PREDICTION"


# --- algorithms ---


def test_ml_algorithms(patch_client):
    result = runner.invoke(app, ["ml", "algorithms", "a1", "t1", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "RandomForest" in result.output
    assert "XGBoost" in result.output


def test_ml_algorithms_json(patch_client):
    result = runner.invoke(
        app, ["ml", "algorithms", "a1", "t1", "--project", "PROJ1", "-o", "json"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    algos = {a["name"]: a["enabled"] for a in parsed}
    assert algos["RandomForest"] == "True"
    assert algos["XGBoost"] == "False"


# --- set-algorithm ---


def test_ml_set_algorithm(patch_client):
    result = runner.invoke(
        app,
        [
            "ml",
            "set-algorithm",
            "a1",
            "t1",
            "--disable-all",
            "--enable",
            "XGBoost",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "updated" in result.output
    settings = patch_client.get_project("PROJ1").get_ml_task("a1", "t1").get_settings()
    settings.disable_all_algorithms.assert_called_once()
    settings.set_algorithm_enabled.assert_called_with("XGBoost", True)
    settings.save.assert_called_once()


# --- delete ---


def test_ml_delete(patch_client):
    result = runner.invoke(
        app, ["ml", "delete", "a1", "t1", "--project", "PROJ1", "--yes"]
    )
    assert result.exit_code == 0
    assert "Deleted ML task" in result.output
    patch_client.get_project("PROJ1").get_ml_task(
        "a1", "t1"
    ).delete.assert_called_once()
