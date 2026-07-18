"""Configuration and environment variables for Dataiku MCP server.

Config-file resolution (first hit wins), so an installed package does not read a
``.dataiku/config.json`` sitting next to the installed source tree:

1. ``$DKU_CONFIG_DIR/config.json`` when ``DKU_CONFIG_DIR`` is set,
2. else ``./.dataiku/config.json`` relative to the current working directory,
3. else ``$XDG_CONFIG_HOME/dataiku-headless/config.json`` (XDG-compliant; defaults
   to ``~/.config/dataiku-headless/config.json`` when ``XDG_CONFIG_HOME`` is unset).

``resolve_dotenv_path()`` exposes the matching precedence for a ``.env`` file so
the entrypoint can load it from the same locations (the actual ``load_dotenv``
call lives in the package ``__init__``).

The in-memory instance registry (``_instances`` / ``_current_instance_name``) is
guarded by ``_registry_lock`` because ``switch_instance`` can run concurrently
with tool calls that read the active instance.
"""

from dataclasses import dataclass
import json
import os
import threading
from pathlib import Path


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

# Guards the instance registry above. A plain Lock is sufficient: none of the
# guarded functions call another guarded function while holding it.
_registry_lock = threading.Lock()

### ------------------------------ ###
###       Config-file location     ###
### ------------------------------ ###

_TRUE_TOKENS = frozenset({"true", "1", "yes"})
_FALSE_TOKENS = frozenset({"false", "0", "no", ""})


def _xdg_config_home() -> Path:
    """Return ``$XDG_CONFIG_HOME`` when set, else the XDG default ``~/.config``."""
    raw = os.environ.get("XDG_CONFIG_HOME", "").strip()
    if raw:
        return Path(raw)
    return Path.home() / ".config"


def _config_search_paths() -> list[Path]:
    """Ordered candidate locations for ``config.json`` (first hit wins)."""
    paths: list[Path] = []
    config_dir = os.environ.get("DKU_CONFIG_DIR", "").strip()
    if config_dir:
        paths.append(Path(config_dir) / "config.json")
    paths.append(Path.cwd() / ".dataiku" / "config.json")
    paths.append(_xdg_config_home() / "dataiku-headless" / "config.json")
    return paths


def resolve_config_file() -> Path | None:
    """Return the first existing config file from the search order, or None."""
    for candidate in _config_search_paths():
        if candidate.is_file():
            return candidate
    return None


def resolve_dotenv_path() -> Path:
    """Return the ``.env`` path to load, using the same precedence as config.json.

    Returns the first existing candidate; if none exist, returns the cwd-relative
    ``./.env`` (a missing file is a no-op for ``load_dotenv``). The package
    ``__init__`` should call this instead of hardcoding a path next to the
    installed source tree.
    """
    candidates: list[Path] = []
    config_dir = os.environ.get("DKU_CONFIG_DIR", "").strip()
    if config_dir:
        candidates.append(Path(config_dir) / ".env")
    candidates.append(Path.cwd() / ".env")
    candidates.append(_xdg_config_home() / "dataiku-headless" / ".env")
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return candidates[-2] if config_dir else candidates[0]


### ------------------------------ ###
###       Load configuration       ###
### ------------------------------ ###
def _parse_no_check_certificate(value: str) -> bool:
    """Strictly parse a boolean env value, failing closed on garbage.

    Fails loudly rather than treating an unrecognised value (e.g. a typo like
    ``"flase"``) as a silent True/False, which previously could disable
    certificate verification by accident.
    """
    token = (value or "").strip().lower()
    if token in _TRUE_TOKENS:
        return True
    if token in _FALSE_TOKENS:
        return False
    raise ValueError(
        f"Invalid DKU_NO_CHECK_CERTIFICATE {value!r}. Allowed values: "
        "true/1/yes (verification off) or false/0/no or empty (verification on)."
    )


