"""Configuration and environment variables for Dataiku MCP server."""

import json
import os
import tempfile
import threading
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
    jwt_audience: str = ""
    jwt_scope: str = ""


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
_http_config_file: Path | None = None
_http_config_lock = threading.Lock()

_UNPINNED = object()
_pinned_instance: ContextVar[DSSInstance | None | object] = ContextVar(
    "dataiku_mcp_pinned_instance",
    default=_UNPINNED,
)
_http_identity: ContextVar[tuple[str, str] | None] = ContextVar(
    "dataiku_mcp_http_identity", default=None
)
_http_dss_token: ContextVar[str | None] = ContextVar(
    "dataiku_mcp_http_dss_token", default=None
)


DEFAULT_HTTP_CONFIG_PATH = Path.home() / ".dataiku-mcp" / "http.json"


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


def set_http_config_path(path: Path | None) -> None:
    """Select the HTTP settings file for this server process."""
    global _http_config_file
    _http_config_file = (
        path.expanduser() if path is not None else DEFAULT_HTTP_CONFIG_PATH
    )


def get_http_config_path() -> Path:
    """Return the single operator-managed HTTP configuration file."""
    global _http_config_file
    if _http_config_file is None:
        _http_config_file = DEFAULT_HTTP_CONFIG_PATH
    return _http_config_file


def _load_http_config_document() -> dict:
    try:
        with open(get_http_config_path(), "r") as file:
            document = json.load(file)
    except FileNotFoundError as err:
        raise ValueError(
            f"HTTP instance configuration was not found at '{get_http_config_path()}'."
        ) from err
    if not isinstance(document, dict):
        raise ValueError("HTTP instance configuration must be a JSON object.")
    return document


def _require_http_section(document: dict, name: str) -> dict:
    section = document.get(name)
    if not isinstance(section, dict):
        raise ValueError(f"HTTP settings requires an object named '{name}'.")
    return section


def _require_http_string(section: dict, section_name: str, key: str) -> str:
    value = section.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"HTTP settings requires '{section_name}.{key}'.")
    return value


def get_http_auth_settings() -> dict[str, str]:
    """Return the OIDC and RFC 8693 settings from the HTTP settings file."""
    document = _load_http_config_document()
    oidc = _require_http_section(document, "oidc")
    token_exchange = _require_http_section(document, "token_exchange")
    return {
        "issuer": _require_http_string(oidc, "oidc", "issuer"),
        "jwks_uri": _require_http_string(oidc, "oidc", "jwks_uri"),
        "audience": _require_http_string(oidc, "oidc", "audience"),
        "scope": _require_http_string(oidc, "oidc", "scope"),
        "token_exchange_url": _require_http_string(
            token_exchange, "token_exchange", "url"
        ),
        "client_id": _require_http_string(
            token_exchange, "token_exchange", "client_id"
        ),
        "client_secret": _require_http_string(
            token_exchange, "token_exchange", "client_secret"
        ),
    }


def get_http_server_settings() -> dict[str, str | int]:
    """Return validated Streamable HTTP transport settings."""
    server = _require_http_section(_load_http_config_document(), "server")
    host = _require_http_string(server, "server", "host")
    path = _require_http_string(server, "server", "path")
    port = server.get("port")
    if not isinstance(port, int):
        raise ValueError("HTTP settings requires integer 'server.port'.")
    return {"host": host, "port": port, "path": path}


def _http_instances_and_defaults() -> tuple[
    dict[str, DSSInstance], dict[str, dict[str, str]]
]:
    document = _load_http_config_document()
    raw_instances = document.get("dss_instances")
    defaults = document.get("user_defaults", {})
    if not isinstance(raw_instances, dict) or not raw_instances:
        raise ValueError(
            "HTTP instance configuration requires non-empty dss_instances."
        )
    if not isinstance(defaults, dict):
        raise ValueError("HTTP instance configuration user_defaults must be an object.")

    instances: dict[str, DSSInstance] = {}
    for name, details in raw_instances.items():
        if not isinstance(details, dict):
            raise ValueError(f"HTTP instance '{name}' must be an object.")
        url = details.get("url", "")
        audience = details.get("audience", "")
        scope = details.get("scope", "")
        if not all(
            isinstance(value, str) and value for value in (url, audience, scope)
        ):
            raise ValueError(
                f"HTTP instance '{name}' requires non-empty url, audience, and scope."
            )
        instances[name] = DSSInstance(
            name=name,
            url=url,
            api_key="",
            no_check_certificate=bool(details.get("no_check_certificate", False)),
            source="http",
            description=details.get("description", ""),
            jwt_audience=audience,
            jwt_scope=scope,
        )

    for issuer, subjects in defaults.items():
        if not isinstance(issuer, str) or not isinstance(subjects, dict):
            raise ValueError("HTTP user_defaults must map issuers to subject mappings.")
        for subject, instance_name in subjects.items():
            if not isinstance(subject, str) or instance_name not in instances:
                raise ValueError("HTTP user_defaults references an unknown instance.")
    return instances, defaults


