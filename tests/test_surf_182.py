"""Issue #182 — SELECT result title carries the row count."""

from __future__ import annotations

from typer.testing import CliRunner

from dku_cli.commands.sql import app

runner = CliRunner()


class _FakeResult:
    def __init__(self, schema, rows):
        self._schema = schema
        self._rows = rows

    def get_schema(self):
        return self._schema

    def iter_rows(self):
        return iter(self._rows)


class _FakeClient:
    def __init__(self, result):
        self._result = result

    def sql_query(self, *args, **kwargs):
        return self._result


def _wire(monkeypatch, schema, rows):
    client = _FakeClient(_FakeResult(schema, rows))
    monkeypatch.setattr("dku_cli.commands.sql.get_client_from_ctx", lambda ctx: client)
    return client


def test_zero_row_select_reports_count(monkeypatch):
    _wire(monkeypatch, [{"name": "c"}], [])
    result = runner.invoke(app, ["SELECT 1", "-c", "myconn"])
    assert result.exit_code == 0, result.stdout + result.stderr
    assert "0 row(s)" in result.stderr
    assert "myconn" in result.stderr


def test_nonzero_row_select_reports_count(monkeypatch):
    _wire(monkeypatch, [{"name": "c"}], [["a"], ["b"], ["c"]])
    result = runner.invoke(app, ["SELECT c FROM t", "-c", "myconn"])
    assert result.exit_code == 0, result.stdout + result.stderr
    assert "3 row(s)" in result.stderr
