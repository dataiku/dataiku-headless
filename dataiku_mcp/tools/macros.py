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

"""Discover and execute installed Dataiku macros."""

import base64
import json

from ..auth import get_dss_client
from ..executors import run_blocking
from ..instance_policy import PROJECT_EXECUTION_POLICY, PROJECT_READ_POLICY
from ..server import mcp
from .utils.errors import safe_error_text
from .utils.serialization import columnar, compact_json
from .utils.validation import require_non_empty_string


def _status(state):
    return {
        **{
            k: state[k]
            for k in (
                "exists",
                "running",
                "empty",
                "type",
                "progress",
                "resultError",
                "storedError",
            )
            if k in state
        },
        "error_reported": bool(state.get("resultError") or state.get("storedError")),
    }


@mcp.tool(
    title="List Macros",
    meta=PROJECT_READ_POLICY,
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "openWorldHint": False,
    },
)
async def list_macros(project_key: str) -> str:
    """Find installed macros available in a project."""
    project_key = require_non_empty_string(project_key, "project_key")
    client = get_dss_client()
    items = await run_blocking(lambda: client.get_project(project_key).list_macros())
    return compact_json(
        {
            "macros": columnar(
                [
                    {
                        "macro_id": m.get("runnableType"),
                        "plugin_id": m.get("ownerPluginId"),
                        "label": m.get("meta", {}).get("label"),
                        "description": m.get("meta", {}).get("description"),
                        "result_type": m.get("resultType"),
                    }
                    for m in items
                ],
                ["macro_id", "plugin_id", "label", "description", "result_type"],
            )
        }
    )


@mcp.tool(
    title="Get Macro Definition",
    meta=PROJECT_READ_POLICY,
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "openWorldHint": False,
    },
)
async def get_macro_definition(project_key: str, macro_id: str) -> str:
    """Inspect a macro's parameters, permissions, and result type before running it."""
    project_key = require_non_empty_string(project_key, "project_key")
    macro_id = require_non_empty_string(macro_id, "macro_id")
    client = get_dss_client()
    raw = await run_blocking(
        lambda: client.get_project(project_key).get_macro(macro_id).get_definition()
    )
    return compact_json(
        {
            k: raw[k]
            for k in (
                "runnableType",
                "ownerPluginId",
                "meta",
                "longDescription",
                "params",
                "adminParams",
                "permissions",
                "requiresGlobalAdmin",
                "impersonate",
                "resultType",
                "resultLabel",
                "mimeType",
                "extension",
            )
            if k in raw
        }
    )


@mcp.tool(
    title="Run Macro",
    meta=PROJECT_EXECUTION_POLICY,
    annotations={
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
async def run_macro(
    project_key: str,
    macro_id: str,
    params: dict | None = None,
    admin_params: dict | None = None,
) -> str:
    """Start an installed macro, which may modify or delete data, and return its run ID."""
    project_key = require_non_empty_string(project_key, "project_key")
    macro_id = require_non_empty_string(macro_id, "macro_id")
    client = get_dss_client()
    try:
        run_id = await run_blocking(
            lambda: (
                client.get_project(project_key)
                .get_macro(macro_id)
                .run(
                    params=params,
                    admin_params=admin_params,
                    wait=False,
                )
            )
        )
    except Exception:
        raise RuntimeError(
            "Dataiku did not return a macro run ID. Check the macro in the UI "
            "before retrying: the request may have started a run."
        ) from None
    return compact_json(
        {
            "project_key": project_key,
            "macro_id": macro_id,
            "run_id": run_id,
            "status": "started",
        }
    )


@mcp.tool(
    title="Get Macro Status",
    meta=PROJECT_EXECUTION_POLICY,
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "openWorldHint": False,
    },
)
async def get_macro_status(project_key: str, macro_id: str, run_id: str) -> str:
    """Check a macro run without fetching its result or removing its run record."""
    project_key = require_non_empty_string(project_key, "project_key")
    macro_id = require_non_empty_string(macro_id, "macro_id")
    run_id = require_non_empty_string(run_id, "run_id")
    identity = {"project_key": project_key, "macro_id": macro_id, "run_id": run_id}
    client = get_dss_client()
    try:
        state = await run_blocking(
            lambda: (
                client.get_project(project_key).get_macro(macro_id).get_status(run_id)
            )
        )
    except Exception:
        raise RuntimeError(
            "Macro status lookup failed. Inspect the run in the Dataiku UI; do not restart the macro."
        ) from None
    return compact_json({**identity, "state": _status(state)})


@mcp.tool(
    title="Get Macro Result",
    meta=PROJECT_EXECUTION_POLICY,
    annotations={
        "readOnlyHint": False,
        "destructiveHint": True,
        "openWorldHint": False,
    },
)
async def get_macro_result(project_key: str, macro_id: str, run_id: str) -> str:
    """Fetch a completed macro's output; Dataiku removes the run record after retrieval."""
    project_key = require_non_empty_string(project_key, "project_key")
    macro_id = require_non_empty_string(macro_id, "macro_id")
    run_id = require_non_empty_string(run_id, "run_id")
    identity = {"project_key": project_key, "macro_id": macro_id, "run_id": run_id}
    client = get_dss_client()

    def _read():
        macro = client.get_project(project_key).get_macro(macro_id)
        state = macro.get_status(run_id)
        response = {**identity, "state": _status(state)}
        if (
            not state.get("exists")
            or state.get("running")
            or response["state"]["error_reported"]
        ):
            return response
        with macro.get_result(run_id) as stream:
            content = stream.read()
        if state.get("type") in ("RESULT_TABLE", "JSON_OBJECT"):
            try:
                content = json.loads(content)
                encoding = "json"
            except (ValueError, UnicodeError):
                content = base64.b64encode(content).decode("ascii")
                encoding = "base64"
        else:
            try:
                content = content.decode("utf-8")
                encoding = "utf-8"
            except UnicodeError:
                content = base64.b64encode(content).decode("ascii")
                encoding = "base64"
        return {
            **response,
            "result": content,
            "encoding": encoding,
            "run_consumed": True,
        }

    try:
        return compact_json(await run_blocking(_read))
    except Exception as exc:
        raise RuntimeError(
            f"Macro result retrieval failed: {safe_error_text(exc)}. "
            "Fetching a result may already have removed the run; do not restart the macro."
        ) from None


@mcp.tool(
    title="Abort Macro Run",
    meta=PROJECT_EXECUTION_POLICY,
    annotations={
        "readOnlyHint": False,
        "destructiveHint": True,
        "openWorldHint": False,
    },
)
async def abort_macro_run(project_key: str, macro_id: str, run_id: str) -> str:
    """Request cancellation of a macro run; earlier effects are not undone."""
    project_key = require_non_empty_string(project_key, "project_key")
    macro_id = require_non_empty_string(macro_id, "macro_id")
    run_id = require_non_empty_string(run_id, "run_id")
    identity = {"project_key": project_key, "macro_id": macro_id, "run_id": run_id}
    client = get_dss_client()
    try:
        await run_blocking(
            lambda: client.get_project(project_key).get_macro(macro_id).abort(run_id)
        )
    except Exception:
        raise RuntimeError(
            "Macro cancellation failed. Check its status before retrying."
        ) from None
    return compact_json({**identity, "status": "abort_requested"})
