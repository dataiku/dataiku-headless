# Copyright 2026 Dataiku SAS
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Authentication utilities for Dataiku client creation."""

import dataikuapi
from dataikuapi.utils import DataikuException

from ... import config
from .async_executor import run_blocking


def _require_instance_property(
    value: str,
    property_name: str,
    instance_name: str,
) -> None:
    """Require an active-instance property and provide actionable guidance."""
    if value:
        return

    alternative_instances = [
        name for name in config.get_instances() if name != instance_name
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


def get_current_instance_for_tool() -> config.DSSInstance:
    """Return the active instance or raise guidance suitable for an MCP agent."""
    try:
        return config.get_current_instance()
    except config.NoConfiguredInstancesError:
        raise ValueError(
            "No Dataiku instances are configured. Run configure_instance."
        ) from None
    except config.NoActiveInstanceError:
        raise ValueError(
            "No active Dataiku instance is selected. Run list_instances, then ask "
            "the user which configured instance to switch to, or whether to "
            "configure a new one."
        ) from None


def get_dss_client() -> dataikuapi.DSSClient:
    """Get a Dataiku API client for the currently active instance."""
    current_instance = get_current_instance_for_tool()

    _require_instance_property(
        current_instance.api_key,
        "API key",
        current_instance.name,
    )
    _require_instance_property(
        current_instance.url,
        "URL",
        current_instance.name,
    )

    client = dataikuapi.DSSClient(current_instance.url, current_instance.api_key)
    client._session.verify = not current_instance.no_check_certificate
    return client


def get_govern_client() -> dataikuapi.GovernClient:
    """Get a Govern API client from the environment or the active instance.

    `DKU_GOVERN_URL` and `DKU_GOVERN_API_KEY` win when set. Otherwise the
    active instance profile must carry a Govern URL and API key, entered
    through `configure_instance`.
    """
    connection = config.get_govern_connection_from_env()
    if connection is None:
        current_instance = get_current_instance_for_tool()
        connection = config.govern_connection_for_instance(current_instance)
        if not connection.url:
            raise ValueError(
                f"Dataiku instance '{current_instance.name}' has no Govern node "
                "configured. Set DKU_GOVERN_URL and DKU_GOVERN_API_KEY in the MCP "
                "server environment, or run configure_instance and fill the "
                "Govern node fields."
            )
    if not connection.api_key:
        source = (
            "DKU_GOVERN_API_KEY"
            if connection.source == "environment"
            else f"the Govern API key of instance '{connection.instance_name}'"
        )
        raise ValueError(
            f"The Govern node at {connection.url} has no API key. Set {source}."
        )

    client = dataikuapi.GovernClient(connection.url, connection.api_key)
    client._session.verify = not connection.no_check_certificate
    return client


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
