"""Project exploration, listing, and limited creation tools."""

from fastmcp import Context

from .. import mcp
from .utils.async_executor import run_blocking
from .utils.auth import get_dss_client
from .utils.parsing import coerce_json_object as _coerce_json_object
from .utils.serialization import columnar, compact_json, omit_empty
from .utils.validation import (
    require_non_empty_string as _require_non_empty_string,
)

_CODE_ENV_MODES = {"INHERIT", "USE_BUILTIN_MODE", "EXPLICIT_ENV"}
_CONTAINER_MODES = {"INHERIT", "NONE", "EXPLICIT_CONTAINER"}
_SUPPORTED_PROJECT_SETTINGS = {
    "flowDisplaySettings.zonesGraphRenderingAlgorithm": {
        "DOT_OLDRANK",
        "DOT_NEWRANK_FREERANK",
    },
    "codeEnvs.python.mode": _CODE_ENV_MODES,
    "codeEnvs.r.mode": _CODE_ENV_MODES,
    "codeEnvs.python.envName": str,
    "codeEnvs.r.envName": str,
    "container.containerMode": _CONTAINER_MODES,
    "container.containerConf": str,
    "containerForVisualRecipesWorkloads.containerMode": _CONTAINER_MODES,
    "containerForVisualRecipesWorkloads.containerConf": str,
    **{
        path: bool
        for path in (
            "flowDisplaySettings.zonesGraphConnectZones",
            "flowDisplaySettings.zonesGraphForJobs",
            "flowDisplaySettings.respectTraversalOrder",
            "flowDisplaySettings.zonesManualPositioning",
            "flowDisplaySettings.showFlowZoneDescriptions",
            "flowBuildSettings.mergeSqlPipelines",
            "flowBuildSettings.pruneBeforeSqlPipelines",
            "flowBuildSettings.mergeSparkPipelines",
            "flowBuildSettings.pruneBeforeSparkPipelines",
            "flowBuildSettings.mergeCdePipelines",
            "flowBuildSettings.pruneBeforeCdePipelines",
            "codeEnvs.python.preventOverride",
            "codeEnvs.r.preventOverride",
        )
    },
}


def _leaf_items(value: dict, prefix: str = ""):
    for key, child in value.items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(child, dict):
            yield from _leaf_items(child, path)
        else:
            yield path, child


def _validate_project_settings_patch(patch: dict) -> None:
    items = list(_leaf_items(patch))
    if not items:
        raise ValueError("'settings_patch' must contain at least one setting")
    for path, value in items:
        rule = _SUPPORTED_PROJECT_SETTINGS.get(path)
        if rule is None:
            raise ValueError(f"Unsupported project setting: '{path}'")
        if value is None:
            continue
        if rule is bool and value is not True and value is not False:
            raise ValueError(f"'{path}' must be a boolean")
        if rule is str:
            _require_non_empty_string(value, path)
        elif isinstance(rule, set) and (
            not isinstance(value, str) or value not in rule
        ):
            raise ValueError(
                f"Invalid '{path}': {value!r}. Allowed values: {sorted(rule)}"
            )


def _apply_json_merge_patch(base: dict, patch: dict) -> dict:
    """Recursively apply a JSON Merge Patch, with null values removing keys."""
    merged = dict(base)
    for key, value in patch.items():
        if value is None:
            merged.pop(key, None)
        elif isinstance(value, dict):
            current = merged.get(key)
            merged[key] = _apply_json_merge_patch(
                current if isinstance(current, dict) else {}, value
            )
        else:
            merged[key] = value
    return merged


def _normalize_code_env_settings(settings: dict, patch: dict) -> None:
    """Keep code environment fields consistent with their selected mode."""
    code_envs_patch = patch.get("codeEnvs")
    if not isinstance(code_envs_patch, dict):
        return
    code_envs = settings.get("codeEnvs", {})
    for language in code_envs_patch:
        code_env = code_envs.get(language, {})
        mode = code_env.get("mode")
        if mode == "EXPLICIT_ENV":
            _require_non_empty_string(
                code_env.get("envName"), f"codeEnvs.{language}.envName"
            )
            code_env["useBuiltinEnv"] = False
        elif mode == "USE_BUILTIN_MODE":
            code_env["useBuiltinEnv"] = True
            code_env.pop("envName", None)
        elif mode == "INHERIT":
            code_env["useBuiltinEnv"] = False
            code_env.pop("envName", None)


@mcp.tool()
async def count_projects(ctx: Context) -> str:
    """Count projects on the Dataiku instance without listing project metadata."""
    await ctx.info("Counting Dataiku projects...")
    project_keys = await run_blocking(lambda: get_dss_client().list_project_keys())
    return compact_json({"project_count": len(project_keys)})


