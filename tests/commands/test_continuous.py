"""Tests for continuous activity commands."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from dku_cli.main import app

runner = CliRunner()


def test_continuous_list_table(patch_client):
    result = runner.invoke(app, ["continuous", "list", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "stream_events" in result.output
    assert "STARTED" in result.output


def test_continuous_list_json(patch_client):
    result = runner.invoke(
        app, ["continuous", "list", "--project", "PROJ1", "-o", "json"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert len(parsed) == 1
    assert parsed[0]["recipeId"] == "stream_events"


def test_continuous_list_empty(patch_client):
    proj = patch_client.get_project("PROJ1")
    proj.list_continuous_activities.return_value = []
    result = runner.invoke(app, ["continuous", "list", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "no continuous" in result.output.lower()


def test_continuous_start(patch_client):
    result = runner.invoke(
        app, ["continuous", "start", "stream_events", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    assert "Started" in result.output
    proj = patch_client.get_project("PROJ1")
    proj.get_continuous_activity.assert_called_once_with("stream_events")
    proj.get_continuous_activity.return_value.start.assert_called_once()


def test_continuous_stop(patch_client):
    result = runner.invoke(
        app, ["continuous", "stop", "stream_events", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    assert "Stopped" in result.output


def test_continuous_status_table(patch_client):
    result = runner.invoke(
        app, ["continuous", "status", "stream_events", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    assert "STARTED" in result.output
    assert "RUNNING" in result.output


def test_continuous_status_json(patch_client):
    result = runner.invoke(
        app,
        ["continuous", "status", "stream_events", "--project", "PROJ1", "-o", "json"],
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["desiredState"] == "STARTED"
    assert parsed["mainLoopState"]["state"] == "RUNNING"
