"""Operator-managed Streamable HTTP configuration."""

import threading
from pathlib import Path
from urllib.parse import urlparse

from .files import read_json_object, write_json_atomic
from .models import (
    DSSInstance,
    HTTPAuthConfig,
    HTTPConfig,
    HTTPInteractiveAuthConfig,
    HTTPServerConfig,
    HTTPTokenExchangeConfig,
)


DEFAULT_SETTINGS_PATH = Path.home() / ".dataiku" / "http-config.json"

_settings_path: Path | None = None
_settings_lock = threading.Lock()


def set_settings_path(path: Path | None) -> Path:
    """Select the HTTP settings file for this server process."""
    global _settings_path
    _settings_path = path.expanduser() if path is not None else DEFAULT_SETTINGS_PATH
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

    expected_top_level = {
        "server",
        "oidc",
        "token_exchange",
        "dss_instances",
        "user_selections",
    }
    unknown = set(document) - expected_top_level
    if unknown:
        raise ValueError(
            f"HTTP instance configuration contains unknown fields: {sorted(unknown)}."
        )

    sections = {}
    expected_section_fields = {
        "server": {"host", "port", "path", "public_url"},
        "oidc": {
            "provider",
            "issuer",
            "jwks_uri",
            "audience",
            "scope",
            "interactive",
        },
        "token_exchange": {"url", "client_id", "client_secret"},
    }
    for section_name, expected_fields in expected_section_fields.items():
        section = document.get(section_name)
        if not isinstance(section, dict):
            raise ValueError(
                f"HTTP settings requires an object named '{section_name}'."
            )
        unknown = set(section) - expected_fields
        if unknown:
            raise ValueError(
                f"HTTP settings section '{section_name}' contains unknown fields: "
                f"{sorted(unknown)}."
            )
        sections[section_name] = section

    server = sections["server"]
    oidc = sections["oidc"]
    token_exchange = sections["token_exchange"]
    for section_name, section, keys in (
        ("server", server, ("host", "path")),
        (
            "oidc",
            oidc,
            ("provider", "issuer", "jwks_uri", "audience", "scope"),
        ),
        (
            "token_exchange",
            token_exchange,
            ("url", "client_id", "client_secret"),
        ),
    ):
        for key in keys:
            value = section.get(key)
            if not isinstance(value, str) or not value:
                raise ValueError(f"HTTP settings requires '{section_name}.{key}'.")

    port = server.get("port")
    if not isinstance(port, int):
        raise ValueError("HTTP settings requires integer 'server.port'.")

    provider = oidc["provider"]
    if provider not in {"entra", "oidc"}:
        raise ValueError("HTTP settings 'oidc.provider' must be 'entra' or 'oidc'.")

    public_url = server.get("public_url", "")
    if "public_url" in server:
        parsed_public_url = (
            urlparse(public_url) if isinstance(public_url, str) else None
        )
        if (
            parsed_public_url is None
            or parsed_public_url.scheme not in {"http", "https"}
            or not parsed_public_url.netloc
        ):
            raise ValueError("HTTP settings requires an absolute 'server.public_url'.")

    raw_interactive = oidc.get("interactive")
    interactive = None
    if raw_interactive is not None:
        if not isinstance(raw_interactive, dict):
            raise ValueError("HTTP settings 'oidc.interactive' must be an object.")
        unknown = set(raw_interactive) - {"client_id", "client_secret", "tenant_id"}
        if unknown:
            raise ValueError(
                "HTTP settings section 'oidc.interactive' contains unknown fields: "
                f"{sorted(unknown)}."
            )
        for key in ("client_id", "client_secret"):
            value = raw_interactive.get(key)
            if not isinstance(value, str) or not value:
                raise ValueError(f"HTTP settings requires 'oidc.interactive.{key}'.")
        tenant_id = raw_interactive.get("tenant_id", "")
        if provider == "entra":
            if not isinstance(tenant_id, str) or not tenant_id:
                raise ValueError(
                    "HTTP settings requires 'oidc.interactive.tenant_id' for Entra."
                )
        elif "tenant_id" in raw_interactive:
            raise ValueError(
                "HTTP settings 'oidc.interactive.tenant_id' is only valid for Entra."
            )
        if not public_url:
            raise ValueError(
                "HTTP settings requires 'server.public_url' for interactive OAuth."
            )
        interactive = HTTPInteractiveAuthConfig(
            client_id=raw_interactive["client_id"],
            client_secret=raw_interactive["client_secret"],
            tenant_id=tenant_id,
        )

    raw_instances = document.get("dss_instances")
    selections = document.get("user_selections", {})
    if not isinstance(raw_instances, dict) or not raw_instances:
        raise ValueError(
            "HTTP instance configuration requires non-empty dss_instances."
        )
    if not isinstance(selections, dict):
        raise ValueError(
            "HTTP instance configuration user_selections must be an object."
        )

    instances: dict[str, DSSInstance] = {}
    for name, details in raw_instances.items():
        if not isinstance(details, dict):
            raise ValueError(f"HTTP instance '{name}' must be an object.")
        unknown = set(details) - {
            "url",
            "audience",
            "scope",
            "no_check_certificate",
            "description",
        }
        if unknown:
            raise ValueError(
                f"HTTP instance '{name}' contains unknown fields: {sorted(unknown)}."
            )
        url = details.get("url", "")
        audience = details.get("audience", "")
        scope = details.get("scope", "")
        if not all(
            isinstance(value, str) and value for value in (url, audience, scope)
        ):
            raise ValueError(
                f"HTTP instance '{name}' requires non-empty url, audience, and scope."
            )
        description = details.get("description", "")
        if not isinstance(description, str):
            raise ValueError(f"HTTP instance '{name}' description must be a string.")
        no_check_certificate = details.get("no_check_certificate", False)
        if not isinstance(no_check_certificate, bool):
            raise ValueError(
                f"HTTP instance '{name}' no_check_certificate must be a boolean."
            )
        instances[name] = DSSInstance(
            name=name,
            url=url,
            api_key="",
            no_check_certificate=no_check_certificate,
            source="http",
            description=description,
            jwt_audience=audience,
            jwt_scope=scope,
        )

    for issuer, subjects in selections.items():
        if not isinstance(issuer, str) or not isinstance(subjects, dict):
            raise ValueError(
                "HTTP user_selections must map issuers to subject mappings."
            )
        for subject, instance_name in subjects.items():
            if not isinstance(subject, str) or not isinstance(instance_name, str):
                raise ValueError(
                    "HTTP user_selections must map subjects to instance names."
                )
    return HTTPConfig(
        server=HTTPServerConfig(
            host=server["host"],
            port=port,
            path=server["path"],
            public_url=public_url.rstrip("/"),
        ),
        auth=HTTPAuthConfig(
            provider=provider,
            issuer=oidc["issuer"],
            jwks_uri=oidc["jwks_uri"],
            audience=oidc["audience"],
            scope=oidc["scope"],
            interactive=interactive,
        ),
        token_exchange=HTTPTokenExchangeConfig(
            url=token_exchange["url"],
            client_id=token_exchange["client_id"],
            client_secret=token_exchange["client_secret"],
        ),
        dss_instances=instances,
        user_selections=selections,
    )


