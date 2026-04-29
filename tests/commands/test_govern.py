"""Tests for dku govern top-level commands."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from dku_cli.main import app

runner = CliRunner()


def test_govern_whoami():
    client = MagicMock()
    client.get_auth_info.return_value = {
        "authIdentifier": "api:govern_key",
        "groups": ["admins"],
    }
    with (
        patch("dku_cli.helpers.resolve_node_type", return_value="GOVERN"),
        patch("dku_cli.helpers.get_govern_client", return_value=client),
    ):
        result = runner.invoke(app, ["govern", "whoami"])

    assert result.exit_code == 0
    assert "govern_key" in result.output


def test_govern_whoami_json():
    client = MagicMock()
    client.get_auth_info.return_value = {"authIdentifier": "api:govern_key"}
    with (
        patch("dku_cli.helpers.resolve_node_type", return_value="GOVERN"),
        patch("dku_cli.helpers.get_govern_client", return_value=client),
    ):
        result = runner.invoke(app, ["govern", "whoami", "-o", "json"])

    assert result.exit_code == 0
    assert '"authIdentifier": "api:govern_key"' in result.output


def test_govern_info():
    client = MagicMock()
    instance = MagicMock()
    instance.node_id = "govern_node"
    instance.node_name = "IKU"
    instance.node_type = "GOVERN"
    client.get_instance_info.return_value = instance
    with (
        patch("dku_cli.helpers.resolve_node_type", return_value="GOVERN"),
        patch("dku_cli.helpers.get_govern_client", return_value=client),
    ):
        result = runner.invoke(app, ["govern", "info"])

    assert result.exit_code == 0
    assert "govern_node" in result.output or "IKU" in result.output


def test_govern_info_json():
    client = MagicMock()
    instance = MagicMock()
    instance.node_id = "govern_node"
    instance.node_name = "IKU"
    instance.node_type = "GOVERN"
    client.get_instance_info.return_value = instance
    with (
        patch("dku_cli.helpers.resolve_node_type", return_value="GOVERN"),
        patch("dku_cli.helpers.get_govern_client", return_value=client),
    ):
        result = runner.invoke(app, ["govern", "info", "-o", "json"])

    assert result.exit_code == 0
    assert '"node_type": "GOVERN"' in result.output
    assert '"node_name": "IKU"' in result.output


def test_govern_refuses_non_govern_profile():
    with patch("dku_cli.helpers.resolve_node_type", return_value="DESIGN"):
        result = runner.invoke(app, ["govern", "whoami"])

    assert result.exit_code == 4
    assert "requires: GOVERN" in result.output
