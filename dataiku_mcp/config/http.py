"""Operator-managed Streamable HTTP configuration."""

import threading
from pathlib import Path

from pydantic import ValidationError

from .files import read_json_object, write_json_atomic
from .models import (
    DSSInstance,
    HTTPAuthConfig,
    HTTPConfig,
    HTTPServerConfig,
)


DEFAULT_SETTINGS_PATH = Path.home() / ".dataiku" / "http-config.json"

_settings_path: Path | None = None
_settings_lock = threading.Lock()


def set_settings_path(path: Path | None) -> Path:
    """Select the HTTP settings file for this server process."""
    global _settings_path
    _settings_path = path.expanduser() if path is not None else DEFAULT_SETTINGS_PATH
    return _settings_path


def get_settings_path() -> Path:
    """Return the single operator-managed HTTP settings file."""
    return _settings_path if _settings_path is not None else set_settings_path(None)


def _load_config() -> HTTPConfig:
    path = get_settings_path()
    try:
        document = read_json_object(path, description="HTTP instance configuration")
    except FileNotFoundError as err:
        raise ValueError(
            f"HTTP instance configuration was not found at '{path}'."
        ) from err
    try:
        return HTTPConfig.model_validate(document)
    except ValidationError as err:
        raise ValueError(f"Invalid HTTP settings at '{path}': {err}") from None


def _save_config(config: HTTPConfig) -> None:
    write_json_atomic(
        get_settings_path(),
        config.model_dump(mode="json", exclude_none=True, exclude_defaults=True),
    )


def get_auth_settings() -> HTTPAuthConfig:
    """Return validated HTTP authentication settings."""
    return _load_config().auth


def get_server_settings() -> HTTPServerConfig:
    """Return validated Streamable HTTP transport settings."""
    return _load_config().server


def get_instances_and_selections() -> tuple[
    dict[str, DSSInstance], dict[str, dict[str, str]]
]:
    """Return the global HTTP catalog and persisted user selections."""
    config = _load_config()
    instances = {
        name: instance.to_instance(name)
        for name, instance in config.dss_instances.items()
    }
    return instances, config.user_selections


def set_user_selection(issuer: str, subject: str, instance_name: str) -> None:
    """Persist an authenticated user's selected catalog instance."""
    for field_name, value in (("issuer", issuer), ("subject", subject)):
        if not isinstance(value, str) or not value:
            raise ValueError(f"HTTP user selection requires a non-empty {field_name}.")

    with _settings_lock:
        config = _load_config()
        if instance_name not in config.dss_instances:
            raise ValueError(f"Unknown HTTP instance '{instance_name}'.")
        config.user_selections.setdefault(issuer, {})[subject] = instance_name
        _save_config(config)
