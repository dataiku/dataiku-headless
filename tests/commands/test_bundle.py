"""Tests for bundle commands."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from dku_cli.main import app

runner = CliRunner()


def test_bundle_list_table(patch_client):
    result = runner.invoke(app, ["bundle", "list", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "v1" in result.output
    assert "v2" in result.output


def test_bundle_list_json(patch_client):
    result = runner.invoke(app, ["bundle", "list", "--project", "PROJ1", "-o", "json"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert len(parsed) == 2
    assert parsed[0]["id"] == "v1"
    assert parsed[1]["id"] == "v2"


def test_bundle_export(patch_client):
    result = runner.invoke(app, ["bundle", "export", "v1", "--project", "PROJ1"])
    assert result.exit_code == 0
    proj = patch_client.get_project("PROJ1")
    proj.export_bundle.assert_called_once_with("v1")


def test_bundle_download(patch_client, tmp_path):
    result = runner.invoke(
        app, ["bundle", "download", "v1", "--project", "PROJ1", "--dest", str(tmp_path)]
    )
    assert result.exit_code == 0
    proj = patch_client.get_project("PROJ1")
    proj.download_exported_bundle_archive_to_file.assert_called_once_with(
        "v1", str(tmp_path / "PROJ1-v1.zip")
    )


def test_bundle_import(patch_client, tmp_path):
    archive = tmp_path / "bundle.zip"
    archive.write_bytes(b"fake zip content")

    result = runner.invoke(
        app, ["bundle", "import", str(archive), "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    proj = patch_client.get_project("PROJ1")
    proj.import_bundle_from_archive.assert_called_once()


def test_bundle_import_missing_file(patch_client):
    result = runner.invoke(
        app, ["bundle", "import", "/nonexistent/bundle.zip", "--project", "PROJ1"]
    )
    assert result.exit_code != 0


def test_bundle_activate(patch_client):
    result = runner.invoke(app, ["bundle", "activate", "v1", "--project", "PROJ1"])
    assert result.exit_code == 0
    proj = patch_client.get_project("PROJ1")
    proj.preload_bundle.assert_called_once_with("v1")
    proj.activate_bundle.assert_called_once_with("v1")
