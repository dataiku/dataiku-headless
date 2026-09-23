# Copyright 2026 Dataiku SAS
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Local stdio configuration from environment variables and profile files."""

import logging
import os
import threading
from pathlib import Path

from pydantic import ValidationError

from .files import read_json_object, write_json_atomic
from .models import DSSInstance, StdioConfig, StdioDSSInstanceConfig


DEFAULT_SETTINGS_PATH = Path.home() / ".dataiku" / "stdio-config.json"
_LEGACY_SETTINGS_FILENAME = "config.json"

logger = logging.getLogger("dataiku-mcp")

_settings_path: Path | None = None
_settings_lock = threading.Lock()
_config: StdioConfig | None = None
_environment_instance: DSSInstance | None = None
_current_instance: DSSInstance | None = None


# TODO: Remove this helper after three minor releases.
def _migrate_legacy_settings_if_valid(legacy_path: Path, settings_path: Path) -> bool:
    try:
        document = read_json_object(
            legacy_path, description="Legacy stdio instance configuration"
        )
        config = StdioConfig.model_validate(document)
    except (ValidationError, ValueError):
        return False
    write_json_atomic(
        settings_path,
        config.model_dump(mode="json", exclude_none=True, exclude_defaults=True),
    )
    legacy_path.unlink()
    logger.info(
        "Migrated legacy stdio configuration from '%s' to '%s'.",
        legacy_path,
        settings_path,
    )
    return True


# TODO: Replace _resolve_default_settings_path with this helper after three minor
# releases, when legacy config.json compatibility is removed.
def _resolve_canonical_default_settings_path() -> Path:
    cwd_settings_path = Path.cwd() / ".dataiku" / DEFAULT_SETTINGS_PATH.name
    return cwd_settings_path if cwd_settings_path.exists() else DEFAULT_SETTINGS_PATH


# TODO: Remove legacy config compatibility after three minor releases.
def _resolve_default_settings_path() -> Path:
    cwd_settings_path = Path.cwd() / ".dataiku" / DEFAULT_SETTINGS_PATH.name
    if cwd_settings_path.exists():
        return cwd_settings_path
    if DEFAULT_SETTINGS_PATH.exists():
        return DEFAULT_SETTINGS_PATH

    for settings_directory in (Path.cwd() / ".dataiku", DEFAULT_SETTINGS_PATH.parent):
        settings_path = settings_directory / DEFAULT_SETTINGS_PATH.name
        legacy_path = settings_directory / _LEGACY_SETTINGS_FILENAME
        if legacy_path.exists() and _migrate_legacy_settings_if_valid(
            legacy_path, settings_path
        ):
            return settings_path
    return DEFAULT_SETTINGS_PATH


def set_settings_path(path: Path | None) -> Path:
    """Select the stdio profile file for this server process."""
    global _config, _current_instance, _environment_instance, _settings_path
    if "DKU_CONFIG_FILE" in os.environ:
        raise ValueError(
            "DKU_CONFIG_FILE is deprecated. Use --settings-path to select the "
            "stdio settings file."
        )
    if path is not None:
        _settings_path = path.expanduser()
    else:
        _settings_path = _resolve_default_settings_path()
    _config = None
    _environment_instance = None
    _current_instance = None
    return _settings_path


def get_settings_path() -> Path:
    """Return the profile file selected for this server process."""
    return _settings_path if _settings_path is not None else set_settings_path(None)


def _load_instance_from_env_vars() -> DSSInstance | None:
    # Undocumented override for loading Dataiku instance when running in a Code Studio
    if os.environ.get("DKU_IS_CODE_STUDIO"):
        try:
            backend_url = f"{os.environ['DKU_BACKEND_PROTOCOL']}://{os.environ['DKU_BACKEND_HOST']}:{os.environ['DKU_BACKEND_PORT']}"
            instance = StdioDSSInstanceConfig(
                url=backend_url,
                api_key=os.environ.get("DKU_API_TICKET", ""),
            )
        except ValidationError as err:
            raise ValueError(f"Invalid stdio environment settings in Code Studio: {err}") from None
        return instance.to_instance(
            os.environ.get("DKU_INSTANCE_NAME", "dss-code-studio"),
            source="environment",
        )

    # Documented logic for loading a Dataiku instance from env vars
    if not os.environ.get("DKU_DSS_URL"):
        return None

    no_check_certificate = os.environ.get("DKU_NO_CHECK_CERTIFICATE", "").strip()
    try:
        instance = StdioDSSInstanceConfig(
            url=os.environ["DKU_DSS_URL"],
            api_key=os.environ.get("DKU_API_KEY", ""),
            no_check_certificate=(
                bool(no_check_certificate) and no_check_certificate.lower() != "false"
            ),
        )
    except ValidationError as err:
        raise ValueError(f"Invalid stdio environment settings: {err}") from None
    return instance.to_instance(
        os.environ.get("DKU_INSTANCE_NAME", "dss-env"),
        source="environment",
    )


def _load_config() -> StdioConfig:
    path = get_settings_path()
    try:
        document = read_json_object(path, description="Stdio instance configuration")
    except FileNotFoundError:
        return StdioConfig()
    try:
        return StdioConfig.model_validate(document)
    except ValidationError as err:
        raise ValueError(f"Invalid stdio settings at '{path}': {err}") from None


def _save_config(config: StdioConfig) -> None:
    write_json_atomic(
        get_settings_path(),
        config.model_dump(mode="json", exclude_none=True, exclude_defaults=True),
    )


def _get_config() -> StdioConfig:
    if _config is None:
        raise RuntimeError("Stdio configuration has not been initialized.")
    return _config


def initialize_config() -> None:
    """Load and cache stdio profiles and the active instance."""
    global _config, _current_instance, _environment_instance
    _environment_instance = _load_instance_from_env_vars()
    _config = _load_config()
    if _environment_instance:
        _current_instance = _environment_instance
    elif _config.default_instance:
        _current_instance = _config.dss_instances[_config.default_instance].to_instance(
            _config.default_instance
        )
    else:
        _current_instance = None


def get_instances() -> dict[str, DSSInstance]:
    """Return cached instances, with the environment instance taking precedence."""
    instances = {
        name: instance.to_instance(name)
        for name, instance in _get_config().dss_instances.items()
    }
    if _environment_instance:
        return instances | {_environment_instance.name: _environment_instance}
    return instances


def get_current_instance() -> DSSInstance | None:
    return _current_instance


def set_current_instance(instance: DSSInstance) -> None:
    global _current_instance
    _current_instance = instance


def add_instance_to_config(
    name: str,
    url: str,
    api_key: str,
    *,
    description: str = "",
    no_check_certificate: bool = False,
    set_default: bool = False,
) -> dict:
    """Add an instance to the resolved local profile file."""
    global _config
    with _settings_lock:
        instance = StdioDSSInstanceConfig(
            url=url,
            api_key=api_key,
            description=description,
            no_check_certificate=no_check_certificate,
        )
        config = _load_config()
        config.dss_instances[name] = instance
        if set_default:
            config.default_instance = name
        _save_config(config)
        _config = config
        return {
            "name": name,
            "url": url,
            "description": description,
            "path": str(get_settings_path()),
            "default_instance": config.default_instance,
        }


def delete_instance_from_config(name: str) -> dict:
    """Remove a profile-file instance and update the active/default selection."""
    global _config, _current_instance
    with _settings_lock:
        config = _load_config()
        instances = config.dss_instances
        if name not in instances:
            raise ValueError(
                f"Instance '{name}' not found in config file. Available: {list(instances)}"
            )

        was_current = (
            _current_instance is not None
            and _current_instance.source == "config"
            and _current_instance.name == name
        )
        instances.pop(name)
        if config.default_instance == name:
            config.default_instance = next(iter(instances), None)
        _save_config(config)
        _config = config
        if was_current:
            _current_instance = (
                instances[config.default_instance].to_instance(config.default_instance)
                if config.default_instance
                else None
            )
        return {
            "deleted": name,
            "path": str(get_settings_path()),
            "default_instance": config.default_instance,
            "remaining": list(instances),
        }
