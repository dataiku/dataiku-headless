"""Tests for folder commands."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from typer.testing import CliRunner

from dku_cli.main import app

runner = CliRunner()


def test_folder_list(patch_client):
    result = runner.invoke(app, ["folder", "list", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "folder1" in result.output


def test_folder_list_json(patch_client):
    result = runner.invoke(app, ["folder", "list", "--project", "PROJ1", "-o", "json"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed[0]["id"] == "folder1"


def test_folder_ls(patch_client):
    result = runner.invoke(app, ["folder", "ls", "folder1", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "data.csv" in result.output


def test_folder_upload(patch_client):
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
        f.write(b"col1,col2\na,b\n")
        f.flush()
        result = runner.invoke(app, ["folder", "upload", "folder1", f.name, "--project", "PROJ1"])
        assert result.exit_code == 0
        Path(f.name).unlink()


def test_folder_upload_missing_file(patch_client):
    result = runner.invoke(app, ["folder", "upload", "folder1", "/nonexistent/file.csv", "--project", "PROJ1"])
    assert result.exit_code != 0
