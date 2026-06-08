"""Dataset file-bridge tests (create-from-file + download).

Relocated from the monolithic tests/commands/test_dataset.py (split into this
package) when PR #124's file bridge was folded into the consolidated branch.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from tests.commands.dataset.helpers import app, runner


def _wire_dataset(monkeypatch):
    """Patch get_client_from_ctx to return a controllable dataset mock."""
    ds = MagicMock()
    client = MagicMock()
    client.get_project.return_value.get_dataset.return_value = ds
    client.get_project.return_value.create_upload_dataset.return_value = ds
    monkeypatch.setattr(
        "dku_cli.commands.dataset.get_client_from_ctx", lambda ctx: client
    )
    return client, ds


def test_create_from_file_missing_local_file():
    result = runner.invoke(
        app, ["dataset", "create-from-file", "x", "/no/such/file.csv", "-P", "PROJ1"]
    )
    assert result.exit_code == 1
    assert "not found" in result.output.lower()


def test_download_writes_csv_to_file(tmp_path, monkeypatch):
    _, ds = _wire_dataset(monkeypatch)
    ds.get_schema.return_value = {"columns": [{"name": "a"}, {"name": "b"}]}
    ds.iter_rows.return_value = iter([[1, "x"], [2, "y"]])
    out = tmp_path / "o.csv"
    result = runner.invoke(app, ["dataset", "download", "ds", str(out), "-P", "PROJ1"])
    assert result.exit_code == 0
    text = out.read_text(encoding="utf-8")
    assert "a,b" in text
    assert "1,x" in text and "2,y" in text


def test_download_to_stdout_is_clean_csv(monkeypatch):
    _, ds = _wire_dataset(monkeypatch)
    ds.get_schema.return_value = {"columns": [{"name": "a"}]}
    ds.iter_rows.return_value = iter([["v1"], ["v2"]])
    result = runner.invoke(app, ["dataset", "download", "ds", "-P", "PROJ1"])
    assert result.exit_code == 0
    assert "v1" in result.output and "v2" in result.output
    assert "Downloaded" not in result.output  # no success line polluting stdout CSV


def test_download_dash_streams_to_stdout(tmp_path, monkeypatch):
    """`download ds -` honors the '-' = stdout sentinel: it streams CSV to
    stdout instead of silently creating a file literally named '-' in cwd."""
    _, ds = _wire_dataset(monkeypatch)
    ds.get_schema.return_value = {"columns": [{"name": "a"}, {"name": "b"}]}
    ds.iter_rows.return_value = iter([[1, "x"], [2, "y"]])
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["dataset", "download", "ds", "-", "-P", "PROJ1"])
    assert result.exit_code == 0
    assert "a,b" in result.output  # CSV header streamed to stdout
    # No file literally named '-' was created in the working directory.
    assert not (tmp_path / "-").exists()


def test_download_respects_limit(monkeypatch):
    _, ds = _wire_dataset(monkeypatch)
    ds.get_schema.return_value = {"columns": [{"name": "a"}]}
    ds.iter_rows.return_value = iter([["1"], ["2"], ["3"], ["4"]])
    result = runner.invoke(
        app, ["dataset", "download", "ds", "-P", "PROJ1", "--limit", "2"]
    )
    assert result.exit_code == 0
    lines = [ln for ln in result.output.strip().splitlines() if ln]
    assert lines == ["a", "1", "2"]  # header + 2 rows only


def test_download_limit_zero_writes_header_only(monkeypatch):
    """--limit 0 must yield zero data rows (header only), not download everything."""
    _, ds = _wire_dataset(monkeypatch)
    ds.get_schema.return_value = {"columns": [{"name": "a"}]}
    ds.iter_rows.return_value = iter([["1"], ["2"], ["3"], ["4"]])
    result = runner.invoke(
        app, ["dataset", "download", "ds", "-P", "PROJ1", "--limit", "0"]
    )
    assert result.exit_code == 0
    lines = [ln for ln in result.output.strip().splitlines() if ln]
    assert lines == ["a"]  # header only, no data rows


def test_download_negative_limit_rejected(monkeypatch):
    _, ds = _wire_dataset(monkeypatch)
    ds.get_schema.return_value = {"columns": [{"name": "a"}]}
    ds.iter_rows.return_value = iter([["1"], ["2"]])
    result = runner.invoke(
        app, ["dataset", "download", "ds", "-P", "PROJ1", "--limit", "-1"]
    )
    assert result.exit_code != 0
    assert "non-negative" in result.output
