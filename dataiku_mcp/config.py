"""Configuration and environment variables for Dataiku MCP server."""

import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path


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



@dataclass(frozen=True)
class DSSInstance:
    name: str
    url: str
    api_key: str
    no_check_certificate: bool
    source: str
    description: str = ""


_instances: dict[str, DSSInstance] = {}
_current_instance_name: str = ""
_config_file: Path | None = None


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
    Load DSS instances from `.dataiku/config.json`, if the file exists.

    If the file defines a non-empty `default_instance`, validate that the
    instance name exists in `dss_instances`; raise `ValueError` otherwise.

    Returns a dictionary with shape
    `{"default_instance": "...", "instances": {...}}`, where the values in
    `instances` are `DSSInstance` objects keyed by instance name.
    """
    instances_from_config = {
        "default_instance": "",
        "instances": {},
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
        instances_from_config["instances"][name] = DSSInstance(
            name=name,
            url=details["url"],
            api_key=details.get("api_key", ""),
            description=details.get("description", ""),
            no_check_certificate=details.get("no_check_certificate", False),
            source=".dataiku/config.json",
        )
    return instances_from_config


def load_dss_instances() -> None:
    """
    Load DSS instances from environment variables and `.dataiku/config.json`.

    The config file's `default_instance` selects the startup instance. When
    `DKU_DSS_URL` is set, its environment-backed instance is added and made
    active instead.
    """
    global _instances, _current_instance_name

    # Load instances from environment and config file
    instance_from_env = _load_instance_from_env_vars()
    instances_from_config = _load_instances_from_config()

    # Merge instances (instance from env var takes precedence as default)
    _current_instance_name = instances_from_config["default_instance"]
    _instances = instances_from_config["instances"]

    if instance_from_env:
        _current_instance_name = instance_from_env.name
        _instances[_current_instance_name] = instance_from_env


### ---------------------------------- ###
###       Retrieve configuration       ###
### ---------------------------------- ###


def _atomic_write_config(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", dir=path.parent, prefix="config.", suffix=".tmp", delete=False
    ) as temp_file:
        json.dump(data, temp_file, indent=2)
        temp_file.write("\n")
        temp_path = Path(temp_file.name)
    temp_path.chmod(0o600)
    os.replace(temp_path, path)


def save_instance_from_setup(
    name: str,
    url: str,
    api_key: str,
    *,
    description: str = "",
    no_check_certificate: bool = False,
    set_default: bool = False,
) -> dict:
    """Persist a profile submitted through the local configuration page.

    The API key is written to the resolved configuration file in plaintext;
    the file is created atomically with user-only (0600) permissions.
    """
    global _current_instance_name

    path = get_config_path()
    data: dict = {}
    if path.exists():
        with open(path, "r") as f:
            data = json.load(f)

    instances = data.setdefault("dss_instances", {})
    entry = dict(instances.get(name, {}))
    entry.pop("credential_id", None)
    entry["url"] = url
    entry["api_key"] = api_key
    if description:
        entry["description"] = description
    else:
        entry.pop("description", None)
    if no_check_certificate:
        entry["no_check_certificate"] = True
    else:
        entry.pop("no_check_certificate", None)
    instances[name] = entry

    if set_default or not data.get("default_instance"):
        data["default_instance"] = name

    _atomic_write_config(path, data)

    load_dss_instances()
    _current_instance_name = name

    return {
        "name": name,
        "url": url,
        "description": description,
        "path": str(path),
        "default_instance": data["default_instance"],
        "active": True,
    }


def delete_instance(name: str) -> dict:
    """Remove a config-file instance from `.dataiku/config.json`.

    Only file-backed instances can be deleted. An instance defined through
    environment variables must be removed by unsetting `DKU_DSS_URL`. If the
    removed instance was the `default_instance`, the default is reassigned to
    the first remaining instance (or cleared when none remain).
    """
    if name not in _instances:
        raise ValueError(
            f"Unknown instance '{name}'. Available: {list(_instances.keys())}"
        )
    if _instances[name].source != ".dataiku/config.json":
        raise ValueError(
            f"Instance '{name}' comes from environment variables and is not stored "
            "in the config file. Unset DKU_DSS_URL (and DKU_INSTANCE_NAME) to remove it."
        )

    path = get_config_path()
    with open(path, "r") as f:
        data = json.load(f)

    instances = data.get("dss_instances", {})
    instances.pop(name, None)

    if data.get("default_instance") == name:
        data["default_instance"] = next(iter(instances), "")

    _atomic_write_config(path, data)
    load_dss_instances()

    return {
        "deleted": name,
        "path": str(path),
        "default_instance": data.get("default_instance", ""),
        "remaining": list(instances.keys()),
    }


def switch_instance(name: str) -> dict:
    """Switch to a named instance. Returns the instance info."""
    global _current_instance_name

    # Validate that instance `name` exists in `_instances`
    if name not in _instances:
        raise ValueError(
            f"Unknown instance '{name}'. Available: {list(_instances.keys())}"
        )

    # Set `_current_instance_name` and return summary information
    _current_instance_name = name
    return {
        "name": name,
        "url": _instances[_current_instance_name].url,
        "description": _instances[_current_instance_name].description,
    }


def get_instances() -> dict[str, DSSInstance]:
    """Return the loaded instances dict."""
    return _instances


def get_current_instance_name() -> str:
    """Return the name of the currently active instance."""
    return _current_instance_name


def get_current_instance() -> DSSInstance:
    """Return the currently active DSS instance."""
    if not _current_instance_name:
        raise ValueError(
            "No Dataiku instance is configured. Run configure_instance for local "
            "stdio, set DKU_DSS_URL and DKU_API_KEY for automation, or add a "
            "profile to the resolved configuration file."
        )
    if _current_instance_name not in _instances:
        raise ValueError(
            f"'{_current_instance_name}' is not in the list of available instances: "
            f"{_instances.keys()}. Switch to an available instance."
        )
    return _instances[_current_instance_name]
