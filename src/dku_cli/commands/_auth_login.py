from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit

import dataikuapi
import requests
import typer
from dataikuapi.utils import DataikuException
from rich.prompt import Prompt

from dku_cli.auth import infer_api_key_kind, store_api_key
from dku_cli.brand import print_logo, welcome
from dku_cli.config import set_default_project, set_profile_config
from dku_cli.output import error, info, render_raw, resolve_output_format, success, warn


def redact_url(url: str) -> str:
    parts = urlsplit(url)
    hostname = parts.hostname or ""
    netloc = hostname
    if parts.port:
        netloc = f"{hostname}:{parts.port}"
    return urlunsplit((parts.scheme, netloc, "", "", ""))


def login_impl(profile: str, url: str | None, api_key: str | None) -> None:
    interactive = not api_key
    url, api_key = _resolve_login_inputs(profile, url, api_key, interactive)
    client, user = _authenticate(url, api_key)
    version, node_type = _instance_metadata(client)
    set_profile_config(profile, url, node_type=node_type)
    storage = store_api_key(profile, api_key)
    credential_store, credential_warning = _credential_storage(storage)
    if _render_json_login(
        profile,
        url,
        user,
        version,
        node_type,
        api_key,
        credential_store,
        credential_warning,
    ):
        return
    _render_text_login(
        profile, url, user, version, node_type, api_key, storage, credential_warning
    )
    if interactive and node_type in (None, "DESIGN", "AUTOMATION"):
        _ask_default_project()


def _resolve_login_inputs(
    profile: str, url: str | None, api_key: str | None, interactive: bool
) -> tuple[str, str]:
    if interactive:
        print_logo(subtitle=f"dku auth login  —  profile: {profile}")
    if not url:
        url = Prompt.ask("DSS URL")
    url = url.rstrip("/")
    if not api_key:
        api_key = Prompt.ask("API Key", password=True)
    return url, api_key


def _authenticate(url: str, api_key: str):
    try:
        client = dataikuapi.DSSClient(url, api_key=api_key)
        auth_info = client.get_auth_info()
        user = auth_info.get("authIdentifier", "unknown")
    except (DataikuException, requests.RequestException) as e:
        error(f"Could not connect to {url}: {e}")
        raise typer.Exit(1)
    return client, user


def _instance_metadata(client) -> tuple[str, str | None]:
    version = "unknown"
    node_type: str | None = None
    try:
        raw = client.get_instance_info().raw
        version = raw.get("dssVersion", "unknown")
        node_type = (
            raw.get("nodeType") or raw.get("rawNodeType") or ""
        ).upper() or None
    except (DataikuException, requests.RequestException):
        pass
    return version, node_type


def _render_json_login(
    profile: str,
    url: str,
    user: str,
    version: str,
    node_type: str | None,
    api_key: str,
    credential_store: str,
    credential_warning: str,
) -> bool:
    if resolve_output_format() != "json":
        return False
    render_raw(
        {
            "profile": profile,
            "url": redact_url(url),
            "user": user,
            "dss_version": version,
            "node_type": node_type,
            "api_key_kind": infer_api_key_kind(api_key),
            "credential_store": credential_store,
            "credential_warning": credential_warning,
        },
        output_format="json",
    )
    return True


def _render_text_login(
    profile: str,
    url: str,
    user: str,
    version: str,
    node_type: str | None,
    api_key: str,
    storage: str,
    credential_warning: str,
) -> None:
    success(welcome(user, url, version))
    if node_type:
        info(f"Node type: {node_type}")
    info(f"API key kind: {infer_api_key_kind(api_key)}")
    if credential_warning:
        warn(credential_warning)
    info(f"Credentials stored in {storage}")
    if profile != "default":
        info(f'Profile "{profile}" is now active')


def _credential_storage(storage: str) -> tuple[str, str]:
    credential_store = "file" if storage.startswith("credentials file") else "keychain"
    if credential_store != "file":
        return credential_store, ""
    warning = "Stored in plaintext credentials file protected by mode 0600."
    if "Keychain error:" in storage:
        warning = f"{warning} {storage.partition('(')[2].rstrip(')')}"
    return credential_store, warning


def _ask_default_project() -> None:
    try:
        project_key = Prompt.ask("Default project? (leave blank to skip)", default="")
        if project_key.strip():
            set_default_project(project_key.strip())
            info(f"Default project set to {project_key.strip()}")
    except (EOFError, KeyboardInterrupt):
        pass
