"""Tests for streaming endpoint commands."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from dku_cli.main import app

runner = CliRunner()


def test_streaming_list_table(patch_client):
    result = runner.invoke(app, ["streaming", "list", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "events_stream" in result.output
    assert "kafka" in result.output


def test_streaming_list_json(patch_client):
    result = runner.invoke(
        app, ["streaming", "list", "--project", "PROJ1", "-o", "json"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert len(parsed) == 1
    assert parsed[0]["id"] == "events_stream"
    assert parsed[0]["type"] == "kafka"


def test_streaming_list_empty(patch_client):
    proj = patch_client.get_project("PROJ1")
    proj.list_streaming_endpoints.return_value = []
    result = runner.invoke(app, ["streaming", "list", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "no streaming" in result.output.lower()


def test_streaming_create(patch_client):
    result = runner.invoke(
        app,
        [
            "streaming",
            "create",
            "my_stream",
            "--type",
            "kafka",
            "--connection",
            "kafka_conn",
            "--topic",
            "events",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "Created" in result.output
    proj = patch_client.get_project("PROJ1")
    proj.create_streaming_endpoint.assert_called_once_with(
        "my_stream",
        "kafka",
        params={"connection": "kafka_conn", "topic": "events"},
    )


def test_streaming_get(patch_client):
    result = runner.invoke(
        app, ["streaming", "get", "events_stream", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["type"] == "kafka"


def test_streaming_delete(patch_client):
    result = runner.invoke(
        app,
        ["streaming", "delete", "events_stream", "--yes", "--project", "PROJ1"],
    )
    assert result.exit_code == 0
    assert "Deleted" in result.output


def test_streaming_schema(patch_client):
    result = runner.invoke(
        app, ["streaming", "schema", "events_stream", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    assert "event_id" in result.output
    assert "timestamp" in result.output


def test_streaming_schema_json(patch_client):
    result = runner.invoke(
        app,
        ["streaming", "schema", "events_stream", "--project", "PROJ1", "-o", "json"],
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert len(parsed["columns"]) == 2


def test_streaming_set_schema(patch_client):
    schema = json.dumps({"columns": [{"name": "id", "type": "string"}]})
    result = runner.invoke(
        app,
        [
            "streaming",
            "set-schema",
            "events_stream",
            "-d",
            schema,
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "Updated" in result.output
    se = patch_client.get_project("PROJ1").get_streaming_endpoint("events_stream")
    se.set_schema.assert_called_once()