def is_http_request() -> bool:
    """Whether the current tool call has an authenticated HTTP identity."""
    return _http_identity.get() is not None


def bind_http_identity(issuer: str, subject: str) -> Token:
    """Bind the verified OIDC identity for one HTTP tool request."""
    if not issuer or not subject:
        raise ValueError(
            "The HTTP access token must contain non-empty iss and sub claims."
        )
    return _http_identity.set((issuer, subject))


def reset_http_identity(token: Token) -> None:
    _http_identity.reset(token)


def set_http_dss_token(token: str) -> Token:
    return _http_dss_token.set(token)


def reset_http_dss_token(token: Token) -> None:
    _http_dss_token.reset(token)


def get_http_dss_token() -> str:
    token = _http_dss_token.get()
    if not token:
        raise ValueError("No delegated DSS token is available for this HTTP request.")
    return token


def get_request_owner() -> tuple[str, ...]:
    """Return a stable, request-scoped owner identity for retained state."""
    identity = _http_identity.get()
    return ("local",) if identity is None else ("oidc", *identity)


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
        )
    return DSSConfig(default_instance_name, dss_instances)


def _save_json(data: dict, path: Path) -> None:
    """Atomically persist a JSON document with user-only file permissions."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", dir=path.parent, prefix="config.", suffix=".tmp", delete=False
    ) as temp_file:
        json.dump(data, temp_file, indent=2)
        temp_file.write("\n")
        temp_path = Path(temp_file.name)
    temp_path.chmod(0o600)
    os.replace(temp_path, path)


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
        serialized_instances[name] = serialized_instance

    data = {
        "default_instance": config.default_instance or "",
        "dss_instances": serialized_instances,
    }
    _save_json(data, get_config_path())


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
    if is_http_request():
        instances, _ = _http_instances_and_defaults()
        return instances

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
    if is_http_request():
        instances, defaults = _http_instances_and_defaults()
        issuer, subject = _http_identity.get()  # type: ignore[misc]
        selected_name = defaults.get(issuer, {}).get(subject)
        return _pinned_instance.set(instances[selected_name] if selected_name else None)
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

    if is_http_request():
        issuer, subject = _http_identity.get()  # type: ignore[misc]
        with _http_config_lock:
            document = _load_http_config_document()
            defaults = document.setdefault("user_defaults", {})
            if not isinstance(defaults, dict):
                raise ValueError(
                    "HTTP instance configuration user_defaults must be an object."
                )
            issuer_defaults = defaults.setdefault(issuer, {})
            if not isinstance(issuer_defaults, dict):
                raise ValueError(
                    "HTTP user_defaults must map issuers to subject mappings."
                )
            issuer_defaults[subject] = name
            _save_json(document, get_http_config_path())
        selected = instances[name]
        return {
            "name": selected.name,
            "url": selected.url,
            "description": selected.description,
        }

    _current_instance = instances[name]
    return {
        "name": _current_instance.name,
        "url": _current_instance.url,
        "description": _current_instance.description,
    }


def add_instance_to_config(
    name: str,
    url: str,
    api_key: str,
    *,
    description: str = "",
    no_check_certificate: bool = False,
    set_default: bool = False,
) -> dict:
    """Add an instance to the resolved config file."""
    if is_http_request():
        raise ValueError(
            "HTTP instances are platform-managed and cannot be configured here."
        )
    new_instance = DSSInstance(
        name=name,
        url=url,
        api_key=api_key,
        description=description,
        no_check_certificate=no_check_certificate,
        source="config",
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
        "path": str(get_config_path()),
        "default_instance": config.default_instance,
    }


def delete_instance_from_config(name: str) -> dict:
    """Remove a config-file instance from the resolved config file."""
    global _current_instance

    if is_http_request():
        raise ValueError(
            "HTTP instances are platform-managed and cannot be deleted here."
        )

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
