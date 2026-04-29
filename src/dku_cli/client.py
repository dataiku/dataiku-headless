"""Auth resolution and DSSClient / GovernClient factories."""

from __future__ import annotations

import os

import dataikuapi

from dku_cli.auth import get_api_key
from dku_cli.config import (
    get_active_profile,
    get_profile_config,
    get_profile_node_type,
)
from dku_cli.errors import AuthError


def resolve_auth(
    url: str | None = None,
    api_key: str | None = None,
    profile: str | None = None,
) -> tuple[str, str]:
    """Resolve DSS URL and API key from flags > env > config.

    Returns (url, api_key).
    Raises AuthError if credentials cannot be resolved.
    """
    # 1. CLI flags
    resolved_url = url
    resolved_key = api_key

    # 2. Environment variables
    if not resolved_url:
        resolved_url = os.environ.get("DKU_URL")
    if not resolved_key:
        resolved_key = os.environ.get("DKU_API_KEY")

    # 3. Profile-based config
    if not resolved_url or not resolved_key:
        active = profile or get_active_profile()
        profile_cfg = get_profile_config(active)
        if not resolved_url:
            resolved_url = profile_cfg.get("url")
        if not resolved_key:
            resolved_key = get_api_key(active)

    if not resolved_url:
        raise AuthError("No DSS URL configured. Run 'dku auth login' or set DKU_URL.")
    if not resolved_key:
        raise AuthError(
            "No API key configured. Run 'dku auth login' or set DKU_API_KEY."
        )

    # Normalize URL
    resolved_url = resolved_url.rstrip("/")

    return resolved_url, resolved_key


def resolve_node_type(profile: str | None = None) -> str | None:
    """Return the stored node type for the active (or given) profile.

    Returns one of: 'DESIGN', 'AUTOMATION', 'GOVERN', 'DEPLOYER', 'API', or None
    if not stored (legacy profile from before node-type was tracked).
    """
    active = profile or get_active_profile()
    nt = get_profile_node_type(active)
    if nt:
        return nt.upper()
    return None


def get_client(
    url: str | None = None,
    api_key: str | None = None,
    profile: str | None = None,
) -> dataikuapi.DSSClient:
    """Create an authenticated DSSClient."""
    resolved_url, resolved_key = resolve_auth(url, api_key, profile)
    return dataikuapi.DSSClient(resolved_url, api_key=resolved_key)


def get_govern_client(
    url: str | None = None,
    api_key: str | None = None,
    profile: str | None = None,
):
    """Create an authenticated GovernClient. Used by ``dku govern`` commands."""
    resolved_url, resolved_key = resolve_auth(url, api_key, profile)
    return dataikuapi.GovernClient(resolved_url, api_key=resolved_key)


def probe_node_type(url: str, api_key: str) -> str | None:
    """Call get_instance_info() and return the node type.

    Works for both DESIGN/AUTOMATION/DEPLOYER/API nodes (via DSSClient) and
    GOVERN nodes (via GovernClient). We try DSSClient first because
    get_instance_info() works on every node type — GovernClient also works but
    fails for non-govern auth edge cases. Returns None if both probes fail.
    """
    # DSSClient.get_instance_info() succeeds against any node the API key
    # is valid on, including GOVERN (the endpoint /instance-info is shared).
    try:
        c = dataikuapi.DSSClient(url.rstrip("/"), api_key=api_key)
        info = c.get_instance_info().raw
        nt = info.get("nodeType") or info.get("rawNodeType")
        if nt:
            return nt.upper()
    except Exception:
        pass
    try:
        c = dataikuapi.GovernClient(url.rstrip("/"), api_key=api_key)
        info = c.get_instance_info().raw
        nt = info.get("nodeType") or info.get("rawNodeType")
        if nt:
            return nt.upper()
    except Exception:
        pass
    return None
