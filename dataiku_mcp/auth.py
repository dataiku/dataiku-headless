"""Authentication and Dataiku client creation."""

import logging
from urllib.parse import urlparse

import dataikuapi
import requests
from dataikuapi.utils import DataikuException

from .config import http, request
from .executors import run_blocking

logger = logging.getLogger("dataiku-mcp")


def _require_instance_property(
    value: str,
    property_name: str,
    instance_name: str,
) -> None:
    """Require an active-instance property and provide actionable guidance."""
    if value:
        return

    alternative_instances = [
        name for name in request.get_instances() if name != instance_name
    ]
    message = (
        f"Dataiku instance '{instance_name}' has no {property_name}. Run "
        "configure_instance to update it."
    )
    if alternative_instances:
        message += (
            " Alternatively, run list_instances, then ask the user whether to "
            "switch to another configured instance."
        )
    raise ValueError(message)


def get_dss_client() -> dataikuapi.DSSClient:
    """Get a Dataiku API client for the currently active instance."""
    current_instance = request.get_pinned_instance()

    _require_instance_property(
        current_instance.url,
        "URL",
        current_instance.name,
    )

    if request.is_http_request():
        client = dataikuapi.DSSClient(
            current_instance.url,
            jwt_bearer_token=request.get_http_dss_token(),
        )
    else:
        _require_instance_property(
            current_instance.api_key,
            "API key",
            current_instance.name,
        )
        client = dataikuapi.DSSClient(current_instance.url, current_instance.api_key)
    client._session.verify = not current_instance.no_check_certificate
    return client


async def exchange_http_token(subject_token: str) -> str:
    """Exchange an MCP-audience token for the selected DSS-audience token."""

    def _exchange() -> str:
        auth_settings = http.get_auth_settings()
        instance = request.get_pinned_instance()
        if auth_settings.provider == "entra":
            token_endpoint = auth_settings.token_endpoint
            client_secret = auth_settings.client_secret
            data = {
                "client_id": auth_settings.client_id,
                "client_secret": client_secret,
                "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                "assertion": subject_token,
                "scope": instance.delegated_scope,
                "requested_token_use": "on_behalf_of",
            }
            client_auth = None
        else:
            delegation = auth_settings.delegation
            token_endpoint = delegation.token_endpoint
            client_secret = delegation.client_secret
            data = {
                "grant_type": "urn:ietf:params:oauth:grant-type:token-exchange",
                "subject_token": subject_token,
                "subject_token_type": "urn:ietf:params:oauth:token-type:access_token",
                "audience": instance.delegated_audience,
                "scope": instance.delegated_scope,
            }
            client_auth = (delegation.client_id, client_secret)
        try:
            response = requests.post(
                token_endpoint,
                data=data,
                auth=client_auth,
                timeout=10,
            )
            response.raise_for_status()
        except requests.RequestException as err:
            response = err.response
            details = {}
            if response is not None:
                try:
                    payload = response.json()
                except ValueError:
                    payload = {}
                if isinstance(payload, dict):
                    details = payload

            description = str(details.get("error_description", ""))
            for secret in (subject_token, client_secret):
                if secret:
                    description = description.replace(secret, "<redacted>")
            description = " ".join(description.split())[:500]
            logger.warning(
                "DSS token exchange failed: provider=%s instance=%s endpoint=%s "
                "status=%s exception=%s error=%s description=%s "
                "correlation_id=%s trace_id=%s",
                auth_settings.provider,
                instance.name,
                urlparse(token_endpoint).netloc,
                response.status_code if response is not None else None,
                type(err).__name__,
                details.get("error"),
                description or None,
                details.get("correlation_id"),
                details.get("trace_id"),
            )
            raise PermissionError("DSS token exchange failed.") from err

        try:
            payload = response.json()
        except ValueError as err:
            logger.warning(
                "DSS token exchange returned invalid JSON: provider=%s "
                "instance=%s status=%s content_type=%s",
                auth_settings.provider,
                instance.name,
                response.status_code,
                response.headers.get("content-type"),
            )
            raise PermissionError(
                "DSS token exchange returned an invalid response."
            ) from err
        if not isinstance(payload, dict):
            logger.warning(
                "DSS token exchange returned a non-object response: "
                "provider=%s instance=%s status=%s",
                auth_settings.provider,
                instance.name,
                response.status_code,
            )
            raise PermissionError("DSS token exchange returned an invalid response.")

        delegated_token = payload.get("access_token")
        if not isinstance(delegated_token, str) or not delegated_token:
            logger.warning(
                "DSS token exchange response contained no access token: "
                "provider=%s instance=%s status=%s error=%s",
                auth_settings.provider,
                instance.name,
                response.status_code,
                payload.get("error"),
            )
            raise PermissionError("DSS token exchange returned no access token.")
        return delegated_token

    return await run_blocking(_exchange)


async def require_admin() -> None:
    """Raise a concise error unless the configured credentials are an admin."""

    def _run():
        try:
            get_dss_client().get_general_settings()
        except DataikuException as err:
            raise PermissionError(
                "Dataiku administrator access could not be verified for this operation: "
                f"{err}"
            ) from None

    await run_blocking(_run)
