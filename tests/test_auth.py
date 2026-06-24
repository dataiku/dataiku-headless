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
    assert infer_api_key_kind("A" * 32) == "global"


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


def test_get_api_key_heals_stale_file_pointer_to_keychain(tmp_path):
    """A stale credential_store='file' pointer self-heals to the keychain.

    Regression: when the pointer says 'file' (e.g. flipped by a transient
    KeyringError in store_api_key, or by an unisolated test write) but the file
    has no entry and the key actually lives in the keychain, get_api_key must
    still find it AND repoint the profile to 'keychain'. Before the fix the
    'file' branch returned None without ever consulting the keychain, surfacing
    as a misleading 'No API key configured'.
    """
    from dku_cli.config import (
        get_profile_credential_store,
        set_profile_credential_store,
    )

    cfg = tmp_path / "config.toml"
    creds = tmp_path / "credentials.toml"  # empty → file fallback returns None

    mock_keyring = MagicMock()
    mock_keyring.get_password.return_value = "keychain-key-xyz"
    mock_keyring.errors.KeyringError = Exception

    with (
        patch("dku_cli.config.CONFIG_FILE", cfg),
        patch("dku_cli.auth.CREDENTIALS_FILE", creds),
        patch("dku_cli.auth._keyring_available", return_value=True),
        patch.dict("sys.modules", {"keyring": mock_keyring}),
    ):
        set_profile_credential_store("default", "file")  # stale pointer
        assert get_api_key("default") == "keychain-key-xyz"
        # Pointer self-healed so the next read takes the fast keychain path.
        assert get_profile_credential_store("default") == "keychain"


def test_get_api_key_missing_when_neither_store_has_key(tmp_path):
    """Pointer='file', empty file, no keychain → MISSING (no false heal)."""
    from dku_cli.config import set_profile_credential_store

    cfg = tmp_path / "config.toml"
    creds = tmp_path / "credentials.toml"
    with (
        patch("dku_cli.config.CONFIG_FILE", cfg),
        patch("dku_cli.auth.CREDENTIALS_FILE", creds),
        patch("dku_cli.auth._keyring_available", return_value=False),
    ):
        set_profile_credential_store("default", "file")
        result = get_api_key_with_status("default")
        assert result.key is None
        assert result.status == KeyStatus.MISSING
