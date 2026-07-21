"""Authentication utilities for Dataiku client creation."""

import hashlib

import dataikuapi
from fastmcp.server.dependencies import get_http_request

from ... import config


def get_dss_client(
    instance: "config.DSSInstance | None" = None,
) -> dataikuapi.DSSClient:
    """Get a Dataiku API client using Dataiku-style env/config resolution.

    Pass ``instance`` to build a client for an already-captured instance
    snapshot. Callers that hand work to a worker/daemon thread must resolve the
    active instance and build the client *at tool entry* (in the request
    context) and thread it through, so an in-flight ``switch_instance`` cannot
    retarget the client and so HTTP bearer auth is read while the request
    ContextVars are still in scope.
    """
    client, _ = get_dss_client_and_principal(instance)
    return client


def get_dss_client_and_principal(
    instance: "config.DSSInstance | None" = None,
) -> tuple[dataikuapi.DSSClient, str]:
    """Return a DSS client and a non-secret identity for its effective API key.

    Cobuild conversation metadata can outlive one HTTP request. Binding it only
    to an instance/project would let a different bearer key reuse or approve a
    conversation if it learned the id. The fingerprint lets state-only paths
    compare the effective credential without retaining or returning that key.
    DSS API keys are high-entropy credentials; the domain separator prevents
    this digest from being confused with an unrelated raw SHA-256 use.
    """
    current_instance = instance if instance is not None else config.get_current_instance()
    api_key = _resolve_api_key(current_instance.api_key)
    dss_backend_url = _resolve_backend_url(current_instance.url)

    client = dataikuapi.DSSClient(dss_backend_url, api_key)
    client._session.verify = not current_instance.no_check_certificate
    principal = hashlib.sha256(
        b"dataiku-headless:dss-principal:v1\0" + api_key.encode("utf-8")
    ).hexdigest()
    return client, principal


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
