"""Issue #196 — insight set-definition backfills identity fields on a
params-only JSON instead of crashing with "DSS API error: 'id'"."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

from typer.testing import CliRunner

from dku_cli.commands.insight import app

runner = CliRunner()


class _Settings:
    def __init__(self, raw):
        self._raw = raw
        self.saved = None

    def get_raw(self):
        return self._raw

    def save(self):
        self.saved = dict(self._raw)


def _wire(monkeypatch, initial_raw):
    settings = _Settings(initial_raw)
    insight = MagicMock()
    insight.get_settings.return_value = settings
    client = MagicMock()
    client.get_project.return_value.get_insight.return_value = insight
    monkeypatch.setattr(
        "dku_cli.commands.insight.get_client_from_ctx", lambda ctx: client
    )
    return settings


def test_set_definition_backfills_id_on_params_only(monkeypatch):
    settings = _wire(monkeypatch, {})
    result = runner.invoke(
        app,
        [
            "set-definition",
            "insight1",
            "-P",
            "PROJ1",
            "-d",
            json.dumps({"type": "chart", "params": {"datasetSmartName": "x"}}),
        ],
    )
    assert result.exit_code == 0, result.output
    assert settings.saved is not None
    assert settings.saved["id"] == "insight1"
    assert settings.saved["projectKey"] == "PROJ1"


def test_set_definition_preserves_prior_name_owner(monkeypatch):
    settings = _wire(
        monkeypatch,
        {"id": "insight1", "name": "Old Name", "owner": "alice", "type": "chart"},
    )
    result = runner.invoke(
        app,
        [
            "set-definition",
            "insight1",
            "-P",
            "PROJ1",
            "-d",
            json.dumps({"type": "report", "params": {}}),
        ],
    )
    assert result.exit_code == 0, result.output
    assert settings.saved["id"] == "insight1"
    assert settings.saved["name"] == "Old Name"
    assert settings.saved["owner"] == "alice"
    assert settings.saved["type"] == "report"
