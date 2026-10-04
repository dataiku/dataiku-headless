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

"""Authentication and Dataiku client creation."""

import dataikuapi
from dataikuapi.utils import DataikuException

from .config import request
from .executors import run_blocking


def get_dss_client() -> dataikuapi.DSSClient:
    """Get a Dataiku API client for the currently active instance."""
    current_instance = request.get_pinned_instance()

    if current_instance.api_ticket is not None:
        client = dataikuapi.DSSClient(
            current_instance.url,
            internal_ticket=current_instance.api_ticket,
            extra_headers={"X-DKU-Client-Application": "dataiku-headless"},
        )
    else:
        client = dataikuapi.DSSClient(
            current_instance.url,
            api_key=current_instance.api_key,
            extra_headers={"X-DKU-Client-Application": "dataiku-headless"},
        )
    client._session.verify = (
        False
        if current_instance.no_check_certificate
        else current_instance.encrypted_rpc_cert_path or True
    )
    return client


def get_dataiku_version(client: dataikuapi.DSSClient) -> str:
    """Return the instance's Dataiku version, or an empty string if unavailable."""
    try:
        return client.get_instance_info().raw.get("dssVersion") or ""
    except Exception:
        # /instance-info is permission-gated. Version reporting should not make
        # get_current_instance fail for credentials that cannot read it.
        return ""


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
