"""DSS Design-node code environment administration tools."""

from typing import Literal

from fastmcp import Context
from pydantic import BaseModel

from .. import mcp
from .utils.async_executor import run_blocking
from .utils.auth import get_dss_client
from .utils.serialization import columnar, compact_json
from .utils.validation import (
    require_allowed_value as _require_allowed_value,
    require_non_empty_string as _require_non_empty_string,
    require_non_negative_int as _require_non_negative_int,
    require_positive_int as _require_positive_int,
)

_LANGUAGES = {"PYTHON", "R"}
_SEARCH_MODES = {"partial", "exact"}
_SUMMARY_COLUMNS = ["name", "language", "deployment_mode"]
_DETAIL_COLUMNS = [
    *_SUMMARY_COLUMNS,
    "owner",
    "usable_by_all",
    "group_permissions",
    "python_interpreter",
    "requested_packages",
    "actual_packages",
    "all_container_configurations",
    "container_configurations",
    "all_spark_kubernetes_configurations",
    "spark_kubernetes_configurations",
    "usages",
]


class CodeEnvGroupPermission(BaseModel):
    """One DSS group's access to a code environment."""

    group: str
    use: bool
    update: bool
    manage_users: bool


def _language(value: str) -> str:
    return _require_allowed_value(
        _require_non_empty_string(value, "language"), "language", _LANGUAGES
    )


def _list_entry(raw: dict) -> dict:
    return {
        "name": raw.get("envName") or raw.get("name", ""),
        "language": raw.get("envLang") or raw.get("language", ""),
        "deployment_mode": raw.get("deploymentMode") or raw.get("type", ""),
    }


def _split_lines(value: str | None) -> list[str]:
    return value.splitlines() if value else []


def _serialize_details(raw: dict, summary: dict) -> dict:
    desc = raw.get("desc") or {}
    permissions = raw.get("permissions", desc.get("permissions", [])) or []
    return {
        **summary,
        "owner": desc.get("owner", raw.get("owner", "")),
        "usable_by_all": raw.get("usableByAll", desc.get("usableByAll", False)),
        "group_permissions": [
            {
                "group": permission.get("group", ""),
                "use": permission.get("use", False),
                "update": permission.get("update", False),
                "manage_users": permission.get("manageUsers", False),
            }
            for permission in permissions
        ],
        "python_interpreter": desc.get("pythonInterpreter"),
        "requested_packages": _split_lines(raw.get("specPackageList")),
        "actual_packages": _split_lines(raw.get("actualPackageList")),
        "all_container_configurations": raw.get(
            "allContainerConfs", desc.get("allContainerConfs", False)
        ),
        "container_configurations": raw.get(
            "containerConfs", desc.get("containerConfs", [])
        ),
        "all_spark_kubernetes_configurations": raw.get(
            "allSparkKubernetesConfs", desc.get("allSparkKubernetesConfs", False)
        ),
        "spark_kubernetes_configurations": raw.get(
            "sparkKubernetesConfs", desc.get("sparkKubernetesConfs", [])
        ),
    }


def _apply_build_targets(
    settings,
    *,
    all_container_configurations: bool | None,
    container_configurations: list[str] | None,
    all_spark_kubernetes_configurations: bool | None,
    spark_kubernetes_configurations: list[str] | None,
) -> bool:
    changed = False
    raw = settings.get_raw()
    if (
        all_container_configurations is not None
        or container_configurations is not None
    ):
        if all_container_configurations is True and container_configurations:
            raise ValueError(
                "Cannot provide container_configurations when "
                "all_container_configurations is true"
            )
        settings.set_built_container_confs(
            *(container_configurations or raw.get("containerConfs", [])),
            all=(
                all_container_configurations
                if all_container_configurations is not None
                else raw.get("allContainerConfs", False)
            ),
        )
        changed = True
    if (
        all_spark_kubernetes_configurations is not None
        or spark_kubernetes_configurations is not None
    ):
        if all_spark_kubernetes_configurations is True and spark_kubernetes_configurations:
            raise ValueError(
                "Cannot provide spark_kubernetes_configurations when "
                "all_spark_kubernetes_configurations is true"
            )
        settings.set_built_spark_kubernetes_confs(
            *(spark_kubernetes_configurations or raw.get("sparkKubernetesConfs", [])),
            all=(
                all_spark_kubernetes_configurations
                if all_spark_kubernetes_configurations is not None
                else raw.get("allSparkKubernetesConfs", False)
            ),
        )
        changed = True
    return changed


