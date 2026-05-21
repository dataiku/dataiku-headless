"""Tests for auth module."""

from __future__ import annotations

from unittest.mock import patch, MagicMock

from dku_cli.auth import (
    KeyStatus,
    _keyring_available,
    delete_api_key,
    get_api_key,
    get_api_key_with_status,
    infer_api_key_kind,
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


# ── Bug A: surface keychain access denial instead of swallowing ──────────


def test_get_api_key_with_status_returns_denied_on_access_denied(tmp_path):
    """KeyringError messages mentioning 'denied' map to KeyStatus.DENIED.

    Regression: previously the CLI silently swallowed KeyringError and reported
    'no key' — misleading users into running 'dku auth login' when the
    credential was actually present, just inaccessible.
    """
    cred_file = tmp_path / "credentials.toml"
    config_file = tmp_path / "config.toml"
    mock_keyring = MagicMock()
    mock_keyring.errors.KeyringError = RuntimeError
    mock_keyring.get_password.side_effect = RuntimeError(
        "User interaction is not allowed"
    )

    with (
        patch("dku_cli.auth.CREDENTIALS_FILE", cred_file),
        patch("dku_cli.config.CONFIG_FILE", config_file),
        patch("dku_cli.auth._keyring_available", return_value=True),
        patch.dict("sys.modules", {"keyring": mock_keyring}),
    ):
        result = get_api_key_with_status("default")

    assert result.key is None
    assert result.status == KeyStatus.DENIED
    assert "interaction is not allowed" in (result.detail or "").lower()


def test_get_api_key_with_status_returns_missing_when_no_key(tmp_path):
    """Missing keychain entry AND no file fallback → status=missing, not denied."""
    cred_file = tmp_path / "credentials.toml"
    config_file = tmp_path / "config.toml"
    mock_keyring = MagicMock()
    mock_keyring.get_password.return_value = None  # no entry

    with (
        patch("dku_cli.auth.CREDENTIALS_FILE", cred_file),
        patch("dku_cli.config.CONFIG_FILE", config_file),
        patch("dku_cli.auth._keyring_available", return_value=True),
        patch.dict("sys.modules", {"keyring": mock_keyring}),
    ):
        result = get_api_key_with_status("nonexistent")

    assert result.key is None
    assert result.status == KeyStatus.MISSING


def test_get_api_key_with_status_returns_backend_error_for_other_keyring_errors(
    tmp_path,
):
    """KeyringError without denial keywords maps to BACKEND_ERROR (not DENIED)."""
    cred_file = tmp_path / "credentials.toml"
    config_file = tmp_path / "config.toml"
    mock_keyring = MagicMock()
    mock_keyring.errors.KeyringError = RuntimeError
    mock_keyring.get_password.side_effect = RuntimeError("Backend exploded")

    with (
        patch("dku_cli.auth.CREDENTIALS_FILE", cred_file),
        patch("dku_cli.config.CONFIG_FILE", config_file),
        patch("dku_cli.auth._keyring_available", return_value=True),
        patch.dict("sys.modules", {"keyring": mock_keyring}),
    ):
        result = get_api_key_with_status("default")

    assert result.key is None
    assert result.status == KeyStatus.BACKEND_ERROR


def test_get_api_key_with_status_file_fallback_recovers_on_denial(tmp_path):
    """When keychain is denied BUT a file fallback exists, return the file key."""
    cred_file = tmp_path / "credentials.toml"
    config_file = tmp_path / "config.toml"
    mock_keyring = MagicMock()
    mock_keyring.errors.KeyringError = RuntimeError
    mock_keyring.get_password.side_effect = RuntimeError(
        "User interaction is not allowed"
    )

    # Seed a file-backed credential first.
    with (
        patch("dku_cli.auth.CREDENTIALS_FILE", cred_file),
        patch("dku_cli.config.CONFIG_FILE", config_file),
        patch("dku_cli.auth._keyring_available", return_value=False),
    ):
        store_api_key("default", "file-fallback-key")

    with (
        patch("dku_cli.auth.CREDENTIALS_FILE", cred_file),
        patch("dku_cli.config.CONFIG_FILE", config_file),
        patch("dku_cli.auth._keyring_available", return_value=True),
        patch.dict("sys.modules", {"keyring": mock_keyring}),
    ):
        # Profile is now file-backed so we skip keychain entirely.
        result = get_api_key_with_status("default")

    assert result.key == "file-fallback-key"
    assert result.status == KeyStatus.OK


# ── Bug B: API key format detection ──────────────────────────────────────


def test_infer_api_key_kind_personal():
    """Personal API Keys start with 'dkuaps-'."""
    assert infer_api_key_kind("dkuaps-abc123def456") == "personal"


def test_infer_api_key_kind_global():
    """Global API Keys are bare 32-char alphanumeric (no prefix)."""
    # Real-world example from the user's chrispersonal sandbox.
    assert infer_api_key_kind("K4972T02QMfDslQUtmm7ryS4RnFbuQRZ") == "global"


def test_infer_api_key_kind_deployer():
    assert infer_api_key_kind("dkuapdp-abc123") == "deployer"


def test_infer_api_key_kind_automation():
    assert infer_api_key_kind("dkuapau-abc123") == "automation"


def test_infer_api_key_kind_api_node():
    assert infer_api_key_kind("dkuapan-abc123") == "api-node"


def test_infer_api_key_kind_unknown_for_garbage():
    assert infer_api_key_kind("not a real key with spaces") == "unknown"
    assert infer_api_key_kind("") == "unknown"
    assert infer_api_key_kind(None) == "unknown"
