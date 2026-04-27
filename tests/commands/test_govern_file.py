"""Tests for dku govern-file commands."""

from __future__ import annotations

import json
import tempfile
import os

from typer.testing import CliRunner

from dku_cli.main import app

runner = CliRunner()


def test_file_upload(patch_client):
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write("test content")
        f.flush()
        tmp_path = f.name
    try:
        result = runner.invoke(app, ["govern", "file", "upload", tmp_path])
        assert result.exit_code == 0
        assert "uf.1" in result.output
    finally:
        os.unlink(tmp_path)


def test_file_upload_not_found(patch_client):
    result = runner.invoke(app, ["govern", "file", "upload", "/nonexistent/file.txt"])
    assert result.exit_code != 0


def test_file_get(patch_client):
    result = runner.invoke(app, ["govern", "file", "get", "uf.1"])
    assert result.exit_code == 0


def test_file_get_json(patch_client):
    result = runner.invoke(app, ["govern", "file", "get", "uf.1", "-o", "json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["id"] == "uf.1"
    assert data["name"] == "report.pdf"


def test_file_download(patch_client):
    with tempfile.TemporaryDirectory() as tmpdir:
        dest = os.path.join(tmpdir, "downloaded.pdf")
        result = runner.invoke(
            app, ["govern", "file", "download", "uf.1", "--dest", dest]
        )
        assert result.exit_code == 0
        assert os.path.exists(dest)
        with open(dest, "rb") as f:
            assert f.read() == b"fake file content"
