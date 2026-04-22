"""Tests for model commands."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from dku_cli.main import app

runner = CliRunner()


def test_model_list(patch_client):
    result = runner.invoke(app, ["model", "list", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "model1" in result.output


def test_model_list_json(patch_client):
    result = runner.invoke(app, ["model", "list", "--project", "PROJ1", "-o", "json"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed[0]["id"] == "model1"


def test_model_get(patch_client):
    result = runner.invoke(app, ["model", "get", "model1", "--project", "PROJ1"])
    assert result.exit_code == 0


def test_model_get_json(patch_client):
    result = runner.invoke(
        app, ["model", "get", "model1", "--project", "PROJ1", "-o", "json"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["active_version"] == "v1"


def test_model_versions(patch_client):
    result = runner.invoke(app, ["model", "versions", "model1", "--project", "PROJ1"])
    assert result.exit_code == 0


def test_model_versions_json(patch_client):
    result = runner.invoke(
        app, ["model", "versions", "model1", "--project", "PROJ1", "-o", "json"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed[0]["id"] == "v1"
    assert parsed[0]["algorithm"] == "RandomForest"


# --- set-active-version ---


def test_model_set_active_version(patch_client):
    result = runner.invoke(
        app, ["model", "set-active-version", "model1", "v2", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    assert "Activated version v2" in result.output
    patch_client.get_project("PROJ1").get_saved_model(
        "model1"
    ).set_active_version.assert_called_once_with("v2")


def test_model_set_active_version_not_found(patch_client):
    sm = patch_client.get_project("PROJ1").get_saved_model("model1")
    sm.set_active_version.side_effect = Exception(
        "NotFoundException: version not_exist does not exist"
    )
    result = runner.invoke(
        app,
        ["model", "set-active-version", "model1", "not_exist", "--project", "PROJ1"],
    )
    assert result.exit_code != 0


# --- metrics ---


def test_model_metrics(patch_client):
    result = runner.invoke(app, ["model", "metrics", "model1", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "auc" in result.output


def test_model_metrics_json(patch_client):
    result = runner.invoke(
        app, ["model", "metrics", "model1", "--project", "PROJ1", "-o", "json"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["auc"] == 0.92
    assert parsed["accuracy"] == 0.88


def test_model_metrics_specific_version(patch_client):
    result = runner.invoke(
        app, ["model", "metrics", "model1", "--version", "v2", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    patch_client.get_project("PROJ1").get_saved_model(
        "model1"
    ).get_version_details.assert_called_with("v2")


def test_model_metrics_no_active_version(patch_client):
    sm = patch_client.get_project("PROJ1").get_saved_model("model1")
    sm.get_active_version.return_value = None
    result = runner.invoke(app, ["model", "metrics", "model1", "--project", "PROJ1"])
    assert result.exit_code != 0
    assert "No active version" in result.output


# --- delete-version ---


def test_model_delete_version(patch_client):
    result = runner.invoke(
        app,
        [
            "model",
            "delete-version",
            "model1",
            "--version",
            "v1",
            "--project",
            "PROJ1",
            "--yes",
        ],
    )
    assert result.exit_code == 0
    assert "Deleted 1 version(s)" in result.output
    patch_client.get_project("PROJ1").get_saved_model(
        "model1"
    ).delete_versions.assert_called_once_with(["v1"])


def test_model_delete_version_multiple(patch_client):
    result = runner.invoke(
        app,
        [
            "model",
            "delete-version",
            "model1",
            "--version",
            "v1",
            "--version",
            "v2",
            "--project",
            "PROJ1",
            "--yes",
        ],
    )
    assert result.exit_code == 0
    assert "Deleted 2 version(s)" in result.output
    patch_client.get_project("PROJ1").get_saved_model(
        "model1"
    ).delete_versions.assert_called_once_with(["v1", "v2"])


# --- delete ---


def test_model_delete(patch_client):
    result = runner.invoke(
        app, ["model", "delete", "model1", "--project", "PROJ1", "--yes"]
    )
    assert result.exit_code == 0
    assert "Deleted saved model" in result.output
    patch_client.get_project("PROJ1").get_saved_model(
        "model1"
    ).delete.assert_called_once()


# --- usages ---


def test_model_usages(patch_client):
    result = runner.invoke(app, ["model", "usages", "model1", "--project", "PROJ1"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert "usedIn" in parsed


def test_model_usages_json(patch_client):
    result = runner.invoke(
        app, ["model", "usages", "model1", "--project", "PROJ1", "-o", "json"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed == {"usedIn": []}


# --- set-metadata ---


def test_model_set_metadata_description(patch_client):
    result = runner.invoke(
        app,
        [
            "model",
            "set-metadata",
            "model1",
            "--description",
            "Churn prediction model",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "Updated metadata" in result.output
    model = patch_client.get_project("PROJ1").get_saved_model("model1")
    model.get_settings().save.assert_called()


def test_model_set_metadata_no_args(patch_client):
    result = runner.invoke(
        app, ["model", "set-metadata", "model1", "--project", "PROJ1"]
    )
    assert result.exit_code != 0


# --- create-mlflow ---


def test_model_create_mlflow(patch_client):
    result = runner.invoke(
        app,
        [
            "model",
            "create-mlflow",
            "Churn Model",
            "-t",
            "BINARY_CLASSIFICATION",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "Created" in result.output
    assert "model1" in result.output
    proj = patch_client.get_project("PROJ1")
    proj.create_mlflow_pyfunc_model.assert_called_once_with(
        "Churn Model", prediction_type="BINARY_CLASSIFICATION"
    )


def test_model_create_mlflow_no_type(patch_client):
    """Prediction type is optional."""
    result = runner.invoke(
        app, ["model", "create-mlflow", "Generic Model", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    proj = patch_client.get_project("PROJ1")
    proj.create_mlflow_pyfunc_model.assert_called_once_with(
        "Generic Model", prediction_type=None
    )


def test_model_create_mlflow_json(patch_client):
    result = runner.invoke(
        app,
        ["model", "create-mlflow", "Test", "--project", "PROJ1", "-o", "json"],
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["id"] == "model1"
    assert parsed["name"] == "Test"


def test_model_create_mlflow_invalid_type(patch_client):
    result = runner.invoke(
        app,
        [
            "model",
            "create-mlflow",
            "Bad",
            "-t",
            "INVALID",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code != 0
    assert "BINARY_CLASSIFICATION" in result.output


# --- import-mlflow ---


def test_model_import_mlflow(patch_client):
    result = runner.invoke(
        app,
        [
            "model",
            "import-mlflow",
            "model1",
            "-v",
            "v1",
            "--path",
            "/tmp/mlflow_model",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "Imported" in result.output
    model = patch_client.get_project("PROJ1").get_saved_model("model1")
    model.import_mlflow_version_from_path.assert_called_once_with(
        "v1", "/tmp/mlflow_model", code_env_name="LOCAL-CODE-ENV", set_active=True
    )


def test_model_import_mlflow_no_set_active(patch_client):
    result = runner.invoke(
        app,
        [
            "model",
            "import-mlflow",
            "model1",
            "-v",
            "v2",
            "--path",
            "/tmp/model",
            "--no-set-active",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    model = patch_client.get_project("PROJ1").get_saved_model("model1")
    model.import_mlflow_version_from_path.assert_called_once_with(
        "v2", "/tmp/model", code_env_name="LOCAL-CODE-ENV", set_active=False
    )


# --- create-external ---


def test_model_create_external(patch_client):
    result = runner.invoke(
        app,
        [
            "model",
            "create-external",
            "SageMaker Model",
            "-t",
            "BINARY_CLASSIFICATION",
            "--protocol",
            "sagemaker",
            "--region",
            "eu-west-1",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "Created" in result.output
    proj = patch_client.get_project("PROJ1")
    proj.create_external_model.assert_called_once_with(
        "SageMaker Model",
        "BINARY_CLASSIFICATION",
        {"protocol": "sagemaker", "region": "eu-west-1"},
    )


def test_model_create_external_with_connection(patch_client):
    result = runner.invoke(
        app,
        [
            "model",
            "create-external",
            "Vertex Model",
            "-t",
            "REGRESSION",
            "--protocol",
            "vertex-ai",
            "--region",
            "europe-west1",
            "--connection",
            "vertex_conn",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    proj = patch_client.get_project("PROJ1")
    proj.create_external_model.assert_called_once_with(
        "Vertex Model",
        "REGRESSION",
        {
            "protocol": "vertex-ai",
            "region": "europe-west1",
            "connection": "vertex_conn",
        },
    )


def test_model_create_external_json(patch_client):
    result = runner.invoke(
        app,
        [
            "model",
            "create-external",
            "Test",
            "-t",
            "MULTICLASS",
            "--protocol",
            "databricks",
            "--project",
            "PROJ1",
            "-o",
            "json",
        ],
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["id"] == "model1"


def test_model_create_external_invalid_type(patch_client):
    result = runner.invoke(
        app,
        [
            "model",
            "create-external",
            "Bad",
            "-t",
            "INVALID",
            "--protocol",
            "sagemaker",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code != 0
