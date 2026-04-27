"""Tests for api-service commands."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from dku_cli.main import app

runner = CliRunner()


def test_api_service_list(patch_client):
    result = runner.invoke(app, ["api-service", "list", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "myservice" in result.output


def test_api_service_list_json(patch_client):
    result = runner.invoke(
        app, ["api-service", "list", "--project", "PROJ1", "-o", "json"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert len(parsed) == 1
    assert parsed[0]["id"] == "myservice"


def test_api_service_create(patch_client):
    result = runner.invoke(
        app, ["api-service", "create", "newsvc", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    proj = patch_client.get_project("PROJ1")
    proj.create_api_service.assert_called_once_with("newsvc")


def test_api_service_get(patch_client):
    result = runner.invoke(
        app, ["api-service", "get", "myservice", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    assert "myservice" in result.output


def test_api_service_get_json(patch_client):
    result = runner.invoke(
        app, ["api-service", "get", "myservice", "--project", "PROJ1", "-o", "json"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["id"] == "myservice"
    assert "endpoints" in parsed


def test_api_service_create_package(patch_client):
    result = runner.invoke(
        app, ["api-service", "create-package", "myservice", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    proj = patch_client.get_project("PROJ1")
    svc = proj.get_api_service("myservice")
    svc.create_package.assert_called_once()


def test_api_service_list_packages(patch_client):
    result = runner.invoke(
        app, ["api-service", "list-packages", "myservice", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    assert "pkg1" in result.output


def test_api_service_list_packages_json(patch_client):
    result = runner.invoke(
        app,
        [
            "api-service",
            "list-packages",
            "myservice",
            "--project",
            "PROJ1",
            "-o",
            "json",
        ],
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert len(parsed) == 1
    assert parsed[0]["id"] == "pkg1"
    assert parsed[0]["created_on"] == "2025-01-01"


# --- add-endpoint ---


def test_api_service_add_endpoint_prediction(patch_client):
    result = runner.invoke(
        app,
        [
            "api-service",
            "add-endpoint",
            "myservice",
            "-e",
            "predict_churn",
            "-m",
            "model1",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "Added" in result.output
    assert "predict_churn" in result.output
    svc = patch_client.get_project("PROJ1").get_api_service("myservice")
    settings = svc.get_settings()
    settings.add_prediction_endpoint.assert_called_once_with("predict_churn", "model1")
    settings.save.assert_called_once()


def test_api_service_add_endpoint_forecasting(patch_client):
    result = runner.invoke(
        app,
        [
            "api-service",
            "add-endpoint",
            "myservice",
            "-e",
            "forecast_sales",
            "-m",
            "ts_model",
            "-t",
            "forecasting",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    svc = patch_client.get_project("PROJ1").get_api_service("myservice")
    svc.get_settings().add_forecasting_endpoint.assert_called_once_with(
        "forecast_sales", "ts_model"
    )


def test_api_service_add_endpoint_invalid_type(patch_client):
    result = runner.invoke(
        app,
        [
            "api-service",
            "add-endpoint",
            "myservice",
            "-e",
            "ep1",
            "-m",
            "m1",
            "-t",
            "invalid",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code != 0
    assert "prediction" in result.output  # shows supported types


# --- list-endpoints ---


def test_api_service_list_endpoints_table(patch_client):
    result = runner.invoke(
        app,
        ["api-service", "list-endpoints", "myservice", "--project", "PROJ1"],
    )
    assert result.exit_code == 0
    assert "predict_churn" in result.output
    assert "STD_PREDICTION" in result.output


def test_api_service_list_endpoints_json(patch_client):
    result = runner.invoke(
        app,
        [
            "api-service",
            "list-endpoints",
            "myservice",
            "--project",
            "PROJ1",
            "-o",
            "json",
        ],
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert len(parsed) == 1
    assert parsed[0]["id"] == "predict_churn"
    assert parsed[0]["type"] == "STD_PREDICTION"
    assert parsed[0]["modelRef"] == "model1"


def test_api_service_list_endpoints_empty(patch_client):
    svc = patch_client.get_project("PROJ1").get_api_service("myservice")
    svc.get_settings().endpoints = []
    result = runner.invoke(
        app,
        ["api-service", "list-endpoints", "myservice", "--project", "PROJ1"],
    )
    assert result.exit_code == 0
    assert "no endpoints" in result.output.lower()


# --- publish-package ---


def test_api_service_publish_package(patch_client):
    result = runner.invoke(
        app,
        [
            "api-service",
            "publish-package",
            "myservice",
            "--package",
            "pkg1",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "Published" in result.output
    svc = patch_client.get_project("PROJ1").get_api_service("myservice")
    svc.publish_package.assert_called_once_with("pkg1", published_service_id=None)


def test_api_service_publish_package_custom_service(patch_client):
    result = runner.invoke(
        app,
        [
            "api-service",
            "publish-package",
            "myservice",
            "--package",
            "pkg1",
            "--published-service",
            "prod_svc",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "prod_svc" in result.output
    svc = patch_client.get_project("PROJ1").get_api_service("myservice")
    svc.publish_package.assert_called_once_with("pkg1", published_service_id="prod_svc")


# --- delete-package ---


def test_api_service_delete_package(patch_client):
    result = runner.invoke(
        app,
        [
            "api-service",
            "delete-package",
            "myservice",
            "--package",
            "pkg1",
            "--project",
            "PROJ1",
            "--yes",
        ],
    )
    assert result.exit_code == 0
    assert "Deleted" in result.output
    svc = patch_client.get_project("PROJ1").get_api_service("myservice")
    svc.delete_package.assert_called_once_with("pkg1")