def _apply_changes(
    settings,
    *,
    owner: str | None,
    usable_by_all: bool | None,
    group_permissions: list[CodeEnvGroupPermission] | None,
    requested_packages: list[str] | None,
    python_interpreter: str | None,
    all_container_configurations: bool | None,
    container_configurations: list[str] | None,
    all_spark_kubernetes_configurations: bool | None,
    spark_kubernetes_configurations: list[str] | None,
    baseline: bool = False,
) -> bool:
    raw = settings.get_raw()
    desc = raw.setdefault("desc", {})
    changed = False
    if baseline:
        desc["installCorePackages"] = True
        desc["installJupyterSupport"] = True
        changed = True
    if owner is not None:
        desc["owner"] = owner
        changed = True
    if usable_by_all is not None:
        raw["usableByAll"] = usable_by_all
        changed = True
    if group_permissions is not None:
        raw["permissions"] = [
            {
                "group": permission.group,
                "use": permission.use,
                "update": permission.update,
                "manageUsers": permission.manage_users,
            }
            for permission in group_permissions
        ]
        changed = True
    if requested_packages is not None:
        settings.set_required_packages(*requested_packages)
        changed = True
    if python_interpreter is not None:
        desc["pythonInterpreter"] = python_interpreter
        changed = True
    return _apply_build_targets(
        settings,
        all_container_configurations=all_container_configurations,
        container_configurations=container_configurations,
        all_spark_kubernetes_configurations=all_spark_kubernetes_configurations,
        spark_kubernetes_configurations=spark_kubernetes_configurations,
    ) or changed


@mcp.tool()
async def list_code_envs(
    ctx: Context,
    search: str = "",
    search_mode: Literal["partial", "exact"] = "partial",
    language: str | None = None,
    include_details: bool = False,
    include_usages: bool = False,
    offset: int = 0,
    limit: int = 5,
) -> str:
    """List DSS code environments with optional precise detail and usage enrichment.

    ``search_mode="exact"`` is the precise read path for one environment.
    ``include_details`` requires global Create code envs or Manage all code envs
    permission. ``include_usages`` implies details and is allowed only when the
    complete filtered result has at most five environments.
    """
    search = search.strip()
    search_mode = _require_allowed_value(search_mode, "search_mode", _SEARCH_MODES)
    if search_mode == "exact" and not search:
        raise ValueError("'search' must be non-empty when search_mode is 'exact'")
    if language is not None:
        language = _language(language)
    offset = _require_non_negative_int(offset, "offset")
    limit = min(_require_positive_int(limit, "limit"), 10)
    include_details = include_details or include_usages
    await ctx.info("Listing DSS code environments...")

    def _run():
        client = get_dss_client()
        all_envs = [_list_entry(raw) for raw in client.list_code_envs()]
        matched = all_envs
        if search:
            if search_mode == "exact":
                matched = [env for env in matched if env["name"] == search]
            else:
                query = search.casefold()
                matched = [
                    env for env in matched if query in env["name"].casefold()
                ]
        if language is not None:
            matched = [env for env in matched if env["language"] == language]
        matched.sort(key=lambda env: (env["name"].casefold(), env["name"]))
        if include_usages and len(matched) > 5:
            raise ValueError(
                "include_usages requires at most five matching code environments; "
                "narrow search or language"
            )
        page = matched[offset : offset + limit]
        if include_details:
            rows = []
            for env in page:
                code_env = client.get_code_env(env["language"], env["name"])
                row = _serialize_details(code_env.get_settings().get_raw(), env)
                if include_usages:
                    row["usages"] = code_env.list_usages()
                rows.append(row)
        else:
            rows = page
        return len(all_envs), len(matched), rows

    total, matched, rows = await run_blocking(_run)
    returned = len(rows)
    result = {
        "total_code_envs": total,
        "matched_code_envs": matched,
        "returned_code_envs": returned,
        "next_offset": offset + returned if offset + returned < matched else None,
        "code_envs": columnar(rows, _DETAIL_COLUMNS if include_details else _SUMMARY_COLUMNS),
    }
    if include_usages:
        result["warning"] = (
            "Usage data is an impact snapshot; DSS remains the authority on whether "
            "an environment can be deleted."
        )
    return compact_json(result)


