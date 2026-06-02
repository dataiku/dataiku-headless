"""Tests for api-deployer commands."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from dku_cli.main import app

runner = CliRunner()


def test_list_infras_table(patch_client):
    result = runner.invoke(app, ["api-deployer", "list-infras"])
    assert result.exit_code == 0
    assert "infra1" in result.output
    assert "STATIC" in result.output


def test_list_infras_json(patch_client):
    result = runner.invoke(app, ["api-deployer", "list-infras", "-o", "json"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert len(parsed) == 1
    assert parsed[0]["id"] == "infra1"
    assert parsed[0]["type"] == "STATIC"


def test_list_services_table(patch_client):
    result = runner.invoke(app, ["api-deployer", "list-services"])
    assert result.exit_code == 0
    assert "svc1" in result.output


def test_list_services_json(patch_client):
    result = runner.invoke(app, ["api-deployer", "list-services", "-o", "json"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert len(parsed) == 1
    assert parsed[0]["id"] == "svc1"


def test_get_service(patch_client):
    result = runner.invoke(app, ["api-deployer", "get-service", "svc1", "-o", "json"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["id"] == "svc1"


def test_list_deployments_table(patch_client):
    result = runner.invoke(app, ["api-deployer", "list-deployments"])
    assert result.exit_code == 0
    assert "dep1" in result.output
    assert "svc1" in result.output
    assert "infra1" in result.output


def test_list_deployments_json(patch_client):
    result = runner.invoke(app, ["api-deployer", "list-deployments", "-o", "json"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert len(parsed) == 1
    assert parsed[0]["id"] == "dep1"
    assert parsed[0]["service_id"] == "svc1"
    assert parsed[0]["infra_id"] == "infra1"


def test_create_deployment(patch_client):
    result = runner.invoke(
        app,
        [
            "api-deployer",
            "create-deployment",
            "--id",
            "new_dep",
            "--service-id",
            "svc1",
            "--infra-id",
            "infra1",
            "--version",
            "v1",
        ],
    )
    assert result.exit_code == 0
    deployer = patch_client.get_apideployer()
    deployer.create_deployment.assert_called_once_with(
        "new_dep", "svc1", "infra1", "v1", ignore_warnings=False
    )


def test_create_deployment_ignore_warnings(patch_client):
    # --ignore-warnings lets agents proceed past non-fatal validation warnings
    # (e.g. "WARNING : Dataiku Govern Instance is unreachable") that otherwise
    # abort deployment creation on dev/sandbox instances.
    result = runner.invoke(
        app,
        [
            "api-deployer",
            "create-deployment",
            "--id",
            "new_dep",
            "--service-id",
            "svc1",
            "--infra-id",
            "infra1",
            "--version",
            "v1",
            "--ignore-warnings",
        ],
    )
    assert result.exit_code == 0
    deployer = patch_client.get_apideployer()
    deployer.create_deployment.assert_called_once_with(
        "new_dep", "svc1", "infra1", "v1", ignore_warnings=True
    )


def test_get_deployment(patch_client):
    result = runner.invoke(
        app, ["api-deployer", "get-deployment", "dep1", "-o", "json"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["id"] == "dep1"
    assert parsed["serviceId"] == "svc1"


def test_update_deployment_wait(patch_client):
    result = runner.invoke(app, ["api-deployer", "update-deployment", "dep1"])
    assert result.exit_code == 0
    deployer = patch_client.get_apideployer()
    dep_handle = deployer.get_deployment("dep1")
    dep_handle.start_update.assert_called_once()
    dep_handle.start_update().wait_for_result.assert_called_once()


def test_update_deployment_no_wait(patch_client):
    result = runner.invoke(
        app, ["api-deployer", "update-deployment", "dep1", "--no-wait"]
    )
    assert result.exit_code == 0
    deployer = patch_client.get_apideployer()
    dep_handle = deployer.get_deployment("dep1")
    dep_handle.start_update.assert_called_once()
    dep_handle.start_update.return_value.wait_for_result.assert_not_called()


def test_delete_deployment_with_yes(patch_client):
    result = runner.invoke(app, ["api-deployer", "delete-deployment", "dep1", "--yes"])
    assert result.exit_code == 0
    deployer = patch_client.get_apideployer()
    dep_handle = deployer.get_deployment("dep1")
    dep_handle.delete.assert_called_once()


def test_delete_deployment_without_yes(patch_client):
    result = runner.invoke(
        app, ["api-deployer", "delete-deployment", "dep1"], input="n\n"
    )
    assert result.exit_code != 0


def test_deployment_status(patch_client):
    result = runner.invoke(
        app, ["api-deployer", "deployment-status", "dep1", "-o", "json"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["health"] == "HEALTHY"
    assert parsed["deployment_id"] == "dep1"
    assert parsed["service_urls"] == ["https://apinode.example/public/api/v1/svc1"]


def test_deployment_status_still_initializing(patch_client):
    # get_service_urls() raises ValueError while the deployment is initializing;
    # the command must degrade to an empty list, not crash.
    deployer = patch_client.get_apideployer()
    status = deployer.get_deployment("dep1").get_status()
    status.get_service_urls.side_effect = ValueError("PublicURL not available")
    result = runner.invoke(
        app, ["api-deployer", "deployment-status", "dep1", "-o", "json"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["service_urls"] == []
