"""Tests for config module."""

from __future__ import annotations

from unittest.mock import patch

from dku_cli.config import (
    _read_toml,
    _toml_key,
    _toml_value,
    _write_toml,
    clear_profile_configs,
    delete_profile_config,
    get_config,
    get_profile_credential_store,
    set_profile_config,
    set_profile_credential_store,
)


def test_toml_value_string():
    assert _toml_value("hello") == '"hello"'


def test_toml_value_escapes_strings():
    assert _toml_value('hello "dss" \\ prod') == '"hello \\"dss\\" \\\\ prod"'


def test_toml_key_quotes_dotted_profile_names():
    assert _toml_key("prod.eu") == '"prod.eu"'


def test_toml_value_bool():
    assert _toml_value(True) == "true"
    assert _toml_value(False) == "false"


def test_toml_value_int():
    assert _toml_value(42) == "42"


def test_read_toml_missing(tmp_path):
    result = _read_toml(tmp_path / "nonexistent.toml")
    assert result == {}


def test_write_and_read_toml(tmp_path):
    path = tmp_path / "test.toml"
    data = {
        "active_profile": "sandbox",
        "sandbox": {"url": "https://dss.example.com"},
    }
    _write_toml(path, data)
    assert path.exists()

    result = _read_toml(path)
    assert result["active_profile"] == "sandbox"
    assert result["sandbox"]["url"] == "https://dss.example.com"


def test_write_toml_escapes_values_and_section_names(tmp_path):
    path = tmp_path / "test.toml"
    data = {
        "active_profile": 'prod"eu',
        "prod.eu": {
            "url": 'https://dss.example.com/a"b\\c',
            "default_project": "AGENT.TEST",
        },
    }

    _write_toml(path, data)
    result = _read_toml(path)

    assert result["active_profile"] == 'prod"eu'
    assert result["prod.eu"]["url"] == 'https://dss.example.com/a"b\\c'
    assert result["prod.eu"]["default_project"] == "AGENT.TEST"


def test_set_profile_config_preserves_existing_values(tmp_path):
    path = tmp_path / "config.toml"
    _write_toml(
        path,
        {
            "active_profile": "default",
            "default": {
                "url": "https://old.example.com",
                "default_project": "PROJ1",
            },
        },
    )

    with patch("dku_cli.config.CONFIG_FILE", path):
        set_profile_config("default", "https://new.example.com")
        result = get_config()

    assert result["default"]["url"] == "https://new.example.com"
    assert result["default"]["default_project"] == "PROJ1"


def test_delete_profile_config_repoints_active_profile(tmp_path):
    path = tmp_path / "config.toml"
    _write_toml(
        path,
        {
            "active_profile": "production",
            "default": {"url": "https://default.example.com"},
            "production": {"url": "https://prod.example.com"},
        },
    )

    with patch("dku_cli.config.CONFIG_FILE", path):
        removed = delete_profile_config("production")
        result = get_config()

    assert removed is True
    assert "production" not in result
    assert result["active_profile"] == "default"


def test_clear_profile_configs_preserves_root_settings(tmp_path):
    path = tmp_path / "config.toml"
    _write_toml(
        path,
        {
            "active_profile": "default",
            "dangerous_mode": True,
            "default": {"url": "https://default.example.com"},
        },
    )

    with patch("dku_cli.config.CONFIG_FILE", path):
        removed = clear_profile_configs()
        result = get_config()

    assert removed == 1
    assert result == {"dangerous_mode": True}


def test_set_profile_credential_store_preserves_existing_values(tmp_path):
    path = tmp_path / "config.toml"
    _write_toml(
        path,
        {
            "active_profile": "default",
            "default": {
                "url": "https://default.example.com",
                "default_project": "PROJ1",
            },
        },
    )

    with patch("dku_cli.config.CONFIG_FILE", path):
        set_profile_credential_store("default", "file")
        result = get_config()

    assert result["default"]["url"] == "https://default.example.com"
    assert result["default"]["default_project"] == "PROJ1"
    assert result["default"]["credential_store"] == "file"


def test_write_toml_does_not_chmod_credentials_path(tmp_path):
    """config never writes credentials; _write_toml must not chmod that path.

    The old dead branch chmod'd 0600 whenever the target equalled
    CREDENTIALS_FILE, but config.py never targets it — auth.py owns credential
    writes. Writing config to a path named like the credentials file must not
    invoke Path.chmod at all.
    """
    path = tmp_path / "credentials.toml"
    with (
        patch("dku_cli.config.CREDENTIALS_FILE", path),
        patch("pathlib.Path.chmod") as chmod,
    ):
        _write_toml(path, {"default": {"url": "https://dss.example.com"}})

    chmod.assert_not_called()


def test_get_profile_credential_store_returns_value(tmp_path):
    path = tmp_path / "config.toml"
    _write_toml(
        path,
        {
            "default": {
                "url": "https://default.example.com",
                "credential_store": "keychain",
            }
        },
    )

    with patch("dku_cli.config.CONFIG_FILE", path):
        assert get_profile_credential_store("default") == "keychain"
