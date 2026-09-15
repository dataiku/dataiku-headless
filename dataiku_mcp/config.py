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

"""Configuration and environment variables for Dataiku MCP server."""

import json
import os
import tempfile
from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class DSSInstance:
    name: str
    url: str
    api_key: str
    no_check_certificate: bool
    source: str
    description: str = ""
    govern_url: str = ""
    govern_api_key: str = ""
    govern_no_check_certificate: bool = False


@dataclass(frozen=True)
class GovernConnection:
    """Resolved Govern node credentials for the govern tool."""

    url: str
    api_key: str
    no_check_certificate: bool
    source: str
    instance_name: str = ""


@dataclass
class DSSConfig:
    """Persisted Dataiku instance profiles and their startup default."""

    default_instance: str | None = None
    dss_instances: dict[str, DSSInstance] = field(default_factory=dict)


class NoConfiguredInstancesError(ValueError):
    """Raised when no Dataiku instances are available."""


class NoActiveInstanceError(ValueError):
    """Raised when instances exist but none is selected."""


_current_instance: DSSInstance | None = None
_config_file: Path | None = None

_UNPINNED = object()
_pinned_instance: ContextVar[DSSInstance | None | object] = ContextVar(
    "dataiku_mcp_pinned_instance",
    default=_UNPINNED,
)


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


def _parse_no_check_certificate(value: str) -> bool:
    return bool(value.strip()) and value.strip().lower() != "false"


