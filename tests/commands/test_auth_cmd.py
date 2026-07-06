"""Tests for auth commands."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from dku_cli.auth import KeyResult, KeyStatus
from dku_cli.main import app

runner = CliRunner()


def _key_result(key):
    """Mirror get_api_key_with_status: found key → OK, missing → MISSING."""
    return KeyResult(key, KeyStatus.OK if key else KeyStatus.MISSING)


def test_auth_logout_all_clears_profile_config():
    with (
        patch(
            "dku_cli.commands.auth_cmd.get_all_profiles",
            return_value={"default": {}, "prod": {}},
        ),
        patch("dku_cli.commands.auth_cmd.delete_api_key") as mock_delete,
        patch(
            "dku_cli.commands.auth_cmd.clear_profile_configs", return_value=2
        ) as mock_clear,
    ):
        result = runner.invoke(app, ["auth", "logout", "--all"])

    assert result.exit_code == 0
    assert mock_delete.call_count == 2
    mock_clear.assert_called_once_with()


def test_auth_logout_removes_profile_from_config():
    with (
        patch("dku_cli.commands.auth_cmd.get_active_profile", return_value="default"),
        patch("dku_cli.commands.auth_cmd.delete_api_key", return_value=False),
        patch(
            "dku_cli.commands.auth_cmd.delete_profile_config", return_value=True
        ) as mock_delete_profile,
    ):
        result = runner.invoke(app, ["auth", "logout"])

    assert result.exit_code == 0
    mock_delete_profile.assert_called_once_with("default")


def test_auth_status_shows_sources_and_project(patch_client):
    project = MagicMock()
    project.get_metadata.return_value = {"label": "Project One"}
    patch_client.get_project.return_value = project

    with (
        patch("dku_cli.commands.auth_cmd.get_active_profile", return_value="default"),
        patch(
            "dku_cli.commands.auth_cmd.get_profile_config",
            return_value={"url": "https://dss.example.com", "default_project": "PROJ1"},
        ),
        patch(
            "dku_cli.commands.auth_cmd.resolve_auth",
            return_value=("https://dss.example.com", "secret"),
        ),
        patch("dataikuapi.DSSClient", return_value=patch_client),
    ):
        result = runner.invoke(app, ["auth", "status"])

    assert result.exit_code == 0
    assert "Profile:" in result.output
    assert "URL Src:" in result.output
    assert "Key Src:" in result.output
    assert "DSS:" in result.output
    assert "Project:" in result.output
    assert "Project OK:" in result.output


def test_auth_status_project_access_error(patch_client):
    patch_client.get_project.side_effect = Exception(
        "NotFoundException: Project MISSING does not exist"
    )

    with (
        patch("dku_cli.commands.auth_cmd.get_active_profile", return_value="default"),
        patch(
            "dku_cli.commands.auth_cmd.get_profile_config",
            return_value={
                "url": "https://dss.example.com",
                "default_project": "MISSING",
            },
        ),
        patch(
            "dku_cli.commands.auth_cmd.resolve_auth",
            return_value=("https://dss.example.com", "secret"),
        ),
        patch("dataikuapi.DSSClient", return_value=patch_client),
    ):
        result = runner.invoke(app, ["auth", "status"])

    assert result.exit_code == 0
    assert "Project OK:" in result.output
    assert "NotFoundException: Project MISSING does not exist" in result.output


def test_auth_status_uses_requested_profile_default_project(patch_client):
    project = MagicMock()
    project.get_metadata.return_value = {"label": "Other Project"}
    patch_client.get_project.return_value = project

    profile_cfgs = {
        "default": {"url": "https://dss.example.com", "default_project": "PROJ1"},
        "other": {"url": "https://dss.example.com", "default_project": "PROJ2"},
    }

    with (
        patch("dku_cli.commands.auth_cmd.get_active_profile", return_value="default"),
        patch(
            "dku_cli.commands.auth_cmd.get_profile_config",
            side_effect=lambda profile: profile_cfgs[profile],
        ),
        patch(
            "dku_cli.commands.auth_cmd.resolve_auth",
            return_value=("https://dss.example.com", "secret"),
        ),
        patch("dataikuapi.DSSClient", return_value=patch_client),
    ):
        result = runner.invoke(app, ["--profile", "other", "auth", "status"])

    assert result.exit_code == 0
    assert "PROJ2 [profile:other]" in result.output
    patch_client.get_project.assert_called_once_with("PROJ2")


def test_auth_switch_exits_zero_on_success():
    """Regression: auth switch must exit 0 on success (not 2) for set -e scripts."""
    with (
        patch(
            "dku_cli.commands.auth_cmd.get_all_profiles",
            return_value={"default": {}, "analytics": {}},
        ),
        patch("dku_cli.commands.auth_cmd.set_active_profile") as mock_set,
    ):
        result = runner.invoke(app, ["auth", "switch", "analytics"])

    assert result.exit_code == 0
    assert "Switched to profile" in result.output
    mock_set.assert_called_once_with("analytics")


def test_auth_switch_nonexistent_profile_exits_one():
    with patch(
        "dku_cli.commands.auth_cmd.get_all_profiles",
        return_value={"default": {}},
    ):
        result = runner.invoke(app, ["auth", "switch", "nonexistent"])

    assert result.exit_code == 1
    assert "does not exist" in result.output


def test_auth_list_json_round_trips_url_and_node_type():
    """auth list -o json must include every persisted profile field so callers
    can pipe through jq without falling back to dataikuapi internals."""
    profiles = {
        "default": {
            "url": "https://dss.example.com",
            "node_type": "DESIGN",
            "default_project": "PROJ1",
        },
        "govern": {
            "url": "https://govern.example.com",
            "node_type": "GOVERN",
        },
    }
    with (
        patch("dku_cli.commands.auth_cmd.get_all_profiles", return_value=profiles),
        patch("dku_cli.commands.auth_cmd.get_active_profile", return_value="default"),
        patch(
            "dku_cli.commands.auth_cmd.get_api_key_with_status",
            side_effect=lambda name: _key_result(
                "secret" if name == "default" else None
            ),
        ),
    ):
        result = runner.invoke(app, ["--format", "json", "auth", "list"])

    assert result.exit_code == 0, result.output
    parsed = json.loads(result.output)
    assert isinstance(parsed, list) and len(parsed) == 2
    by_name = {p["name"]: p for p in parsed}
    assert by_name["default"] == {
        "name": "default",
        "active": True,
        "node_type": "DESIGN",
        "url": "https://dss.example.com",
        "default_project": "PROJ1",
        "auth_mode": "api_key",
        "has_key": True,
    }
    assert by_name["govern"]["url"] == "https://govern.example.com"
    assert by_name["govern"]["node_type"] == "GOVERN"
    assert by_name["govern"]["active"] is False
    assert by_name["govern"]["has_key"] is False
    # default_project key is always present, even if empty
    assert "default_project" in by_name["govern"]


def test_auth_list_text_keeps_legacy_layout():
    """Text output preserves the historical 'name [node] url (key stored)' layout."""
    profiles = {
        "default": {"url": "https://dss.example.com", "node_type": "DESIGN"},
    }
    with (
        patch("dku_cli.commands.auth_cmd.get_all_profiles", return_value=profiles),
        patch("dku_cli.commands.auth_cmd.get_active_profile", return_value="default"),
        patch(
            "dku_cli.commands.auth_cmd.get_api_key_with_status",
            return_value=_key_result("secret"),
        ),
    ):
        result = runner.invoke(app, ["auth", "list"])

    assert result.exit_code == 0
    assert "default *" in result.output
    assert "[DESIGN]" in result.output
    assert "https://dss.example.com" in result.output
    assert "key stored" in result.output


def test_auth_list_json_empty_profiles():
    """No profiles → empty JSON array (not an info message in JSON mode)."""
    with patch("dku_cli.commands.auth_cmd.get_all_profiles", return_value={}):
        result = runner.invoke(app, ["--format", "json", "auth", "list"])
    assert result.exit_code == 0
    assert json.loads(result.output) == []


def test_auth_login_json_reports_file_credential_store(patch_client):
    patch_client.get_auth_info.return_value = {"authIdentifier": "alice"}
    patch_client.get_instance_info.return_value.raw = {
        "dssVersion": "14.5.0",
        "nodeType": "DESIGN",
    }

    with (
        patch(
            "dataikuapi.DSSClient",
            return_value=patch_client,
        ),
        patch("dku_cli.commands._auth_login.set_profile_config"),
        patch(
            "dku_cli.commands._auth_login.store_api_key",
            return_value=(
                "credentials file (/tmp/credentials.toml) (Keychain error: locked)"
            ),
        ),
    ):
        result = runner.invoke(
            app,
            [
                "--format",
                "json",
                "auth",
                "login",
                "--url",
                "https://dss.example.com/path",
                "--api-key",
                "dkuaps-test-key",
            ],
        )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["credential_store"] == "file"
    assert "plaintext credentials file" in payload["credential_warning"]
    assert "Keychain error: locked" in payload["credential_warning"]
    assert payload["url"] == "https://dss.example.com"
    assert "dkuaps-test-key" not in result.output


def test_auth_login_transport_error_exits_cleanly(patch_client):
    """Regression: a raw requests/urllib3 error (unreachable URL, DSS down) must
    print a compact 'Could not connect to' message and exit 1, not a traceback."""
    import requests

    patch_client.get_auth_info.side_effect = requests.exceptions.ConnectionError(
        "connection refused"
    )

    with patch(
        "dataikuapi.DSSClient",
        return_value=patch_client,
    ):
        result = runner.invoke(
            app,
            [
                "auth",
                "login",
                "--url",
                "http://127.0.0.1:9",
                "--api-key",
                "dkuaps-deadkey",
            ],
        )

    assert result.exit_code == 1, result.output
    assert "Could not connect to" in result.output
    assert "Traceback" not in result.output


def test_auth_login_instance_info_transport_error_still_succeeds(patch_client):
    """get_instance_info() can hit the same transport path after auth succeeds;
    that must degrade to dss_version: unknown, not crash the login."""
    import requests

    patch_client.get_auth_info.return_value = {"authIdentifier": "alice"}
    patch_client.get_instance_info.side_effect = requests.exceptions.ConnectionError(
        "connection refused"
    )

    with (
        patch(
            "dataikuapi.DSSClient",
            return_value=patch_client,
        ),
        patch("dku_cli.commands._auth_login.set_profile_config"),
        patch(
            "dku_cli.commands._auth_login.store_api_key",
            return_value="credentials file (/tmp/credentials.toml)",
        ),
    ):
        result = runner.invoke(
            app,
            [
                "--format",
                "json",
                "auth",
                "login",
                "--url",
                "https://dss.example.com",
                "--api-key",
                "dkuaps-test-key",
            ],
        )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["dss_version"] == "unknown"
    assert "Traceback" not in result.output


def test_auth_login_text_warns_on_file_credential_store(patch_client):
    patch_client.get_auth_info.return_value = {"authIdentifier": "alice"}
    patch_client.get_instance_info.return_value.raw = {
        "dssVersion": "14.5.0",
        "nodeType": "DESIGN",
    }

    with (
        patch(
            "dataikuapi.DSSClient",
            return_value=patch_client,
        ),
        patch("dku_cli.commands._auth_login.set_profile_config"),
        patch(
            "dku_cli.commands._auth_login.store_api_key",
            return_value="credentials file (/tmp/credentials.toml)",
        ),
    ):
        result = runner.invoke(
            app,
            [
                "auth",
                "login",
                "--url",
                "https://dss.example.com",
                "--api-key",
                "dkuaps-test-key",
            ],
        )

    assert result.exit_code == 0, result.output
    assert "Stored in plaintext credentials file" in result.output
