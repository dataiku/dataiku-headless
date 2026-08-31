"""Authentication and Dataiku client creation."""

import dataikuapi
import requests
from dataikuapi.utils import DataikuException

from .config import http, request
from .config.models import (
    DSSInstance,
    NoActiveInstanceError,
    NoConfiguredInstancesError,
)
from .executors import run_blocking


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


def get_current_instance_for_tool() -> DSSInstance:
    """Return the active instance or raise guidance suitable for an MCP agent."""
    try:
        return request.get_pinned_instance()
    except NoConfiguredInstancesError:
        if request.is_http_request():
            raise ValueError(
                "No platform-managed Dataiku instances are configured."
            ) from None
        raise ValueError(
            "No Dataiku instances are configured. Run configure_instance."
        ) from None
    except NoActiveInstanceError:
        if request.is_http_request():
            raise ValueError(
                "No active Dataiku instance is selected. Run list_instances, then "
                "switch_instance to choose a platform-managed instance."
            ) from None
        raise ValueError(
            "No active Dataiku instance is selected. Run list_instances, then ask "
            "the user which configured instance to switch to, or whether to "
            "configure a new one."
        ) from None


def get_dss_client() -> dataikuapi.DSSClient:
    """Get a Dataiku API client for the currently active instance."""
    current_instance = get_current_instance_for_tool()

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


async def exchange_http_token(mcp_token: str) -> str:
    """Exchange an MCP-audience token for the selected DSS-audience token."""

    def _exchange() -> str:
        settings = http.get_auth_settings()
        instance = get_current_instance_for_tool()
        try:
            response = requests.post(
                settings["token_exchange_url"],
                data={
                    "grant_type": "urn:ietf:params:oauth:grant-type:token-exchange",
                    "subject_token": mcp_token,
                    "subject_token_type": "urn:ietf:params:oauth:token-type:access_token",
                    "audience": instance.jwt_audience,
                    "scope": instance.jwt_scope,
                },
                auth=(settings["client_id"], settings["client_secret"]),
                timeout=10,
            )
            response.raise_for_status()
            delegated_token = response.json().get("access_token")
        except requests.RequestException as err:
            raise PermissionError("DSS token exchange failed.") from err
        except ValueError as err:
            raise PermissionError(
                "DSS token exchange returned an invalid response."
            ) from err
        if not isinstance(delegated_token, str) or not delegated_token:
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
