"""Authentication utilities for Dataiku client creation."""

import dataikuapi

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

    raise ValueError(
        "No authentication key found. Set DKU_API_KEY or configure the selected "
        "instance's api_key in .dataiku/config.json."
    )


def _resolve_backend_url(backend_url) -> str:
    if backend_url:
        return backend_url

    raise ValueError(
        "No Dataiku URL found. Set DKU_DSS_URL or configure .dataiku/config.json."
    )
