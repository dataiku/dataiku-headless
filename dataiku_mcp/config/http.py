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
_config: HTTPConfig | None = None
_user_selections: dict[str, dict[str, str]] | None = None


def set_settings_path(path: Path | None) -> Path:
    """Select the HTTP settings file for this server process."""
    global _config, _settings_path, _user_selections
    _settings_path = path.expanduser() if path is not None else DEFAULT_SETTINGS_PATH
    _config = None
    _user_selections = None
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


def _get_config() -> HTTPConfig:
    if _config is None:
        raise RuntimeError("HTTP configuration has not been initialized.")
    return _config


def initialize_config() -> None:
    """Load and cache the HTTP configuration for this server process."""
    global _config, _user_selections
    _config = _load_config()
    _user_selections = {
        issuer: dict(selections)
        for issuer, selections in _config.user_selections.items()
    }


def get_auth_settings() -> HTTPAuthConfig:
    """Return validated HTTP authentication settings."""
    return _get_config().auth


def get_server_settings() -> HTTPServerConfig:
    """Return validated Streamable HTTP transport settings."""
    return _get_config().server


def get_instances_and_selections() -> tuple[
    dict[str, DSSInstance], dict[str, dict[str, str]]
]:
    """Return the cached HTTP catalog and user selections."""
    config = _get_config()
    if _user_selections is None:
        raise RuntimeError("HTTP configuration has not been initialized.")
    instances = {
        name: instance.to_instance(name)
        for name, instance in config.dss_instances.items()
    }
    selections = {
        issuer: dict(subjects) for issuer, subjects in _user_selections.items()
    }
    return instances, selections


def set_user_selection(issuer: str, subject: str, instance_name: str) -> None:
    """Persist an authenticated user's selected catalog instance."""
    global _user_selections
    for field_name, value in (("issuer", issuer), ("subject", subject)):
        if not isinstance(value, str) or not value:
            raise ValueError(f"HTTP user selection requires a non-empty {field_name}.")

    with _settings_lock:
        if instance_name not in _get_config().dss_instances:
            raise ValueError(f"Unknown HTTP instance '{instance_name}'.")
        persisted_config = _load_config()
        if instance_name not in persisted_config.dss_instances:
            raise ValueError(
                f"HTTP instance '{instance_name}' was removed from the settings file. "
                "Restart the server to load the updated instance catalog."
            )
        persisted_config.user_selections.setdefault(issuer, {})[subject] = instance_name
        _save_config(persisted_config)
        _user_selections = {
            selected_issuer: dict(subjects)
            for selected_issuer, subjects in persisted_config.user_selections.items()
        }
