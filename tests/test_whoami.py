"""Tests for whoami command."""

from __future__ import annotations

from typer.testing import CliRunner

from dku_cli.main import app

runner = CliRunner()


def test_whoami(patch_client):
    result = runner.invoke(app, ["whoami"])
    assert result.exit_code == 0
    assert "testuser" in result.output
    assert "◆" in result.output


def test_whoami_shows_groups(patch_client):
    result = runner.invoke(app, ["whoami"])
    assert result.exit_code == 0
    assert "admin" in result.output
