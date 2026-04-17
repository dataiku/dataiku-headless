"""Tests for config module."""

from __future__ import annotations

from unittest.mock import patch


from dku_cli.config import (
    _read_toml,
    _write_toml,
    _toml_value,
    clear_profile_configs,
    delete_profile_config,
    get_config,
    get_profile_credential_store,
    set_profile_config,
    set_profile_credential_store,
)


def test_toml_value_string():
    assert _toml_value("hello") == '"hello"'


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
            "output": "json",
            "default": {"url": "https://default.example.com"},
        },
    )

    with patch("dku_cli.config.CONFIG_FILE", path):
        removed = clear_profile_configs()
        result = get_config()

    assert removed == 1
    assert result == {"output": "json"}


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
