"""Local stdio configuration from environment variables and profile files."""

import os
import threading
from pathlib import Path

from .files import read_json_object, write_json_atomic
from .models import DSSConfig, DSSInstance


DEFAULT_SETTINGS_PATH = Path.home() / ".dataiku" / "stdio-config.json"

_current_instance: DSSInstance | None = None
_settings_path: Path | None = None
_settings_lock = threading.Lock()


def set_settings_path(path: Path | None) -> Path:
    """Select the stdio profile file for this server process."""
    global _settings_path
    if path is not None:
        _settings_path = path.expanduser()
    else:
        cwd_settings_path = Path.cwd() / ".dataiku" / "stdio-config.json"
        _settings_path = (
            cwd_settings_path if cwd_settings_path.exists() else DEFAULT_SETTINGS_PATH
        )
    return _settings_path


def get_settings_path() -> Path:
    """Return the profile file selected for this server process."""
    return _settings_path if _settings_path is not None else set_settings_path(None)


def _load_instance_from_env_vars() -> DSSInstance | None:
    if not os.environ.get("DKU_DSS_URL"):
        return None

    no_check_certificate = os.environ.get("DKU_NO_CHECK_CERTIFICATE", "").strip()
    return DSSInstance(
        name=os.environ.get("DKU_INSTANCE_NAME", "dss-env"),
        url=os.environ.get("DKU_DSS_URL", ""),
        api_key=os.environ.get("DKU_API_KEY", ""),
        no_check_certificate=(
            bool(no_check_certificate) and no_check_certificate.lower() != "false"
        ),
        source="environment",
    )


def _load_config() -> DSSConfig:
    try:
        document = read_json_object(
            get_settings_path(), description="Stdio instance configuration"
        )
    except FileNotFoundError:
        return DSSConfig()

    default_instance_name = document.get("default_instance") or None
    raw_instances = document.get("dss_instances", {})
    if default_instance_name and default_instance_name not in raw_instances:
        raise ValueError(
            f"Default instance '{default_instance_name}' not found in "
            f".dataiku/stdio-config.json. Available: {raw_instances.keys()}."
        )

    instances = {
        name: DSSInstance(
            name=name,
            url=details["url"],
            api_key=details.get("api_key", ""),
            description=details.get("description", ""),
            no_check_certificate=details.get("no_check_certificate", False),
            source="config",
        )
        for name, details in raw_instances.items()
    }
    return DSSConfig(default_instance_name, instances)


def _save_config(config: DSSConfig) -> None:
    instances = {}
    for name, instance in config.dss_instances.items():
        serialized = {
            "url": instance.url,
            "api_key": instance.api_key,
            "no_check_certificate": instance.no_check_certificate,
        }
        if instance.description:
            serialized["description"] = instance.description
        instances[name] = serialized
    write_json_atomic(
        get_settings_path(),
        {"default_instance": config.default_instance or "", "dss_instances": instances},
    )


def initialize_current_instance() -> None:
    """Initialize the active stdio instance from environment variables or profiles."""
    global _current_instance
    environment_instance = _load_instance_from_env_vars()
    config = _load_config()
    if environment_instance:
        _current_instance = environment_instance
    elif config.default_instance:
        _current_instance = config.dss_instances[config.default_instance]
    else:
        _current_instance = None


def get_instances() -> dict[str, DSSInstance]:
    """Return local instances, with an environment instance taking precedence."""
    environment_instance = _load_instance_from_env_vars()
    instances = _load_config().dss_instances
    if environment_instance:
        return instances | {environment_instance.name: environment_instance}
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
    with _settings_lock:
        instance = DSSInstance(
            name=name,
            url=url,
            api_key=api_key,
            description=description,
            no_check_certificate=no_check_certificate,
            source="config",
        )
        config = _load_config()
        config.dss_instances[name] = instance
        if set_default:
            config.default_instance = name
        _save_config(config)
        return {
            "name": name,
            "url": url,
            "description": description,
            "path": str(get_settings_path()),
            "default_instance": config.default_instance,
        }


def delete_instance_from_config(name: str) -> dict:
    """Remove a profile-file instance and update the active/default selection."""
    global _current_instance
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
        if was_current:
            _current_instance = (
                instances[config.default_instance] if config.default_instance else None
            )
        return {
            "deleted": name,
            "path": str(get_settings_path()),
            "default_instance": config.default_instance,
            "remaining": list(instances),
        }
