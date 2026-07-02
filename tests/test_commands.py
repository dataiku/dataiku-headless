"""Tests for the `dku commands` full-index listing."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from dku_cli.main import app

runner = CliRunner()


def test_commands_default_is_tsv():
    result = runner.invoke(app, ["commands"])
    assert result.exit_code == 0
    header, *rows = result.output.splitlines()
    assert header == "group\tcommand\tdescription"
    assert any(row.startswith("dataset\tshare\t") for row in rows)
    assert any(row.startswith("dataset\tmetrics run\t") for row in rows)
    assert any(row.startswith("root\twhoami\t") for row in rows)


def test_commands_json_format():
    result = runner.invoke(app, ["commands", "--format", "json"])
    assert result.exit_code == 0
    rows = json.loads(result.output)
    assert any(r["group"] == "recipe" and r["command"] == "create-join" for r in rows)
    assert any(
        r["group"] == "govern" and r["command"] == "blueprint list-signoff-configs"
        for r in rows
    )


def test_commands_ids_format_uses_full_paths():
    result = runner.invoke(app, ["commands", "--format", "ids"])
    assert result.exit_code == 0
    paths = result.output.splitlines()
    assert "dataset metrics run" in paths
    assert "govern blueprint list-signoff-configs" in paths
    assert "whoami" in paths
    assert "commands" in paths
    assert "admin" not in paths


def test_commands_excludes_hidden_groups():
    result = runner.invoke(app, ["commands"])
    assert result.exit_code == 0
    groups = {line.split("\t", 1)[0] for line in result.output.splitlines()[1:]}
    assert "managedfolder" not in groups
    assert "managed-folder" not in groups
