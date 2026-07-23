"""Authentication utilities for Dataiku client creation."""

import dataikuapi

from ... import config


def get_dss_client() -> dataikuapi.DSSClient:
    """Get a Dataiku API client using Dataiku-style env/config resolution."""
    current_instance = config.get_current_instance()
    api_key = _resolve_api_key(current_instance.api_key, current_instance.name)
    dss_backend_url = _resolve_backend_url(current_instance.url, current_instance.name)

    client = dataikuapi.DSSClient(dss_backend_url, api_key)
    client._session.verify = not current_instance.no_check_certificate
    return client


def _resolve_api_key(api_key: str, instance_name: str) -> str:
    if api_key:
        return api_key

    raise ValueError(
        f"No API key for Dataiku instance '{instance_name}'. Set one by running "
        "the configure_instance tool, by setting DKU_API_KEY, or by adding an "
        '"api_key" to this instance in ~/.dataiku/config.json. '
        "Create an API key in Dataiku under Profile & Settings > API keys."
    )


def _resolve_backend_url(backend_url: str, instance_name: str) -> str:
    if backend_url:
        return backend_url

    raise ValueError(
        f"No URL for Dataiku instance '{instance_name}'. Set one by running the "
        "configure_instance tool, by setting DKU_DSS_URL, or by adding a "
        '"url" to this instance in ~/.dataiku/config.json '
        "(e.g. https://your-instance.dataiku.com)."
    )
