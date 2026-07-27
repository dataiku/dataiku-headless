"""Configuration and environment variables for Dataiku MCP server."""

import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DSSInstance:
    name: str
    url: str
    api_key: str
    no_check_certificate: bool
    source: str
    description: str = ""


_current_instance: DSSInstance | None = None
_config_file: Path | None = None


### ------------------------------ ###
###        config.json path        ###
### ------------------------------ ###
def _resolve_config_file() -> Path:
    """Select the configuration file path for the current launch context.

    Resolution order:
      1. `DKU_CONFIG_FILE` env var (explicit path)
      2. `./.dataiku/config.json` when it already exists (repo-local dev)
      3. `~/.dataiku/config.json` otherwise (canonical user location)
    """
    explicit = os.environ.get("DKU_CONFIG_FILE")
    if explicit:
        return Path(explicit).expanduser()

    cwd_config = Path.cwd() / ".dataiku" / "config.json"
    if cwd_config.exists():
        return cwd_config

    return Path.home() / ".dataiku" / "config.json"


def get_config_path() -> Path:
    """Return the config file selected for this server process.

    The path is resolved lazily and cached so all reads, additions, and
    deletions use the same file.
    """
    global _config_file
    if _config_file is None:
        _config_file = _resolve_config_file()
    return _config_file


### ------------------------------ ###
###       Load configuration       ###
### ------------------------------ ###
def _parse_no_check_certificate(value: str) -> bool:
    return bool(value.strip()) and value.strip().lower() != "false"


def _load_instance_from_env_vars() -> DSSInstance | None:
    """
    Load the DSS instance defined by environment variables. An instance
    is considered configured when `DKU_DSS_URL` is set.

    Returns a single instance object, with at least `name`, `url`,
    and `no_check_certificate` populated.
    """
    if not os.environ.get("DKU_DSS_URL"):
        return None

    return DSSInstance(
        name=os.environ.get("DKU_INSTANCE_NAME", "dss-env"),
        url=os.environ.get("DKU_DSS_URL", ""),
        api_key=os.environ.get("DKU_API_KEY", ""),
        no_check_certificate=_parse_no_check_certificate(
            os.environ.get("DKU_NO_CHECK_CERTIFICATE", "")
        ),
        source="environment variables",
    )


def _load_instances_from_config() -> dict:
    """
    Load DSS instances from resolved config.json, if the file exists.

    If the file defines a non-empty `default_instance`, validate that the
    instance name exists in `dss_instances`; raise `ValueError` otherwise.

    Returns a dictionary with shape
    `{"default_instance": "...", "dss_instances": {...}}`, where the values
    in `dss_instances` are `DSSInstance` objects keyed by instance name.
    """
    instances_from_config = {
        "default_instance": None,
        "dss_instances": {},
    }

    dataiku_config_file = {}
    try:
        with open(get_config_path(), "r") as f:
            dataiku_config_file = json.load(f)
    except FileNotFoundError:
        return instances_from_config

    default_instance_name = dataiku_config_file.get("default_instance", "")
    instances = dataiku_config_file.get("dss_instances", {})

    # If defined, validate that `default_instance_name` is present in `instances`.
    if default_instance_name and default_instance_name not in instances:
        raise ValueError(
            f"Default instance '{default_instance_name}' not found in "
            f".dataiku/config.json. Available: {instances.keys()}."
        )

    # Populate `instances_from_config`
    instances_from_config["default_instance"] = default_instance_name
    for name, details in instances.items():
        instances_from_config["dss_instances"][name] = DSSInstance(
            name=name,
            url=details["url"],
            api_key=details.get("api_key", ""),
            description=details.get("description", ""),
            no_check_certificate=details.get("no_check_certificate", False),
            source=".dataiku/config.json",
        )
    return instances_from_config


def _serialize_instances_from_config(config):
    config_serialized = {
        "default_instance": "",
        "dss_instances": {},
    }

    if config["default_instance"]:
        config_serialized["default_instance"] = config["default_instance"]

    for _, dss_instance in config["dss_instances"].items():
        serialized_instance = {
              "url": dss_instance.url,
              "api_key": dss_instance.api_key,
              "no_check_certificate": dss_instance.no_check_certificate,
          }
        if dss_instance.description:
            serialized_instance["description"] = dss_instance.description

        config_serialized["dss_instances"][dss_instance.name] = serialized_instance

    return config_serialized


