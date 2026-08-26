"""Operator-managed Streamable HTTP configuration."""

import json
import os
import tempfile
import threading
from pathlib import Path

from .models import DSSInstance


DEFAULT_SETTINGS_PATH = Path.home() / ".dataiku-mcp" / "http.json"

_settings_path: Path | None = None
_settings_lock = threading.Lock()


def set_settings_path(path: Path | None) -> None:
    """Select the HTTP settings file for this server process."""
    global _settings_path
    _settings_path = path.expanduser() if path is not None else DEFAULT_SETTINGS_PATH


def get_settings_path() -> Path:
    """Return the single operator-managed HTTP settings file."""
    global _settings_path
    if _settings_path is None:
        _settings_path = DEFAULT_SETTINGS_PATH
    return _settings_path


def _load_document() -> dict:
    try:
        with open(get_settings_path()) as file:
            document = json.load(file)
    except FileNotFoundError as err:
        raise ValueError(
            f"HTTP instance configuration was not found at '{get_settings_path()}'."
        ) from err
    if not isinstance(document, dict):
        raise ValueError("HTTP instance configuration must be a JSON object.")
    return document


def _require_section(document: dict, name: str) -> dict:
    section = document.get(name)
    if not isinstance(section, dict):
        raise ValueError(f"HTTP settings requires an object named '{name}'.")
    return section


def _require_string(section: dict, section_name: str, key: str) -> str:
    value = section.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"HTTP settings requires '{section_name}.{key}'.")
    return value


def get_auth_settings() -> dict[str, str]:
    """Return validated OIDC and RFC 8693 settings."""
    document = _load_document()
    oidc = _require_section(document, "oidc")
    token_exchange = _require_section(document, "token_exchange")
    return {
        "issuer": _require_string(oidc, "oidc", "issuer"),
        "jwks_uri": _require_string(oidc, "oidc", "jwks_uri"),
        "audience": _require_string(oidc, "oidc", "audience"),
        "scope": _require_string(oidc, "oidc", "scope"),
        "token_exchange_url": _require_string(token_exchange, "token_exchange", "url"),
        "client_id": _require_string(token_exchange, "token_exchange", "client_id"),
        "client_secret": _require_string(
            token_exchange, "token_exchange", "client_secret"
        ),
    }


def get_server_settings() -> dict[str, str | int]:
    """Return validated Streamable HTTP transport settings."""
    server = _require_section(_load_document(), "server")
    host = _require_string(server, "server", "host")
    path = _require_string(server, "server", "path")
    port = server.get("port")
    if not isinstance(port, int):
        raise ValueError("HTTP settings requires integer 'server.port'.")
    return {"host": host, "port": port, "path": path}


def _instances_and_defaults(
    document: dict,
) -> tuple[dict[str, DSSInstance], dict[str, dict[str, str]]]:
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
            if not isinstance(subject, str) or not isinstance(instance_name, str):
                raise ValueError(
                    "HTTP user_defaults must map subjects to instance names."
                )
    return instances, defaults


def get_instances_and_defaults() -> tuple[
    dict[str, DSSInstance], dict[str, dict[str, str]]
]:
    """Return the global HTTP catalog and validated per-user defaults."""
    return _instances_and_defaults(_load_document())


def _save_document(document: dict) -> None:
    path = get_settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", dir=path.parent, prefix="config.", suffix=".tmp", delete=False
    ) as temp_file:
        json.dump(document, temp_file, indent=2)
        temp_file.write("\n")
        temp_path = Path(temp_file.name)
    temp_path.chmod(0o600)
    os.replace(temp_path, path)


def set_user_default(issuer: str, subject: str, instance_name: str) -> None:
    """Persist an authenticated user's selected catalog instance."""
    with _settings_lock:
        document = _load_document()
        instances, _ = _instances_and_defaults(document)
        if instance_name not in instances:
            raise ValueError(f"Unknown HTTP instance '{instance_name}'.")
        defaults = document.setdefault("user_defaults", {})
        if not isinstance(defaults, dict):
            raise ValueError(
                "HTTP instance configuration user_defaults must be an object."
            )
        issuer_defaults = defaults.setdefault(issuer, {})
        if not isinstance(issuer_defaults, dict):
            raise ValueError("HTTP user_defaults must map issuers to subject mappings.")
        issuer_defaults[subject] = instance_name
        _save_document(document)