def _coerce_no_check_certificate(value: object, *, instance_name: str) -> bool:
    """Strictly coerce a config-file ``no_check_certificate`` value.

    A JSON boolean is honored directly; a JSON string runs through the same
    strict vocabulary as the env parser (``true``/``1``/``yes`` vs
    ``false``/``0``/``no``/empty). Everything else — including the string
    ``"false"`` being naively truthy — raises, naming the offending instance, so
    a typo or a stringified bool can never silently disable TLS verification.
    """
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, str):
        try:
            return _parse_no_check_certificate(value)
        except ValueError as exc:
            raise ValueError(
                f"Invalid 'no_check_certificate' for instance '{instance_name}': "
                f"{exc}"
            ) from exc
    raise ValueError(
        f"Invalid 'no_check_certificate' for instance '{instance_name}': {value!r}. "
        "Expected a JSON boolean or one of true/1/yes, false/0/no."
    )


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
    Load DSS instances from the resolved ``config.json`` (see module docstring),
    if such a file exists.

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

    config_file = resolve_config_file()
    if config_file is None:
        return instances_from_config

    with open(config_file, "r") as f:
        dataiku_config_file = json.load(f)

    default_instance_name = dataiku_config_file.get("default_instance", "")
    instances = dataiku_config_file.get("dss_instances", {})

    # If defined, validate that `default_instance_name` is present in `instances`.
    if default_instance_name and default_instance_name not in instances:
        raise ValueError(
            f"Default instance '{default_instance_name}' not found in "
            f"{config_file}. Available: {instances.keys()}."
        )

    # Populate `instances_from_config`
    instances_from_config["default_instance"] = default_instance_name
    for name, details in instances.items():
        instances_from_config["instances"][name] = DSSInstance(
            name=name,
            url=details["url"],
            api_key=details["api_key"],
            description=details.get("description", ""),
            no_check_certificate=_coerce_no_check_certificate(
                details.get("no_check_certificate", False), instance_name=name
            ),
            source=str(config_file),
        )
    return instances_from_config


def load_dss_instances() -> None:
    """
    Load DSS instances from environment variables and the resolved ``config.json``.

    The DSS instance defined in environment variables takes precedence over
    the default instance defined in the config file.
    """
    global _instances, _current_instance_name

    # Load instances from environment and config file
    instance_from_env = _load_instance_from_env_vars()
    instances_from_config = _load_instances_from_config()

    # Merge instances (instance from env var takes precedence as default)
    with _registry_lock:
        _current_instance_name = instances_from_config["default_instance"]
        _instances = instances_from_config["instances"]

        if instance_from_env:
            _current_instance_name = instance_from_env.name
            _instances[_current_instance_name] = instance_from_env


### ---------------------------------- ###
###       Retrieve configuration       ###
### ---------------------------------- ###

def switch_instance(name: str) -> dict:
    """Switch to a named instance. Returns the instance info.

    The switch is atomic with respect to concurrent readers, but it only affects
    tool calls that resolve the instance *after* it returns; a Cobuild turn (or
    any other call) already in flight keeps running against the instance it was
    started on.
    """
    with _registry_lock:
        # Validate that instance `name` exists in `_instances`
        if name not in _instances:
            raise ValueError(
                f"Unknown instance '{name}'. Available: {list(_instances.keys())}"
            )

        # Set `_current_instance_name` and return summary information
        global _current_instance_name
        _current_instance_name = name
        instance = _instances[name]
        return {
            "name": name,
            "url": instance.url,
            "description": instance.description,
        }


def get_instances() -> dict[str, DSSInstance]:
    """Return a snapshot of the loaded instances dict."""
    with _registry_lock:
        return dict(_instances)


def get_current_instance_name() -> str:
    """Return the name of the currently active instance."""
    with _registry_lock:
        return _current_instance_name


def get_current_instance() -> DSSInstance:
    """Return the currently active DSS instance as an immutable snapshot."""
    with _registry_lock:
        if not _current_instance_name:
            raise ValueError(
                "No current DSS instance configured. "
                f"Switch to an available instance: {list(_instances.keys())}."
            )
        if _current_instance_name not in _instances:
            raise ValueError(
                f"'{_current_instance_name}' is not in the list of available "
                f"instances: {list(_instances.keys())}. Switch to an available "
                "instance."
            )
        return _instances[_current_instance_name]