### ------------------------------ ###
###      Getters and setters       ###
### ------------------------------ ###
def initialize_current_instance() -> None:
    """
    Initialize the _current_instance from environment variables and
    resolved config.json.

    Resolution order:
        1. Environment variables when `DKU_DSS_URL` is set
        2. The resolved config file's `default_instance`
        3. None if neither are defined
    """
    global _current_instance

    instance_from_env = _load_instance_from_env_vars()
    instances_from_config = _load_instances_from_config()

    config_default_instance = instances_from_config["default_instance"]
    if instance_from_env:
        _current_instance = instance_from_env
    elif config_default_instance:
        _current_instance = instances_from_config["dss_instances"][config_default_instance]
    else:
        _current_instance = None


def get_instances() -> dict[str, DSSInstance]:
    """Return the instances from the environment and config file."""
    instance_from_env = _load_instance_from_env_vars()
    instances_from_config = _load_instances_from_config()

    all_instances = {}
    if instance_from_env:
        all_instances[instance_from_env.name] = instance_from_env

    all_instances = instances_from_config["dss_instances"] | all_instances
    return all_instances


def get_current_instance() -> DSSInstance:
    """Return the currently active DSS instance."""
    if not _current_instance:
        raise ValueError("No current Dataiku instance configured.")

    return _current_instance


def get_current_instance_name() -> str:
    """Return the name of the currently active instance."""
    if not _current_instance:
        return ""

    return _current_instance.name


def set_current_instance(name: str) -> dict:
    """Set current instance to a named instance. Returns the instance info."""
    global _current_instance

    instances = get_instances()
    if name not in instances.keys():
        raise ValueError(
            f"Unknown instance '{name}'. Available: {list(instances.keys())}"
        )

    _current_instance = instances[name]
    return {
        "name": _current_instance.name,
        "url": _current_instance.url,
        "description": _current_instance.description,
    }

### ---------------------------------- ###
###       Add/Delete config file       ###
### ---------------------------------- ###


def _atomic_write_config(data: dict) -> None:
    path = get_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", dir=path.parent, prefix="config.", suffix=".tmp", delete=False
    ) as temp_file:
        json.dump(data, temp_file, indent=2)
        temp_file.write("\n")
        temp_path = Path(temp_file.name)
    temp_path.chmod(0o600)
    os.replace(temp_path, path)


def add_instance_to_config(
    name: str,
    url: str,
    api_key: str,
    *,
    description: str = "",
    no_check_certificate: bool = False,
    set_default: bool = False,
) -> dict:
    """Add an instance to resolved config.json"""
    new_instance = DSSInstance(
        name=name,
        url=url,
        api_key=api_key,
        description=description,
        no_check_certificate=no_check_certificate,
        source=".dataiku/config.json",
    )

    config = _load_instances_from_config()
    config["dss_instances"][name] = new_instance

    if set_default:
        config["default_instance"] = name

    config_serialized = _serialize_instances_from_config(config)
    _atomic_write_config(config_serialized)

    return {
        "name": name,
        "url": url,
        "description": description,
        "path": str(get_config_path()),
        "default_instance": config["default_instance"],
    }


def delete_instance_from_config(name: str) -> dict:
    """Remove a config-file instance from the resolved config file.

    Deletion of currently active instance is prohibited and results in
    ValueError.
    """
    config = _load_instances_from_config()
    instances_from_config = config.get("dss_instances", {})

    if name not in instances_from_config:
        raise ValueError(
            f"Instance '{name}' not found in config file. Available: {list(instances_from_config.keys())}"
        )
    if _current_instance and name == _current_instance.name:
        raise ValueError(
            f"'{name}' is the current active instance. Switch to another instance prior to deleting."
        )

    instances_from_config.pop(name, None)

    if config.get("default_instance") == name:
        config["default_instance"] = next(iter(instances_from_config), "")

    config_serialized = _serialize_instances_from_config(config)
    _atomic_write_config(config_serialized)

    return {
        "deleted": name,
        "path": str(get_config_path()),
        "default_instance": config.get("default_instance", ""),
        "remaining": list(instances_from_config.keys()),
    }