@mcp.tool()
async def list_projects(ctx: Context, search: str = "") -> str:
    """List projects with ownership, description, and last-modified context."""
    await ctx.info("Listing Dataiku projects...")
    raw_projects = await run_blocking(lambda: get_dss_client().list_projects())
    projects = [
        {
            "projectKey": project["projectKey"],
            "name": project.get("name", ""),
            "ownerLogin": project.get("ownerLogin", ""),
            "ownerDisplayName": project.get("ownerDisplayName", ""),
            "shortDesc": project.get("shortDesc", ""),
            "lastModifiedOn": project.get("versionTag", {}).get("lastModifiedOn"),
            "lastModifiedBy": project.get("versionTag", {})
            .get("lastModifiedBy", {})
            .get("login", ""),
        }
        for project in raw_projects
    ]
    if search:
        q = search.lower()
        projects = [
            project
            for project in projects
            if q in project["projectKey"].lower()
            or q in project["name"].lower()
            or q in project["ownerLogin"].lower()
            or q in project["ownerDisplayName"].lower()
            or q in project["shortDesc"].lower()
        ]
    return compact_json(
        {
            "projects": columnar(
                projects,
                [
                    "projectKey",
                    "name",
                    "ownerLogin",
                    "ownerDisplayName",
                    "shortDesc",
                    "lastModifiedOn",
                    "lastModifiedBy",
                ],
            )
        }
    )


@mcp.tool()
async def create_project(
    project_key: str,
    name: str,
    ctx: Context,
    short_desc: str = "",
    folder_id: str = "",
) -> str:
    """Create a new project on the Dataiku instance."""
    project_key = _require_non_empty_string(project_key, "project_key")
    name = _require_non_empty_string(name, "name")
    await ctx.info(f"Creating project '{project_key}'...")

    def _run():
        client = get_dss_client()
        auth_info = client.get_auth_info()
        owner = auth_info.get("authIdentifier", "")
        normalized_folder_id = folder_id.strip()
        if not normalized_folder_id:
            client.create_project(
                project_key, name, owner=owner, description=short_desc
            )
            return omit_empty({"projectKey": project_key, "name": name, "owner": owner})

        folder = client.get_project_folder(
            _require_non_empty_string(normalized_folder_id, "folder_id")
        )
        folder.create_project(project_key, name, owner)
        project = client.get_project(project_key)
        metadata = project.get_metadata()
        if short_desc:
            metadata["shortDesc"] = short_desc
            project.set_metadata(metadata)
        return omit_empty(
            {
                "projectKey": project_key,
                "name": name,
                "owner": owner,
                "folder_id": folder.id,
                "folder_path": folder.get_path(),
            }
        )

    return compact_json(await run_blocking(_run))


@mcp.tool()
async def get_project_metadata(project_key: str, ctx: Context) -> str:
    """Get project metadata: label, descriptions, tags, and checklists."""
    project_key = _require_non_empty_string(project_key, "project_key")
    await ctx.info(f"Fetching metadata for project {project_key}...")
    metadata = await run_blocking(
        lambda: get_dss_client().get_project(project_key).get_metadata()
    )
    return compact_json(metadata)


@mcp.tool()
async def get_project_variables(project_key: str, ctx: Context) -> str:
    """Get the project variables as {'standard': {...}, 'local': {...}}."""
    project_key = _require_non_empty_string(project_key, "project_key")
    await ctx.info(f"Fetching variables for project {project_key}...")
    variables = await run_blocking(
        lambda: get_dss_client().get_project(project_key).get_variables()
    )
    return compact_json(variables)


@mcp.tool()
async def get_project_settings(project_key: str, ctx: Context) -> str:
    """Get the project's editable settings."""
    project_key = _require_non_empty_string(project_key, "project_key")
    await ctx.info(f"Fetching settings for project {project_key}...")

    def _run():
        raw = get_dss_client().get_project(project_key).get_settings().get_raw()
        return raw["settings"]

    return compact_json(await run_blocking(_run))


@mcp.tool()
async def update_project_settings(
    project_key: str,
    settings_patch: dict | str,
    ctx: Context,
) -> str:
    """Merge supported fields into the project's editable settings.

    Nested objects are merged, scalar values are replaced, and null values remove
    fields. Undocumented fields are rejected. Use get_project_settings first to
    inspect the current values.
    """
    project_key = _require_non_empty_string(project_key, "project_key")
    patch = _coerce_json_object(settings_patch, "settings_patch")
    if not patch:
        raise ValueError("'settings_patch' must not be empty")
    _validate_project_settings_patch(patch)
    await ctx.info(f"Updating settings for project {project_key}...")

    def _run():
        project = get_dss_client().get_project(project_key)
        settings = project.get_settings()
        raw = settings.get_raw()
        raw["settings"] = _apply_json_merge_patch(raw["settings"], patch)
        _normalize_code_env_settings(raw["settings"], patch)
        settings.save()
        return project.get_settings().get_raw()["settings"]

    return compact_json(await run_blocking(_run))


@mcp.tool()
async def set_project_variables(
    project_key: str,
    variables: dict | str,
    ctx: Context,
) -> str:
    """Set the project variables.

    Args:
        variables: A modified version of the object returned by get_project_variables
    """
    project_key = _require_non_empty_string(project_key, "project_key")
    variables_obj = _coerce_json_object(variables, "variables")
    await ctx.info(f"Updating variables for project {project_key}...")

    def _run():
        get_dss_client().get_project(project_key).set_variables(variables_obj)

    await run_blocking(_run)
    return compact_json({"project_key": project_key})
