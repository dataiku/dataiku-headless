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

"""Container execution placement for existing project objects."""

from __future__ import annotations

from typing import Annotated, Literal, get_args

from fastmcp import Context
from pydantic import Field

from .. import mcp
from .machine_learning.shared.common import require_single_ml_task
from .utils.async_executor import run_blocking
from .utils.auth import get_dss_client
from .utils.serialization import compact_json
from .utils.validation import require_allowed_value, require_non_empty_string

ContainerMode = Literal["INHERIT", "NONE", "EXPLICIT_CONTAINER"]
ObjectType = Literal[
    "recipe", "ml_task", "saved_model", "webapp", "knowledge_bank", "agent_tool"
]
ObjectId = Annotated[
    str,
    Field(
        description=(
            "Recipe name for 'recipe'; the id of an analysis holding a single ML task "
            "for 'ml_task'; the object's id otherwise."
        )
    ),
]
ContainerConfig = Annotated[
    str | None,
    Field(
        description=(
            "Configuration name from list_container_exec_configs, copied exactly; "
            "only with container_mode='EXPLICIT_CONTAINER'."
        )
    ),
]
_CONTAINER_MODES = set(get_args(ContainerMode))
_CONTAINER_OBJECT_TYPES = set(get_args(ObjectType))


def _resolve_handle(project, object_type: str, object_id: str) -> tuple:
    """Return the settings-bearing handle for one object, plus identity extras.

    Identifier resolution happens once per operation, so re-reading the saved
    settings costs one settings fetch rather than repeating the lookup that
    found the object.
    """
    if object_type == "recipe":
        return project.get_recipe(object_id), {}
    if object_type == "ml_task":
        analysis = project.get_analysis(object_id)
        mltask_id = require_single_ml_task(analysis)["mlTaskId"]
        return analysis.get_ml_task(mltask_id), {"mltask_id": mltask_id}
    if object_type == "saved_model":
        return project.get_saved_model(object_id), {}
    if object_type == "webapp":
        return project.get_webapp(object_id), {}
    if object_type == "knowledge_bank":
        return project.get_knowledge_bank(object_id), {}
    if object_type == "agent_tool":
        return project.get_agent_tool(object_id), {}


def _require_selection(selection, label: str) -> dict:
    if not isinstance(selection, dict):
        raise ValueError(f"This {label} does not expose a container execution override")
    return selection


def _recipe_selection(settings) -> dict:
    """Return the one container selection a recipe exposes.

    Dataiku stores it in a different place per recipe family, so collect every
    candidate and refuse an ambiguous recipe rather than writing to a location
    Dataiku may not read. A recipe whose payload is code rather than JSON
    raises on the payload read and simply contributes no candidate.
    """
    candidates: dict[str, dict] = {}
    params = settings.get_recipe_params() or {}
    try:
        payload = settings.get_json_payload() or {}
    except Exception:
        payload = {}

    for location, selection in (
        ("params.containerSelection", params.get("containerSelection")),
        (
            "params.engineParams.containerSelection",
            (params.get("engineParams") or {}).get("containerSelection"),
        ),
        (
            "payload.engineParams.containerSelection",
            (payload.get("engineParams") or {}).get("containerSelection"),
        ),
    ):
        if isinstance(selection, dict):
            candidates[location] = selection

    if len(candidates) > 1:
        raise ValueError(
            "This recipe exposes a container execution override in several places "
            f"({', '.join(candidates)}); refusing to guess which one Dataiku reads"
        )
    selection = next(iter(candidates.values()), None)
    return _require_selection(selection, "recipe")


def _locate_selection(object_type: str, settings) -> dict:
    """Return the live container selection inside ``settings``.

    The selection is a reference into the settings, so mutating it and calling
    ``settings.save()`` writes back only the container placement.
    """
    if object_type == "recipe":
        return _recipe_selection(settings)

    raw = settings.get_raw()
    if object_type == "ml_task":
        return _require_selection(raw.get("containerSelection"), "ML task")
    if object_type == "saved_model":
        mini_task = raw.get("miniTask") or {}
        return _require_selection(mini_task.get("containerSelection"), "saved model")
    if object_type == "webapp":
        infra = (raw.get("params") or {}).get("infra") or {}
        return _require_selection(infra.get("containerSelection"), "WebApp")
    if object_type == "knowledge_bank":
        return _require_selection(raw.get("containerExecSelection"), "Knowledge Bank")
    if object_type == "agent_tool":
        params = raw.get("params") or {}
        return _require_selection(params.get("containerExecSelection"), "agent tool")


def _apply_selection(
    selection: dict, container_mode: str, container_config: str | None
) -> None:
    selection["containerMode"] = container_mode
    if container_mode == "EXPLICIT_CONTAINER":
        selection["containerConf"] = container_config
    else:
        selection.pop("containerConf", None)


@mcp.tool(
    title="Set Container Execution Config",
    annotations={
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def set_container_exec_config(
    project_key: str,
    object_type: ObjectType,
    object_id: ObjectId,
    container_mode: ContainerMode,
    ctx: Context,
    container_config: ContainerConfig = None,
) -> str:
    """Set which container one existing object runs in, changing placement only."""
    project_key = require_non_empty_string(project_key, "project_key")
    object_type = require_allowed_value(
        object_type, "object_type", _CONTAINER_OBJECT_TYPES
    )
    object_id = require_non_empty_string(object_id, "object_id")
    container_mode = require_allowed_value(
        container_mode, "container_mode", _CONTAINER_MODES
    )
    if container_mode == "EXPLICIT_CONTAINER":
        container_config = require_non_empty_string(
            container_config, "container_config"
        )
    elif container_config is not None:
        raise ValueError(
            "'container_config' is only valid with container_mode='EXPLICIT_CONTAINER'"
        )
    await ctx.info(
        f"Setting container execution for {object_type} '{object_id}' in {project_key}..."
    )

    def _run():
        project = get_dss_client().get_project(project_key)
        handle, identity = _resolve_handle(project, object_type, object_id)
        settings = handle.get_settings()
        _apply_selection(
            _locate_selection(object_type, settings), container_mode, container_config
        )
        settings.save()
        return {
            "project_key": project_key,
            "object_type": object_type,
            "object_id": object_id,
            **identity,
            "container_selection": _locate_selection(
                object_type, handle.get_settings()
            ),
        }

    return compact_json(await run_blocking(_run))
