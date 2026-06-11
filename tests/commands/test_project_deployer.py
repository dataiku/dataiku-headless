"""Tests for project-deployer commands."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from dku_cli.main import app

runner = CliRunner()


def test_list_infras_table(patch_client):
    result = runner.invoke(app, ["project-deployer", "list-infras"])
    assert result.exit_code == 0
    assert "auto_infra1" in result.output
    assert "STATIC" in result.output


def test_list_infras_json(patch_client):
    result = runner.invoke(app, ["--format", "json", "project-deployer", "list-infras"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert len(parsed) == 1
    assert parsed[0]["id"] == "auto_infra1"
    assert parsed[0]["type"] == "STATIC"


def test_list_projects_table(patch_client):
    result = runner.invoke(app, ["project-deployer", "list-projects"])
    assert result.exit_code == 0
    assert "dp1" in result.output


def test_list_projects_json(patch_client):
    result = runner.invoke(
        app, ["--format", "json", "project-deployer", "list-projects"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert len(parsed) == 1
    assert parsed[0]["id"] == "dp1"


def test_list_deployments_table(patch_client):
    result = runner.invoke(app, ["project-deployer", "list-deployments"])
    assert result.exit_code == 0
    assert "pdep1" in result.output
    assert "dp1" in result.output
    assert "auto_infra1" in result.output


def test_list_deployments_json(patch_client):
    result = runner.invoke(
        app, ["--format", "json", "project-deployer", "list-deployments"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert len(parsed) == 1
    assert parsed[0]["id"] == "pdep1"
    assert parsed[0]["project_id"] == "dp1"
    assert parsed[0]["infra_id"] == "auto_infra1"


def test_create_deployment(patch_client):
    result = runner.invoke(
        app,
        [
            "project-deployer",
            "create-deployment",
            "--id",
            "new_pdep",
            "--project-id",
            "dp1",
            "--infra-id",
            "auto_infra1",
            "--bundle-id",
            "v1",
        ],
    )
    assert result.exit_code == 0
    deployer = patch_client.get_projectdeployer()
    deployer.create_deployment.assert_called_once_with(
        "new_pdep", "dp1", "auto_infra1", "v1", ignore_warnings=False
    )


def test_create_deployment_ignore_warnings(patch_client):
    result = runner.invoke(
        app,
        [
            "project-deployer",
            "create-deployment",
            "--id",
            "new_pdep",
            "--project-id",
            "dp1",
            "--infra-id",
            "auto_infra1",
            "--bundle-id",
            "v1",
            "--ignore-warnings",
        ],
    )
    assert result.exit_code == 0
    deployer = patch_client.get_projectdeployer()
    deployer.create_deployment.assert_called_once_with(
        "new_pdep", "dp1", "auto_infra1", "v1", ignore_warnings=True
    )


def test_get_deployment(patch_client):
    result = runner.invoke(
        app, ["--format", "json", "project-deployer", "get-deployment", "pdep1"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["id"] == "pdep1"
    assert parsed["projectId"] == "dp1"


def test_update_deployment_wait(patch_client):
    result = runner.invoke(app, ["project-deployer", "update-deployment", "pdep1"])
    assert result.exit_code == 0
    deployer = patch_client.get_projectdeployer()
    dep_handle = deployer.get_deployment("pdep1")
    dep_handle.start_update.assert_called_once()
    dep_handle.start_update().wait_for_result.assert_called_once()


def test_update_deployment_no_wait(patch_client):
    result = runner.invoke(
        app, ["project-deployer", "update-deployment", "pdep1", "--no-wait"]
    )
    assert result.exit_code == 0
    deployer = patch_client.get_projectdeployer()
    dep_handle = deployer.get_deployment("pdep1")
    dep_handle.start_update.assert_called_once()


def test_delete_deployment_with_yes(patch_client):
    result = runner.invoke(
        app, ["project-deployer", "delete-deployment", "pdep1", "--yes"]
    )
    assert result.exit_code == 0
    deployer = patch_client.get_projectdeployer()
    dep_handle = deployer.get_deployment("pdep1")
    dep_handle.delete.assert_called_once()


def test_delete_deployment_without_yes(patch_client):
    result = runner.invoke(
        app, ["project-deployer", "delete-deployment", "pdep1"], input="n\n"
    )
    assert result.exit_code != 0


def test_deployment_status(patch_client):
    result = runner.invoke(
        app, ["--format", "json", "project-deployer", "deployment-status", "pdep1"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["health"] == "HEALTHY"
