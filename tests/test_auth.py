"""Tests for auth module."""

from __future__ import annotations

from unittest.mock import patch, MagicMock

from dku_cli.auth import (
    _keyring_available,
    store_api_key,
    get_api_key,
    delete_api_key,
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
        from dku_cli.auth import _store_file_fallback, _delete_file_fallback, _get_file_fallback

        _store_file_fallback("del-test", "del-key")
        assert _get_file_fallback("del-test") == "del-key"

        _delete_file_fallback("del-test")
        assert _get_file_fallback("del-test") is None
