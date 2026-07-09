"""Authentication utilities for Dataiku client creation."""

import dataikuapi
from fastmcp.server.dependencies import get_http_request

from ... import config


def get_dss_client() -> dataikuapi.DSSClient:
    """Get a Dataiku API client using Dataiku-style env/config resolution."""
    current_instance = config.get_current_instance()
    api_key = _resolve_api_key(current_instance.api_key)
    dss_backend_url = _resolve_backend_url(current_instance.url)

    client = dataikuapi.DSSClient(dss_backend_url, api_key)
    client._session.verify = not current_instance.no_check_certificate
    return client


def _resolve_api_key(api_key) -> str:
    if api_key:
        return api_key

    api_key = _get_api_key_from_request_header()
    if api_key:
        return api_key

    raise ValueError(
        "No authentication key found. Set DKU_API_KEY, configure "
        ".dataiku/config.json, or provide Authorization: Bearer <DKU_API_KEY> "
        "for streamable-http requests."
    )


def _get_api_key_from_request_header() -> str:
    try:
        request = get_http_request()
    except Exception:  # in stdio mode
        return ""

    auth_header = request.headers.get("authorization", "").strip()
    if not auth_header:
        return ""

    parts = auth_header.split(maxsplit=1)
    if len(parts) != 2 or parts[0].lower() != "bearer" or not parts[1].strip():
        raise ValueError(
            "Invalid Authorization header format. Expected: Bearer <DKU_API_KEY>."
        )
    return parts[1].strip()


def _resolve_backend_url(backend_url) -> str:
    if backend_url:
        return backend_url

    raise ValueError(
        "No Dataiku URL found. Set DKU_DSS_URL or configure .dataiku/config.json."
    )
