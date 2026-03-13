"""Auth resolution and DSSClient factory."""

from __future__ import annotations

import os

import dataikuapi

from dku_cli.auth import get_api_key
from dku_cli.config import get_active_profile, get_profile_config
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
        raise AuthError(
            "No DSS URL configured. Run 'dku auth login' or set DKU_URL."
        )
    if not resolved_key:
        raise AuthError(
            "No API key configured. Run 'dku auth login' or set DKU_API_KEY."
        )

    # Normalize URL
    resolved_url = resolved_url.rstrip("/")

    return resolved_url, resolved_key


def get_client(
    url: str | None = None,
    api_key: str | None = None,
    profile: str | None = None,
) -> dataikuapi.DSSClient:
    """Create an authenticated DSSClient."""
    resolved_url, resolved_key = resolve_auth(url, api_key, profile)
    return dataikuapi.DSSClient(resolved_url, api_key=resolved_key)
