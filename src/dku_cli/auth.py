"""Credential storage: keyring with file fallback."""

from __future__ import annotations

import sys

from platformdirs import user_config_dir
from pathlib import Path
from dku_cli.config import get_profile_credential_store, set_profile_credential_store

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

SERVICE_NAME = "dku-cli"
CONFIG_DIR = Path(user_config_dir("dku", ensure_exists=True))
CREDENTIALS_FILE = CONFIG_DIR / "credentials.toml"


def _keyring_available() -> bool:
    try:
        import keyring

        # Test that a real backend is available (not the fail backend)
        backend = keyring.get_keyring()
        return "fail" not in type(backend).__module__.lower()
    except Exception:
        return False


def store_api_key(profile: str, api_key: str) -> str:
    """Store API key, returns storage location description."""
    if _keyring_available():
        import keyring

        try:
            keyring.set_password(SERVICE_NAME, profile, api_key)
            backend = keyring.get_keyring()
            set_profile_credential_store(profile, "keychain")
            return type(backend).__name__
        except keyring.errors.KeyringError as e:
            storage = _store_file_fallback(profile, api_key)
            set_profile_credential_store(profile, "file")
            return f"{storage} (Keychain error: {e})"

    storage = _store_file_fallback(profile, api_key)
    set_profile_credential_store(profile, "file")
    return storage


def get_api_key(profile: str) -> str | None:
    """Retrieve API key for a profile."""
    credential_store = get_profile_credential_store(profile)
    if credential_store == "file":
        return _get_file_fallback(profile)

    # Try keyring first
    if _keyring_available():
        import keyring

        try:
            key = keyring.get_password(SERVICE_NAME, profile)
            if key:
                return key
        except keyring.errors.KeyringError:
            pass
    # Fallback to file
    return _get_file_fallback(profile)


def delete_api_key(profile: str) -> bool:
    """Delete API key for a profile. Returns True if deleted."""
    deleted = False
    credential_store = get_profile_credential_store(profile)
    if credential_store != "file" and _keyring_available():
        import keyring

        try:
            keyring.delete_password(SERVICE_NAME, profile)
            deleted = True
        except keyring.errors.KeyringError:
            pass
    # Also remove from file fallback
    if _delete_file_fallback(profile):
        deleted = True
    return deleted


def _store_file_fallback(profile: str, api_key: str) -> str:
    """Store in credentials.toml with restricted permissions."""
    creds = _read_credentials()
    creds[profile] = {"api_key": api_key}
    _write_credentials(creds)
    return f"credentials file ({CREDENTIALS_FILE})"


def _get_file_fallback(profile: str) -> str | None:
    creds = _read_credentials()
    entry = creds.get(profile, {})
    return entry.get("api_key")


def _delete_file_fallback(profile: str) -> bool:
    creds = _read_credentials()
    if profile in creds:
        del creds[profile]
        _write_credentials(creds)
        return True
    return False


def _read_credentials() -> dict:
    if not CREDENTIALS_FILE.exists():
        return {}
    return tomllib.loads(CREDENTIALS_FILE.read_text())


def _write_credentials(data: dict) -> None:
    lines: list[str] = []
    for profile, values in data.items():
        if isinstance(values, dict):
            lines.append(f"[{profile}]")
            for k, v in values.items():
                lines.append(f'{k} = "{v}"')
            lines.append("")
    CREDENTIALS_FILE.parent.mkdir(parents=True, exist_ok=True)
    CREDENTIALS_FILE.write_text("\n".join(lines) + "\n")
    CREDENTIALS_FILE.chmod(0o600)