def _save_config(config: HTTPConfig) -> None:
    instances = {}
    for name, instance in config.dss_instances.items():
        serialized = {
            "url": instance.url,
            "audience": instance.jwt_audience,
            "scope": instance.jwt_scope,
            "no_check_certificate": instance.no_check_certificate,
        }
        if instance.description:
            serialized["description"] = instance.description
        instances[name] = serialized

    write_json_atomic(
        get_settings_path(),
        {
            "server": {
                "host": config.server.host,
                "port": config.server.port,
                "path": config.server.path,
                **(
                    {"public_url": config.server.public_url}
                    if config.server.public_url
                    else {}
                ),
            },
            "oidc": {
                "provider": config.auth.provider,
                "issuer": config.auth.issuer,
                "jwks_uri": config.auth.jwks_uri,
                "audience": config.auth.audience,
                "scope": config.auth.scope,
                **(
                    {
                        "interactive": {
                            "client_id": config.auth.interactive.client_id,
                            "client_secret": config.auth.interactive.client_secret,
                            **(
                                {"tenant_id": config.auth.interactive.tenant_id}
                                if config.auth.interactive.tenant_id
                                else {}
                            ),
                        }
                    }
                    if config.auth.interactive is not None
                    else {}
                ),
            },
            "token_exchange": {
                "url": config.token_exchange.url,
                "client_id": config.token_exchange.client_id,
                "client_secret": config.token_exchange.client_secret,
            },
            "dss_instances": instances,
            "user_selections": config.user_selections,
        },
    )


def get_auth_settings() -> HTTPAuthConfig:
    """Return validated HTTP authentication settings."""
    return _load_config().auth


def get_token_exchange_settings() -> HTTPTokenExchangeConfig:
    """Return validated delegated-token exchange settings."""
    return _load_config().token_exchange


def get_server_settings() -> HTTPServerConfig:
    """Return validated Streamable HTTP transport settings."""
    return _load_config().server


def get_instances_and_selections() -> tuple[
    dict[str, DSSInstance], dict[str, dict[str, str]]
]:
    """Return the global HTTP catalog and persisted user selections."""
    config = _load_config()
    return config.dss_instances, config.user_selections


def set_user_selection(issuer: str, subject: str, instance_name: str) -> None:
    """Persist an authenticated user's selected catalog instance."""
    with _settings_lock:
        config = _load_config()
        if instance_name not in config.dss_instances:
            raise ValueError(f"Unknown HTTP instance '{instance_name}'.")
        config.user_selections.setdefault(issuer, {})[subject] = instance_name
        _save_config(config)
