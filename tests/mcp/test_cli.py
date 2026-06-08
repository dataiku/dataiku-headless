"""CLI tests for the standalone dku-mcp launcher (``dku_cli.mcp.cli``).

The launcher is intentionally NOT a subcommand of the main ``dku`` app, so these
drive ``dku_cli.mcp.cli:app`` directly (the same object the ``dku-mcp`` console
script and ``python -m dku_cli.mcp`` resolve to).
"""

from __future__ import annotations

import json

from typer.testing import CliRunner

from dku_cli.mcp.cli import app

runner = CliRunner()


def test_help_lists_serve_and_doctor():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "serve" in result.output
    assert "doctor" in result.output
    assert "search" not in result.output


def test_doctor_table():
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0
    assert "sandbox backend" in result.output
    assert "dku on PATH" in result.output


def test_doctor_json_reports_backend():
    result = runner.invoke(app, ["doctor", "-o", "json"])
    assert result.exit_code == 0
    rows = json.loads(result.output)
    by_check = {r["check"]: r for r in rows}
    assert "sandbox backend" in by_check


def test_serve_rejects_bad_transport():
    result = runner.invoke(app, ["serve", "-t", "bogus"])
    assert result.exit_code == 1
    assert "transport" in result.output.lower()


def test_serve_help_does_not_start_server():
    result = runner.invoke(app, ["serve", "--help"])
    assert result.exit_code == 0
    assert "stdio" in result.output


def test_serve_http_refuses_without_bubblewrap():
    # bwrap is absent on this host → backend=subprocess → HTTP serving must
    # refuse rather than silently expose an unisolated executor to the network.
    result = runner.invoke(app, ["serve", "-t", "http", "--sandbox", "subprocess"])
    assert result.exit_code == 1
    assert "bubblewrap" in result.output.lower()


def test_serve_http_refuses_trust_local():
    # local trust (full host env, no sanitize/ulimits) must never back a
    # network-reachable server — refuse before anything starts.
    result = runner.invoke(app, ["serve", "-t", "http", "--trust", "local"])
    assert result.exit_code == 1
    assert "trust local" in result.output.lower()
