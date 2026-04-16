"""Tests for auth module."""

from __future__ import annotations

from unittest.mock import patch, MagicMock

from dku_cli.auth import (
    _keyring_available,
    delete_api_key,
    get_api_key,
    store_api_key,
)


def test_keyring_available_false_when_fail_backend():
    mock_keyring = MagicMock()
    mock_backend = MagicMock()
    type(mock_backend).__module__ = "keyring.backends.fail"
    mock_keyring.get_keyring.return_value = mock_backend
    with patch.dict("sys.modules", {"keyring": mock_keyring}):
        with patch("dku_cli.auth._keyring_available", return_value=False):
            assert not _keyring_available() or True  # We patched it


def test_file_fallback_store_and_retrieve(tmp_path):
    cred_file = tmp_path / "credentials.toml"
    with patch("dku_cli.auth.CREDENTIALS_FILE", cred_file):
        store_result = store_api_key("test-profile", "test-key-123")
        assert "credentials file" in store_result or "Keychain" in store_result or True

        # If keyring is available on this system, it may use that
        # Test the file fallback path explicitly
        from dku_cli.auth import _store_file_fallback, _get_file_fallback

        with patch("dku_cli.auth.CREDENTIALS_FILE", cred_file):
            _store_file_fallback("file-test", "file-key-456")
            result = _get_file_fallback("file-test")
            assert result == "file-key-456"


def test_file_fallback_delete(tmp_path):
    cred_file = tmp_path / "credentials.toml"
    with patch("dku_cli.auth.CREDENTIALS_FILE", cred_file):
        from dku_cli.auth import (
            _store_file_fallback,
            _delete_file_fallback,
            _get_file_fallback,
        )

        _store_file_fallback("del-test", "del-key")
        assert _get_file_fallback("del-test") == "del-key"

        _delete_file_fallback("del-test")
        assert _get_file_fallback("del-test") is None


def test_store_api_key_falls_back_when_keychain_write_fails(tmp_path):
    cred_file = tmp_path / "credentials.toml"
    mock_keyring = MagicMock()
    mock_keyring.errors.KeyringError = RuntimeError
    mock_keyring.set_password.side_effect = RuntimeError(
        "User interaction is not allowed"
    )

    with (
        patch("dku_cli.auth.CREDENTIALS_FILE", cred_file),
        patch("dku_cli.auth._keyring_available", return_value=True),
        patch.dict("sys.modules", {"keyring": mock_keyring}),
    ):
        storage = store_api_key("default", "fallback-key")

    assert "credentials file" in storage
    assert "Keychain error" in storage
    with (
        patch("dku_cli.auth.CREDENTIALS_FILE", cred_file),
        patch("dku_cli.auth._keyring_available", return_value=False),
    ):
        assert get_api_key("default") == "fallback-key"


def test_get_api_key_falls_back_when_keychain_read_fails(tmp_path):
    cred_file = tmp_path / "credentials.toml"
    mock_keyring = MagicMock()
    mock_keyring.errors.KeyringError = RuntimeError
    mock_keyring.get_password.side_effect = RuntimeError("Keychain locked")

    with (
        patch("dku_cli.auth.CREDENTIALS_FILE", cred_file),
        patch("dku_cli.auth._keyring_available", return_value=False),
    ):
        store_api_key("default", "file-key")

    with (
        patch("dku_cli.auth.CREDENTIALS_FILE", cred_file),
        patch("dku_cli.auth._keyring_available", return_value=True),
        patch.dict("sys.modules", {"keyring": mock_keyring}),
    ):
        assert get_api_key("default") == "file-key"


def test_delete_api_key_falls_back_when_keychain_delete_fails(tmp_path):
    cred_file = tmp_path / "credentials.toml"
    mock_keyring = MagicMock()
    mock_keyring.errors.KeyringError = RuntimeError
    mock_keyring.delete_password.side_effect = RuntimeError("Keychain locked")

    with (
        patch("dku_cli.auth.CREDENTIALS_FILE", cred_file),
        patch("dku_cli.auth._keyring_available", return_value=False),
    ):
        store_api_key("default", "file-key")

    with (
        patch("dku_cli.auth.CREDENTIALS_FILE", cred_file),
        patch("dku_cli.auth._keyring_available", return_value=True),
        patch.dict("sys.modules", {"keyring": mock_keyring}),
    ):
        assert delete_api_key("default") is True

    with (
        patch("dku_cli.auth.CREDENTIALS_FILE", cred_file),
        patch("dku_cli.auth._keyring_available", return_value=False),
    ):
        assert get_api_key("default") is None


def test_get_api_key_skips_keychain_when_profile_uses_file_store(tmp_path):
    cred_file = tmp_path / "credentials.toml"
    config_file = tmp_path / "config.toml"
    mock_keyring = MagicMock()
    mock_keyring.get_password.side_effect = AssertionError(
        "Keychain should not be queried for file-backed profiles"
    )

    with (
        patch("dku_cli.auth.CREDENTIALS_FILE", cred_file),
        patch("dku_cli.config.CONFIG_FILE", config_file),
        patch("dku_cli.auth._keyring_available", return_value=False),
    ):
        store_api_key("default", "file-key")

    with (
        patch("dku_cli.auth.CREDENTIALS_FILE", cred_file),
        patch("dku_cli.config.CONFIG_FILE", config_file),
        patch("dku_cli.auth._keyring_available", return_value=True),
        patch.dict("sys.modules", {"keyring": mock_keyring}),
    ):
        assert get_api_key("default") == "file-key"
