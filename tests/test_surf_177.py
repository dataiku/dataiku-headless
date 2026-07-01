"""Issue #177 — dataset upload duplicate-name handling.

The original bug was duplicate file upload ambiguity. Uploading a different
file into a non-empty UploadedFiles dataset is valid DSS behavior and must not
be blocked by a broad preflight.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from typer.testing import CliRunner

from dku_cli.commands.dataset import app

runner = CliRunner()


def _wire(monkeypatch):
    ds = MagicMock()
    client = MagicMock()
    client.get_project.return_value.get_dataset.return_value = ds
    monkeypatch.setattr(
        "dku_cli.commands.dataset.get_client_from_ctx", lambda ctx: client
    )
    return ds


def _csv(tmp_path, name="data.csv"):
    p = tmp_path / name
    p.write_text("a,b\n1,2\n")
    return str(p)


def test_upload_proceeds_for_additional_file(monkeypatch, tmp_path):
    ds = _wire(monkeypatch)
    result = runner.invoke(
        app,
        ["upload", "myds", _csv(tmp_path, "new.csv"), "-P", "PROJ1", "--no-autodetect"],
    )
    assert result.exit_code == 0, result.output
    ds.uploaded_add_file.assert_called_once()
    ds.uploaded_list_files.assert_not_called()
    ds.clear.assert_not_called()


def test_upload_duplicate_name_steers_to_overwrite(monkeypatch, tmp_path):
    ds = _wire(monkeypatch)
    ds.uploaded_add_file.side_effect = Exception("409 Conflict: file already exists")
    result = runner.invoke(
        app,
        ["upload", "myds", _csv(tmp_path), "-P", "PROJ1", "--no-autodetect"],
    )
    assert result.exit_code != 0, result.output
    assert "already uploaded" in result.output
    assert "--overwrite" in result.output
    ds.uploaded_add_file.assert_called_once()
    ds.clear.assert_not_called()


def test_upload_overwrite_clears_before_upload(monkeypatch, tmp_path):
    ds = _wire(monkeypatch)
    result = runner.invoke(
        app,
        [
            "upload",
            "myds",
            _csv(tmp_path),
            "-P",
            "PROJ1",
            "--no-autodetect",
            "--overwrite",
            "--yes",
        ],
    )
    assert result.exit_code == 0, result.output
    ds.clear.assert_called_once()
    ds.uploaded_add_file.assert_called_once()
