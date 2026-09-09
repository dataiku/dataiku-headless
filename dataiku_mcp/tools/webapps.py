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

"""WebApp inspection tools for Dataiku."""

import copy

from fastmcp import Context

from .. import mcp
from .utils.async_executor import run_blocking
from .utils.auth import get_dss_client
from .utils.serialization import columnar, compact_json, omit_empty
from .utils.validation import require_non_empty_string as _require_non_empty_string

WEBAPP_SECRET_REDACTION = "__DATAIKU_REDACTED__"
_PRESERVED_SENSITIVE_KEYS = {"apiKey"}


def _redact_webapp_settings(raw_settings: dict) -> dict:
    redacted = copy.deepcopy(raw_settings)
    for key in _PRESERVED_SENSITIVE_KEYS:
        if key in redacted:
            redacted[key] = WEBAPP_SECRET_REDACTION
    return redacted


def _serialize_webapp_list_item(item: dict) -> dict:
    created_by = item.get("createdBy") or {}
    modified_by = item.get("lastModifiedBy") or {}
    return {
        "id": item.get("id"),
        "name": item.get("name"),
        "type": item.get("type"),
        "backend_running": item.get("backendRunning", False),
        "tags": item.get("tags", []),
        "created_on": item.get("createdOn"),
        "created_by": created_by.get("login"),
        "last_modified_on": item.get("lastModifiedOn"),
        "last_modified_by": modified_by.get("login"),
    }


@mcp.tool(
    title="List Webapps",
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "openWorldHint": False,
    },
)
async def list_webapps(project_key: str, ctx: Context) -> str:
    """Find a project's webapps, their types, and whether each backend is running."""
    project_key = _require_non_empty_string(project_key, "project_key")
    await ctx.info(f"Listing WebApps in {project_key}...")

    items = await run_blocking(
        lambda: get_dss_client().get_project(project_key).list_webapps()
    )
    webapps = [_serialize_webapp_list_item(dict(item)) for item in items]
    return compact_json(
        {
            "webapps": columnar(
                webapps,
                [
                    "id",
                    "name",
                    "type",
                    "backend_running",
                    "tags",
                    "created_on",
                    "created_by",
                    "last_modified_on",
                    "last_modified_by",
                ],
            )
        }
    )


@mcp.tool(
    title="Get Webapp Settings",
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "openWorldHint": False,
    },
)
async def get_webapp_settings(
    project_key: str,
    webapp_id: str,
    ctx: Context,
) -> str:
    """Read one webapp's definition and code, with sensitive fields redacted."""
    project_key = _require_non_empty_string(project_key, "project_key")
    webapp_id = _require_non_empty_string(webapp_id, "webapp_id")
    await ctx.info(f"Loading settings for WebApp {webapp_id} in {project_key}...")

    raw = await run_blocking(
        lambda: (
            get_dss_client()
            .get_project(project_key)
            .get_webapp(webapp_id)
            .get_settings()
            .get_raw()
        )
    )
    return compact_json(_redact_webapp_settings(raw))


@mcp.tool(
    title="Get Webapp State",
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "openWorldHint": False,
    },
)
async def get_webapp_state(
    project_key: str,
    webapp_id: str,
    ctx: Context,
) -> str:
    """Check a webapp backend's running state and recent log output."""
    project_key = _require_non_empty_string(project_key, "project_key")
    webapp_id = _require_non_empty_string(webapp_id, "webapp_id")
    await ctx.info(f"Loading backend state for WebApp {webapp_id} in {project_key}...")

    def _run():
        webapp = get_dss_client().get_project(project_key).get_webapp(webapp_id)
        state = webapp.get_state()
        return omit_empty({"backend_running": state.running, "state": state.state})

    return compact_json(await run_blocking(_run))