def _load_instance_from_env_vars() -> DSSInstance | None:
    """
    Load the Dataiku instance defined by environment variables. An instance
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
        source="environment",
        govern_url=os.environ.get("DKU_GOVERN_URL", ""),
        govern_api_key=os.environ.get("DKU_GOVERN_API_KEY", ""),
        govern_no_check_certificate=_parse_no_check_certificate(
            os.environ.get("DKU_GOVERN_NO_CHECK_CERTIFICATE", "")
        ),
    )


def get_govern_connection_from_env() -> GovernConnection | None:
    """Return the Govern node defined by `DKU_GOVERN_URL`, or None.

    Environment variables win over the active instance profile so a CI job or
    a quick test can target a Govern node without editing the config file.
    """
    govern_url = os.environ.get("DKU_GOVERN_URL", "").strip()
    if not govern_url:
        return None
    return GovernConnection(
        url=govern_url,
        api_key=os.environ.get("DKU_GOVERN_API_KEY", ""),
        no_check_certificate=_parse_no_check_certificate(
            os.environ.get("DKU_GOVERN_NO_CHECK_CERTIFICATE", "")
        ),
        source="environment",
    )


def govern_connection_for_instance(instance: DSSInstance) -> GovernConnection:
    """Return the Govern node stored on an instance profile (URL may be empty)."""
    return GovernConnection(
        url=instance.govern_url,
        api_key=instance.govern_api_key,
        no_check_certificate=instance.govern_no_check_certificate,
        source=instance.source,
        instance_name=instance.name,
    )


def _load_config() -> DSSConfig:
    """Load the resolved config file into the canonical in-memory model.

    If the file defines a non-empty `default_instance`, validate that the
    instance name exists in `dss_instances`; raise `ValueError` otherwise.
    """
    try:
        with open(get_config_path(), "r") as f:
            dataiku_config_file = json.load(f)
    except FileNotFoundError:
        return DSSConfig()

    default_instance_name = dataiku_config_file.get("default_instance") or None
    instances = dataiku_config_file.get("dss_instances", {})

    # If defined, validate that `default_instance_name` is present in `instances`.
    if default_instance_name and default_instance_name not in instances:
        raise ValueError(
            f"Default instance '{default_instance_name}' not found in "
            f".dataiku/config.json. Available: {instances.keys()}."
        )

    dss_instances = {}
    for name, details in instances.items():
        dss_instances[name] = DSSInstance(
            name=name,
            url=details["url"],
            api_key=details.get("api_key", ""),
            description=details.get("description", ""),
            no_check_certificate=details.get("no_check_certificate", False),
            source="config",
            govern_url=details.get("govern_url", ""),
            govern_api_key=details.get("govern_api_key", ""),
            govern_no_check_certificate=details.get(
                "govern_no_check_certificate", False
            ),
        )
    return DSSConfig(default_instance_name, dss_instances)


def _save_config(config: DSSConfig) -> None:
    """Serialize and atomically persist the canonical config document."""
    serialized_instances = {}
    for name, instance in config.dss_instances.items():
        serialized_instance = {
            "url": instance.url,
            "api_key": instance.api_key,
            "no_check_certificate": instance.no_check_certificate,
        }
        if instance.description:
            serialized_instance["description"] = instance.description
        if instance.govern_url or instance.govern_api_key:
            serialized_instance["govern_url"] = instance.govern_url
            serialized_instance["govern_api_key"] = instance.govern_api_key
            serialized_instance["govern_no_check_certificate"] = (
                instance.govern_no_check_certificate
            )
        serialized_instances[name] = serialized_instance

    data = {
        "default_instance": config.default_instance or "",
        "dss_instances": serialized_instances,
    }
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
    config = _load_config()

    if instance_from_env:
        _current_instance = instance_from_env
    elif config.default_instance:
        _current_instance = config.dss_instances[config.default_instance]
    else:
        _current_instance = None


def get_instances() -> dict[str, DSSInstance]:
    """Return the instances from the environment and config file."""
    instance_from_env = _load_instance_from_env_vars()
    config = _load_config()

    all_instances = {}
    if instance_from_env:
        all_instances[instance_from_env.name] = instance_from_env

    all_instances = config.dss_instances | all_instances
    return all_instances


def pin_current_instance() -> Token:
    """Bind the active instance to the current MCP request context.

    Tool requests can overlap while a blocking SDK call is queued. Snapshotting
    here keeps a later ``switch_instance`` call from redirecting that request.
    ``None`` is intentionally pinned too, so a request that began without a
    configured instance cannot silently pick up one configured concurrently.
    """
    return _pinned_instance.set(_current_instance)


def reset_pinned_instance(token: Token) -> None:
    """Restore the request-local instance binding after a tool returns."""
    _pinned_instance.reset(token)


def get_current_instance() -> DSSInstance:
    """Return the currently active Dataiku instance."""
    pinned_instance = _pinned_instance.get()
    if pinned_instance is not _UNPINNED:
        if pinned_instance is not None:
            return pinned_instance
    elif _current_instance:
        return _current_instance

    if get_instances():
        raise NoActiveInstanceError("No active Dataiku instance is selected.")
    raise NoConfiguredInstancesError("No Dataiku instances are configured.")


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
        "govern_url": _current_instance.govern_url,
    }


def add_instance_to_config(
    name: str,
    url: str,
    api_key: str,
    *,
    description: str = "",
    no_check_certificate: bool = False,
    set_default: bool = False,
    govern_url: str = "",
    govern_api_key: str = "",
    govern_no_check_certificate: bool = False,
) -> dict:
    """Add an instance to the resolved config file."""
    new_instance = DSSInstance(
        name=name,
        url=url,
        api_key=api_key,
        description=description,
        no_check_certificate=no_check_certificate,
        source="config",
        govern_url=govern_url,
        govern_api_key=govern_api_key,
        govern_no_check_certificate=govern_no_check_certificate,
    )

    config = _load_config()
    config.dss_instances[name] = new_instance

    if set_default:
        config.default_instance = name

    _save_config(config)

    return {
        "name": name,
        "url": url,
        "description": description,
        "govern_url": govern_url,
        "path": str(get_config_path()),
        "default_instance": config.default_instance,
    }


def delete_instance_from_config(name: str) -> dict:
    """Remove a config-file instance from the resolved config file."""
    global _current_instance

    config = _load_config()
    dss_instances = config.dss_instances

    if name not in dss_instances:
        raise ValueError(
            f"Instance '{name}' not found in config file. Available: {list(dss_instances.keys())}"
        )

    was_current = (
        _current_instance is not None
        and _current_instance.source == "config"
        and _current_instance.name == name
    )
    dss_instances.pop(name)

    if config.default_instance == name:
        config.default_instance = next(iter(dss_instances), None)

    _save_config(config)

    if was_current:
        _current_instance = (
            dss_instances[config.default_instance] if config.default_instance else None
        )

    return {
        "deleted": name,
        "path": str(get_config_path()),
        "default_instance": config.default_instance,
        "remaining": list(dss_instances.keys()),
    }
