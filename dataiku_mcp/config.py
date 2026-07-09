"""Configuration and environment variables for Dataiku MCP server."""

from dataclasses import dataclass
import json
import os
from pathlib import Path

DKU_CONFIG_FILE = Path(__file__).parent.parent / ".dataiku" / "config.json"

@dataclass(frozen=True)
class DSSInstance:
    name: str
    url: str
    api_key: str
    no_check_certificate: bool
    source: str
    description: str = ""
    default_connection: str | None = None
    default_folder_connection: str | None = None
    default_llm: str | None = None
    default_embedding_llm: str | None = None


_instances: dict[str, DSSInstance] = {}
_current_instance_name: str = ""

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
        default_connection=os.environ.get("DKU_DEFAULT_CONNECTION"),
        default_folder_connection=os.environ.get("DKU_DEFAULT_FOLDER_CONNECTION"),
        default_llm=os.environ.get("DKU_DEFAULT_LLM", ""),
        default_embedding_llm=os.environ.get("DKU_DEFAULT_EMBEDDING_LLM", ""),
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
        with open(DKU_CONFIG_FILE, "r") as f:
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
            api_key=details["api_key"],
            description=details.get("description", ""),
            no_check_certificate=details.get("no_check_certificate", False),
            default_connection=details.get("default_connection"),
            default_folder_connection=details.get("default_folder_connection"),
            default_llm=details.get("default_llm"),
            default_embedding_llm=details.get("default_embedding_llm"),
            source=".dataiku/config.json",
        )
    return instances_from_config


def load_dss_instances() -> None:
    """
    Load DSS instances from environment variables and `.dataiku/config.json`.

    The DSS instance defined in environment variables takes precedence over
    the default instance defined in `.dataiku/config.json`.
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
            "No current DSS instance configured. "
            f"Switch to an available instance: {_instances.keys()}."
        )
    if _current_instance_name not in _instances:
        raise ValueError(
            f"'{_current_instance_name}' is not in the list of available instances: "
            f"{_instances.keys()}. Switch to an available instance."
        )
    return _instances[_current_instance_name]
