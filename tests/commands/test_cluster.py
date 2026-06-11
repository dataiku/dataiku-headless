"""Tests for cluster commands."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from dku_cli.main import app

runner = CliRunner()


def test_cluster_list(patch_client):
    result = runner.invoke(app, ["cluster", "list"])
    assert result.exit_code == 0
    assert "k8s-prod" in result.output
    assert "KUBERNETES" in result.output


def test_cluster_list_json(patch_client):
    result = runner.invoke(app, ["--format", "json", "cluster", "list"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert len(parsed) == 1
    assert parsed[0]["name"] == "k8s-prod"


def test_cluster_list_empty(patch_client):
    patch_client.list_clusters.return_value = []
    result = runner.invoke(app, ["cluster", "list"])
    assert result.exit_code == 0
    assert "no clusters" in result.output.lower()


def test_cluster_get(patch_client):
    result = runner.invoke(app, ["cluster", "get", "k8s-prod"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["name"] == "k8s-prod"


def test_cluster_create(patch_client):
    result = runner.invoke(
        app, ["cluster", "create", "new-cluster", "--type", "manual"]
    )
    assert result.exit_code == 0
    assert "Created" in result.output


def test_cluster_start(patch_client):
    result = runner.invoke(app, ["cluster", "start", "k8s-prod"])
    assert result.exit_code == 0
    assert "Started" in result.output


def test_cluster_stop(patch_client):
    result = runner.invoke(app, ["cluster", "stop", "k8s-prod"])
    assert result.exit_code == 0
    assert "Stopped" in result.output


def test_cluster_status(patch_client):
    result = runner.invoke(app, ["cluster", "status", "k8s-prod"])
    assert result.exit_code == 0
    assert "RUNNING" in result.output


def test_cluster_status_json(patch_client):
    result = runner.invoke(app, ["--format", "json", "cluster", "status", "k8s-prod"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["state"] == "RUNNING"


def test_cluster_delete(patch_client):
    result = runner.invoke(app, ["cluster", "delete", "k8s-prod", "--yes"])
    assert result.exit_code == 0
    assert "Deleted" in result.output
