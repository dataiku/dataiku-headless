"""Credential storage: keyring with file fallback."""

from __future__ import annotations

import sys
from typing import NamedTuple

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


class KeyStatus:
    """Status codes returned by get_api_key_with_status."""

    OK = "ok"  # Key found.
    MISSING = "missing"  # No key stored for this profile (not an error).
    DENIED = "denied"  # OS denied keychain access — the entry may still exist.
    BACKEND_ERROR = "backend_error"  # Other keyring backend failure.


class KeyResult(NamedTuple):
    """Result of a keychain lookup. `key` is None unless status == OK."""

    key: str | None
    status: str
    detail: str | None = None  # Human-readable error detail when status != OK.


def infer_api_key_kind(api_key: str | None) -> str:
    """Classify a DSS API key by its visible format.

    DSS supports multiple API key types and all are interchangeable for
    most client operations. Used in CLI output to help users (and the
    keychain owner) recognize what kind of credential they hold.

    Returns one of:
      - "personal"   — starts with "dkuaps-" (Personal API Key, user-scoped)
      - "global"     — 32-char alphanumeric, no prefix (Global API Key, admin)
      - "deployer"   — starts with "dkuapdp-" (API Deployer key)
      - "automation" — starts with "dkuapau-" (Automation node key)
      - "api-node"   — starts with "dkuapan-" (API node key)
      - "unknown"    — doesn't match any known pattern
    """
    if not api_key:
        return "unknown"
    key = api_key.strip()
    if key.startswith("dkuaps-"):
        return "personal"
    if key.startswith("dkuapdp-"):
        return "deployer"
    if key.startswith("dkuapau-"):
        return "automation"
    if key.startswith("dkuapan-"):
        return "api-node"
    # Global API Keys are bare alphanumeric, conventionally 32 chars (the user
    # we asked about saw "K4972T02QMfDslQUtmm7ryS4RnFbuQRZ" — 32 alphanumerics).
    if 24 <= len(key) <= 64 and key.isalnum():
        return "global"
    return "unknown"


def _keyring_available() -> bool:
    try:
        import keyring
    except ImportError:
        return False

    try:
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


def _keyring_get(profile: str) -> str | None:
    """Read a key from the OS keyring, swallowing backend errors.

    Used by the stale-pointer recovery path, where a missing/denied keychain
    should fall through to "key not found here" rather than surface an error.
    """
    if not _keyring_available():
        return None
    import keyring

    try:
        return keyring.get_password(SERVICE_NAME, profile)
    except keyring.errors.KeyringError:
        return None


def get_api_key(profile: str) -> str | None:
    """Retrieve API key for a profile. Returns None on any failure (including
    keychain access denial — use `get_api_key_with_status` to distinguish).
    """
    return get_api_key_with_status(profile).key


def get_api_key_with_status(profile: str) -> KeyResult:
    """Retrieve API key + status. Distinguishes 'missing' from 'access denied'.

    On macOS, the keychain may deny access (e.g. ACL whitelist mismatch, rate
    limit, prompt timeout) instead of returning a missing entry. Conflating
    'denied' with 'missing' misleads users into re-running `dku auth login`
    when the credential is actually present — they just lost permission to read
    it temporarily.

    Returns:
        KeyResult(key, status, detail) where:
          - status == OK            → key is present
          - status == MISSING       → no key configured for this profile
          - status == DENIED        → OS refused keychain access (entry may exist)
          - status == BACKEND_ERROR → other keyring failure
    """
    credential_store = get_profile_credential_store(profile)
    if credential_store == "file":
        file_key = _get_file_fallback(profile)
        if file_key:
            return KeyResult(file_key, KeyStatus.OK)
        # Stale-pointer recovery: the pointer says "file" but the file has no
        # entry. The key may actually live in the keychain — the pointer can be
        # flipped to "file" by a transient KeyringError in store_api_key's
        # fallback branch, or by a test that wrote config without isolation.
        # Treat the pointer as a hint, not a contract: try the keychain and
        # self-heal so the misleading "No API key configured" can't recur.
        healed_key = _keyring_get(profile)
        if healed_key:
            set_profile_credential_store(profile, "keychain")
            return KeyResult(healed_key, KeyStatus.OK)
        return KeyResult(None, KeyStatus.MISSING)

    # Try keyring first
    if _keyring_available():
        import keyring

        try:
            key = keyring.get_password(SERVICE_NAME, profile)
            if key:
                return KeyResult(key, KeyStatus.OK)
            # Keyring returned None — fall through to file fallback below.
        except keyring.errors.KeyringError as e:
            # Distinguish access-denied (recoverable) from other errors.
            msg = str(e).lower()
            is_denied = any(
                hint in msg
                for hint in (
                    "denied",
                    "not allowed",
                    "no access",
                    "errsecauthfailed",
                    "user canceled",
                    "user cancelled",
                    "interaction is not allowed",
                    "-25293",
                    "-128",
                )
            )
            status = KeyStatus.DENIED if is_denied else KeyStatus.BACKEND_ERROR
            # Try file fallback before giving up — but if file has no entry,
            # report the keychain error rather than 'missing'.
            file_key = _get_file_fallback(profile)
            if file_key:
                return KeyResult(file_key, KeyStatus.OK)
            return KeyResult(None, status, str(e))

    # Keyring unavailable or returned None — fall back to file.
    file_key = _get_file_fallback(profile)
    return KeyResult(
        file_key,
        KeyStatus.OK if file_key else KeyStatus.MISSING,
    )


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
