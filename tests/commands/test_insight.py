"""Tests for insight commands."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from dku_cli.main import app

runner = CliRunner()


def test_insight_list(patch_client):
    result = runner.invoke(app, ["insight", "list", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "insight1" in result.output


def test_insight_list_json(patch_client):
    result = runner.invoke(app, ["insight", "list", "--project", "PROJ1", "-o", "json"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed[0]["id"] == "insight1"
    assert parsed[0]["type"] == "chart"


def test_insight_get(patch_client):
    result = runner.invoke(app, ["insight", "get", "insight1", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "insight1" in result.output


def test_insight_get_json(patch_client):
    result = runner.invoke(app, ["insight", "get", "insight1", "--project", "PROJ1", "-o", "json"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["id"] == "insight1"
    assert parsed["type"] == "chart"


def test_insight_create(patch_client):
    result = runner.invoke(app, ["insight", "create", "My Insight", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "Created insight" in result.output
    assert "new_insight_1" in result.output
    proj = patch_client.get_project("PROJ1")
    proj.create_insight.assert_called_once_with({"type": "dataset_table", "name": "My Insight"})


def test_insight_create_with_type(patch_client):
    result = runner.invoke(
        app,
        ["insight", "create", "My Chart", "--project", "PROJ1", "--type", "chart"],
    )
    assert result.exit_code == 0
    proj = patch_client.get_project("PROJ1")
    proj.create_insight.assert_called_once_with({"type": "chart", "name": "My Chart"})


def test_insight_create_with_definition(patch_client):
    defn = json.dumps({"type": "chart", "name": "Custom", "chartDef": {"type": "bars"}})
    result = runner.invoke(
        app,
        ["insight", "create", "Custom", "--project", "PROJ1", "--definition", defn],
    )
    assert result.exit_code == 0
    proj = patch_client.get_project("PROJ1")
    call_args = proj.create_insight.call_args[0][0]
    assert call_args["type"] == "chart"
    assert call_args["chartDef"] == {"type": "bars"}


def test_insight_create_if_not_exists(patch_client):
    proj = patch_client.get_project("PROJ1")
    proj.create_insight.side_effect = Exception("409 Conflict: insight already exists")
    result = runner.invoke(
        app,
        ["insight", "create", "Existing", "--project", "PROJ1", "--if-not-exists"],
    )
    assert result.exit_code == 0
    assert "already exists" in result.output


def test_insight_create_already_exists_fails(patch_client):
    proj = patch_client.get_project("PROJ1")
    proj.create_insight.side_effect = Exception("409 Conflict: insight already exists")
    result = runner.invoke(
        app,
        ["insight", "create", "Existing", "--project", "PROJ1"],
    )
    assert result.exit_code != 0


def test_insight_delete(patch_client):
    result = runner.invoke(app, ["insight", "delete", "insight1", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "Deleted insight" in result.output
    proj = patch_client.get_project("PROJ1")
    insight = proj.get_insight("insight1")
    insight.delete.assert_called_once()


def test_insight_get_definition(patch_client):
    result = runner.invoke(app, ["insight", "get-definition", "insight1", "--project", "PROJ1"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["id"] == "insight1"
    assert parsed["type"] == "chart"


def test_insight_set_definition(patch_client):
    new_def = json.dumps({"id": "insight1", "name": "Updated", "type": "chart", "params": {"x": 1}})
    result = runner.invoke(
        app,
        ["insight", "set-definition", "insight1", "--project", "PROJ1", "--definition", new_def],
    )
    assert result.exit_code == 0
    assert "Updated definition" in result.output
    proj = patch_client.get_project("PROJ1")
    insight = proj.get_insight("insight1")
    insight.get_settings().save.assert_called_once()


def test_insight_set_definition_from_file(tmp_path, patch_client):
    defn_file = tmp_path / "insight_def.json"
    defn_file.write_text(json.dumps({"id": "insight1", "name": "FromFile", "type": "chart"}))
    result = runner.invoke(
        app,
        ["insight", "set-definition", "insight1", "--project", "PROJ1", "--definition", f"@{defn_file}"],
    )
    assert result.exit_code == 0
    assert "Updated definition" in result.output
    proj = patch_client.get_project("PROJ1")
    insight = proj.get_insight("insight1")
    insight.get_settings().save.assert_called_once()
