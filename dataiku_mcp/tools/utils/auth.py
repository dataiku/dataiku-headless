"""Authentication utilities for Dataiku client creation."""

import dataikuapi
from dataikuapi.utils import DataikuException

from ... import config


def get_dss_client() -> dataikuapi.DSSClient:
    """Get a Dataiku API client using Dataiku-style env/config resolution."""
    current_instance = config.get_current_instance()
    api_key = _resolve_api_key(current_instance.api_key)
    dss_backend_url = _resolve_backend_url(current_instance.url)

    client = dataikuapi.DSSClient(dss_backend_url, api_key)
    client._session.verify = not current_instance.no_check_certificate
    return client


def require_admin(client: dataikuapi.DSSClient) -> None:
    """Raise a concise error unless the configured credentials are an admin."""
    try:
        client.get_general_settings()
    except DataikuException as err:
        raise PermissionError(
            "DSS administrator access could not be verified for this operation: "
            f"{err}"
        ) from None


def _resolve_api_key(api_key) -> str:
    if api_key:
        return api_key

    raise ValueError(
        "No authentication key found. Set DKU_API_KEY or configure "
        ".dataiku/config.json."
    )


def _resolve_backend_url(backend_url) -> str:
    if backend_url:
        return backend_url

    raise ValueError(
        "No Dataiku URL found. Set DKU_DSS_URL or configure .dataiku/config.json."
    )
