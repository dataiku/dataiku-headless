"""Tests for flow commands."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from dku_cli.main import app

runner = CliRunner()


def test_flow_graph(patch_client):
    result = runner.invoke(app, ["flow", "graph", "--project", "PROJ1"])
    assert result.exit_code == 0


def test_flow_graph_json(patch_client):
    result = runner.invoke(app, ["flow", "graph", "--project", "PROJ1", "-o", "json"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert "nodes" in parsed


def test_flow_graph_table(patch_client):
    result = runner.invoke(app, ["flow", "graph", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "ds1" in result.output or "recipe1" in result.output


def test_flow_zones(patch_client):
    result = runner.invoke(app, ["flow", "zones", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "zone1" in result.output or "Default" in result.output


def test_flow_zones_json(patch_client):
    result = runner.invoke(app, ["flow", "zones", "--project", "PROJ1", "-o", "json"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert len(parsed) == 1
    assert parsed[0]["id"] == "zone1"
    assert parsed[0]["name"] == "Default"


def test_flow_create_zone(patch_client):
    result = runner.invoke(app, ["flow", "create-zone", "MyZone", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "Created zone" in result.output


def test_flow_propagate(patch_client):
    result = runner.invoke(app, ["flow", "propagate", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "success" in result.output.lower() or "propagation" in result.output.lower()


def test_flow_sources(patch_client):
    result = runner.invoke(app, ["flow", "sources", "--project", "PROJ1"])
    assert result.exit_code == 0
    # ds1 has successors ["recipe1"], recipe1 is downstream — so ds1 is the source
    assert "ds1" in result.output


def test_flow_sources_json(patch_client):
    result = runner.invoke(app, ["flow", "sources", "--project", "PROJ1", "-o", "json"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    source_ids = [s["id"] for s in parsed]
    assert "ds1" in source_ids
    # recipe1 is a successor of ds1, so it should NOT be a source
    assert "recipe1" not in source_ids


def test_flow_successors(patch_client):
    result = runner.invoke(app, ["flow", "successors", "ds1", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "recipe1" in result.output


def test_flow_successors_empty(patch_client):
    result = runner.invoke(app, ["flow", "successors", "recipe1", "--project", "PROJ1"])
    assert result.exit_code == 0
    # recipe1 has no successors, so output should be empty table or empty json