@mcp.tool()
async def create_code_env(
    language: str,
    name: str,
    ctx: Context,
    requested_packages: list[str] | None = None,
    python_interpreter: str | None = None,
    owner: str | None = None,
    usable_by_all: bool = True,
    group_permissions: list[CodeEnvGroupPermission] | None = None,
    all_container_configurations: bool | None = None,
    container_configurations: list[str] | None = None,
    all_spark_kubernetes_configurations: bool | None = None,
    spark_kubernetes_configurations: list[str] | None = None,
) -> str:
    """Create a managed Design-node Python or R code environment.

    Requires global Create code envs or Manage all code envs permission. Core
    packages and Jupyter support are always enabled; container images are never
    built by this tool.
    """
    language = _language(language)
    name = _require_non_empty_string(name, "name")
    if language == "R" and python_interpreter is not None:
        raise ValueError("python_interpreter is only supported for PYTHON environments")
    await ctx.info(f"Creating DSS code environment '{name}'...")

    def _run():
        client = get_dss_client()
        params = {"pythonInterpreter": python_interpreter} if python_interpreter else None
        code_env = client.create_code_env(language, name, "DESIGN_MANAGED", params=params)
        settings = code_env.get_settings()
        _apply_changes(
            settings,
            owner=owner,
            usable_by_all=usable_by_all,
            group_permissions=group_permissions,
            requested_packages=requested_packages,
            python_interpreter=python_interpreter,
            all_container_configurations=all_container_configurations,
            container_configurations=container_configurations,
            all_spark_kubernetes_configurations=all_spark_kubernetes_configurations,
            spark_kubernetes_configurations=spark_kubernetes_configurations,
            baseline=True,
        )
        settings.save()
        package_result = code_env.update_packages()
        jupyter_result = code_env.set_jupyter_support(True)
        details = _serialize_details(
            code_env.get_settings().get_raw(),
            {"name": name, "language": language, "deployment_mode": "DESIGN_MANAGED"},
        )
        return details, package_result, jupyter_result

    details, package_result, jupyter_result = await run_blocking(_run)
    return compact_json(
        {
            "code_env": details,
            "package_update": package_result,
            "jupyter_update": jupyter_result,
        }
    )


@mcp.tool()
async def update_code_env(
    language: str,
    name: str,
    ctx: Context,
    requested_packages: list[str] | None = None,
    python_interpreter: str | None = None,
    owner: str | None = None,
    usable_by_all: bool | None = None,
    group_permissions: list[CodeEnvGroupPermission] | None = None,
    all_container_configurations: bool | None = None,
    container_configurations: list[str] | None = None,
    all_spark_kubernetes_configurations: bool | None = None,
    spark_kubernetes_configurations: list[str] | None = None,
    update_packages: bool = False,
    force_rebuild: bool = False,
    rebuild_images: bool = False,
) -> str:
    """Patch a managed Design-node code environment and optionally rebuild it.

    Requires global Create code envs or Manage all code envs permission. Supplied
    group_permissions replace the complete group permission list. A forced rebuild
    requires update_packages=true.
    """
    language = _language(language)
    name = _require_non_empty_string(name, "name")
    if language == "R" and python_interpreter is not None:
        raise ValueError("python_interpreter is only supported for PYTHON environments")
    if force_rebuild and not update_packages:
        raise ValueError("force_rebuild requires update_packages=true")
    if not any(
        value is not None
        for value in (
            requested_packages,
            python_interpreter,
            owner,
            usable_by_all,
            group_permissions,
            all_container_configurations,
            container_configurations,
            all_spark_kubernetes_configurations,
            spark_kubernetes_configurations,
        )
    ) and not (update_packages or rebuild_images):
        raise ValueError("Provide at least one code environment change or build action")
    await ctx.info(f"Updating DSS code environment '{name}'...")

    def _run():
        code_env = get_dss_client().get_code_env(language, name)
        settings = code_env.get_settings()
        changed = _apply_changes(
            settings,
            owner=owner,
            usable_by_all=usable_by_all,
            group_permissions=group_permissions,
            requested_packages=requested_packages,
            python_interpreter=python_interpreter,
            all_container_configurations=all_container_configurations,
            container_configurations=container_configurations,
            all_spark_kubernetes_configurations=all_spark_kubernetes_configurations,
            spark_kubernetes_configurations=spark_kubernetes_configurations,
        )
        if changed:
            settings.save()
        package_result = (
            code_env.update_packages(force_rebuild_env=force_rebuild)
            if update_packages
            else None
        )
        image_result = code_env.update_images() if rebuild_images else None
        details = _serialize_details(
            code_env.get_settings().get_raw(),
            {"name": name, "language": language, "deployment_mode": "DESIGN_MANAGED"},
        )
        return details, package_result, image_result

    details, package_result, image_result = await run_blocking(_run)
    return compact_json(
        {
            "code_env": details,
            "package_update": package_result,
            "image_update": image_result,
        }
    )


@mcp.tool()
async def delete_code_env(language: str, name: str, ctx: Context) -> str:
    """Delete one managed Design-node code environment.

    Requires global Manage all code envs permission. Use list_code_envs with exact
    search and include_usages before deletion when impact is uncertain.
    """
    language = _language(language)
    name = _require_non_empty_string(name, "name")
    await ctx.info(f"Deleting DSS code environment '{name}'...")
    await run_blocking(lambda: get_dss_client().get_code_env(language, name).delete())
    return compact_json({"name": name, "language": language, "deleted": True})
