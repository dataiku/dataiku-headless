"""Tests for dku govern-time-series commands."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from dku_cli.main import app

runner = CliRunner()


def test_time_series_create(patch_client):
    result = runner.invoke(app, ["govern", "time-series", "create"])
    assert result.exit_code == 0
    gov = patch_client.get_govern_client()
    gov.create_time_series.assert_called_once()


def test_time_series_create_with_datapoints(patch_client):
    result = runner.invoke(
        app,
        [
            "govern",
            "time-series",
            "create",
            "--datapoints",
            '[{"timestamp": 1700000000000, "value": 42}]',
        ],
    )
    assert result.exit_code == 0


def test_time_series_create_json(patch_client):
    result = runner.invoke(
        app, ["--format", "quiet", "govern", "time-series", "create"]
    )
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["id"] == "ts.1"


def test_time_series_get(patch_client):
    result = runner.invoke(app, ["govern", "time-series", "get", "ts.1"])
    assert result.exit_code == 0


def test_time_series_get_json(patch_client):
    result = runner.invoke(
        app, ["--format", "json", "govern", "time-series", "get", "ts.1"]
    )
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert len(data) == 1
    assert data[0]["value"] == 42


def test_time_series_push_values(patch_client):
    result = runner.invoke(
        app,
        [
            "govern",
            "time-series",
            "push-values",
            "ts.1",
            "--datapoints",
            '[{"timestamp": 1700000120000, "value": 55}]',
        ],
    )
    assert result.exit_code == 0
    gov = patch_client.get_govern_client()
    gov.get_time_series.return_value.push_values.assert_called_once()


def test_time_series_delete_requires_confirm(patch_client):
    result = runner.invoke(app, ["govern", "time-series", "delete", "ts.1"])
    assert result.exit_code != 0


def test_time_series_delete(patch_client):
    result = runner.invoke(
        app, ["govern", "time-series", "delete", "ts.1", "--confirm"]
    )
    assert result.exit_code == 0
    gov = patch_client.get_govern_client()
    gov.get_time_series.return_value.delete.assert_called_once()
