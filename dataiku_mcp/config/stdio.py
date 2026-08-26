"""Local stdio configuration from environment variables and profile files."""

import json
import os
import tempfile
from pathlib import Path

from .models import DSSConfig, DSSInstance


_current_instance: DSSInstance | None = None
_config_file: Path | None = None


def _resolve_config_file() -> Path:
    """Select the profile file path for the current launch context."""
    explicit = os.environ.get("DKU_CONFIG_FILE")
    if explicit:
        return Path(explicit).expanduser()

    cwd_config = Path.cwd() / ".dataiku" / "config.json"
    if cwd_config.exists():
        return cwd_config

    return Path.home() / ".dataiku" / "config.json"


def get_config_path() -> Path:
    """Return the profile file selected for this server process."""
    global _config_file
    if _config_file is None:
        _config_file = _resolve_config_file()
    return _config_file


def _parse_no_check_certificate(value: str) -> bool:
    return bool(value.strip()) and value.strip().lower() != "false"


def _load_instance_from_env_vars() -> DSSInstance | None:
    if not os.environ.get("DKU_DSS_URL"):
        return None

    return DSSInstance(
        name=os.environ.get("DKU_INSTANCE_NAME", "dss-env"),
        url=os.environ.get("DKU_DSS_URL", ""),
        api_key=os.environ.get("DKU_API_KEY", ""),
        no_check_certificate=_parse_no_check_certificate(
            os.environ.get("DKU_NO_CHECK_CERTIFICATE", "")
        ),
        source="environment",
    )


def _load_config() -> DSSConfig:
    try:
        with open(get_config_path()) as file:
            document = json.load(file)
    except FileNotFoundError:
        return DSSConfig()

    default_instance_name = document.get("default_instance") or None
    raw_instances = document.get("dss_instances", {})
    if default_instance_name and default_instance_name not in raw_instances:
        raise ValueError(
            f"Default instance '{default_instance_name}' not found in "
            f".dataiku/config.json. Available: {raw_instances.keys()}."
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


def _save_json(document: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", dir=path.parent, prefix="config.", suffix=".tmp", delete=False
    ) as temp_file:
        json.dump(document, temp_file, indent=2)
        temp_file.write("\n")
        temp_path = Path(temp_file.name)
    temp_path.chmod(0o600)
    os.replace(temp_path, path)


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
    _save_json(
        {"default_instance": config.default_instance or "", "dss_instances": instances},
        get_config_path(),
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
        "path": str(get_config_path()),
        "default_instance": config.default_instance,
    }


def delete_instance_from_config(name: str) -> dict:
    """Remove a profile-file instance and update the active/default selection."""
    global _current_instance
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
        "path": str(get_config_path()),
        "default_instance": config.default_instance,
        "remaining": list(instances),
    }
