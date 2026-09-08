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

"""Dataiku code environment administration tools."""

import re

from fastmcp import Context
from pydantic import BaseModel

from ..server import mcp
from ..auth import get_dss_client
from ..executors import run_blocking
from .utils.serialization import columnar, compact_json
from .utils.validation import (
    require_allowed_value as _require_allowed_value,
    require_non_empty_string as _require_non_empty_string,
    require_non_empty_strings as _require_non_empty_strings,
    require_non_negative_int as _require_non_negative_int,
    require_positive_int as _require_positive_int,
)

_LANGUAGES = {"PYTHON", "R"}
_SEARCH_MODES = {"partial", "exact"}
_PACKAGE_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_PACKAGE_SPEC_NAME_PATTERN = re.compile(
    r'^\s*(?:["\'](?P<quoted>[A-Za-z0-9][A-Za-z0-9._-]*)["\']|'
    r"(?P<plain>[A-Za-z0-9][A-Za-z0-9._-]*))"
)
_PYTHON_INTERPRETERS = {
    "PYTHON39",
    "PYTHON310",
    "PYTHON311",
    "PYTHON312",
    "PYTHON313",
    "PYTHON314",
}
_SUMMARY_COLUMNS = ["name", "language", "owner", "deployment_mode"]
_DETAIL_COLUMNS = [
    *_SUMMARY_COLUMNS,
    "usable_by_all",
    "group_permissions",
    "python_interpreter",
    "requested_packages",
    "actual_packages",
    "all_container_configurations",
    "container_configurations",
    "all_spark_kubernetes_configurations",
    "spark_kubernetes_configurations",
]


class CodeEnvGroupPermission(BaseModel):
    """One Dataiku group's access to a code environment."""

    group: str
    use: bool
    update: bool
    manage_users: bool


def _normalize_package_name(name: str, language: str) -> str:
    """Normalize a package name for comparison in one code-environment language."""
    if language == "PYTHON":
        return re.sub(r"[-_.]+", "-", name).casefold()
    return name.casefold()


def _validate_package_names(packages: list[str] | None) -> list[str] | None:
    """Validate query package names rather than requirement/version specifications."""
    if packages is None:
        return None
    if not packages:
        raise ValueError("'packages' must be a non-empty list")
    packages = _require_non_empty_strings(packages, "packages")
    invalid = [
        package for package in packages if not _PACKAGE_NAME_PATTERN.fullmatch(package)
    ]
    if invalid:
        raise ValueError(
            "'packages' must contain package names only, without version constraints "
            f"or extras: {invalid}"
        )
    return packages


def _requested_package_names(raw: dict, language: str) -> set[str]:
    """Return normalized names from an environment's declared package specifications."""
    return {
        _normalize_package_name(match.group("quoted") or match.group("plain"), language)
        for spec in raw.get("specPackageList", "").splitlines()
        if (match := _PACKAGE_SPEC_NAME_PATTERN.match(spec)) is not None
    }


def _serialize_code_env_summary(raw: dict) -> dict:
    """Map a raw Dataiku code environment to the MCP summary response."""
    return {
        "name": raw.get("envName", ""),
        "language": raw.get("envLang", ""),
        "owner": raw.get("owner", ""),
        "deployment_mode": raw.get("deploymentMode", ""),
    }


def _serialize_code_env_details(raw: dict) -> dict:
    """Map raw Dataiku code-environment settings to the MCP detail response."""
    desc = raw.get("desc") or {}
    permissions = raw.get("permissions", desc.get("permissions", [])) or []
    return {
        **_serialize_code_env_summary(raw),
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
        "requested_packages": raw.get("specPackageList", "").splitlines(),
        "actual_packages": raw.get("actualPackageList", "").splitlines(),
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


def _apply_changes(
    settings,
    *,
    owner: str | None,
    usable_by_all: bool | None,
    group_permissions: list[CodeEnvGroupPermission] | None,
    requested_packages: list[str] | None,
    all_container_configurations: bool | None,
    container_configurations: list[str] | None,
    all_spark_kubernetes_configurations: bool | None,
    spark_kubernetes_configurations: list[str] | None,
    baseline: bool = False,
) -> None:
    raw = settings.get_raw()
    desc = raw.setdefault("desc", {})
    if baseline:
        desc["installCorePackages"] = True
        desc["installJupyterSupport"] = True
    if owner is not None:
        desc["owner"] = owner
    if usable_by_all is not None:
        raw["usableByAll"] = usable_by_all
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
    if requested_packages is not None:
        settings.set_required_packages(*requested_packages)
    if all_container_configurations is not None:
        raw["allContainerConfs"] = all_container_configurations
    if container_configurations is not None:
        raw["containerConfs"] = container_configurations
    if all_spark_kubernetes_configurations is not None:
        raw["allSparkKubernetesConfs"] = all_spark_kubernetes_configurations
    if spark_kubernetes_configurations is not None:
        raw["sparkKubernetesConfs"] = spark_kubernetes_configurations


@mcp.tool()
async def list_code_envs(
    ctx: Context,
    search: str = "",
    search_mode: str = "partial",
    language: str | None = None,
    packages: list[str] | None = None,
    include_details: bool = False,
    offset: int = 0,
    limit: int = 5,
) -> str:
    """List Dataiku code environments with optional settings detail.

    Args:
        search: Environment name search. Defaults to every environment.
        search_mode: ``partial`` for case-insensitive name matching, or ``exact``
            to retrieve one named environment. Ignored when ``search`` is empty.
        language: Exact language filter: ``PYTHON`` or ``R``.
        packages: Return only environments that declare every listed package name.
            Requires the same permission as ``include_details``.
        include_details: Return owner, access, packages, and image-build targets
            for each returned environment. Requires global Create code envs or
            Manage all code envs permission.
        offset: Zero-based offset within the matching environments.
        limit: Maximum environments to return. Values above 100 are capped at 100.
    """
    search = search.strip()
    if search:
        search_mode = _require_allowed_value(search_mode, "search_mode", _SEARCH_MODES)
    if language is not None:
        language = _require_allowed_value(language, "language", _LANGUAGES)
    packages = _validate_package_names(packages)
    offset = _require_non_negative_int(offset, "offset")
    limit = min(_require_positive_int(limit, "limit"), 100)
    await ctx.info("Listing Dataiku code environments...")

    def _run():
        client = get_dss_client()
        all_envs = [_serialize_code_env_summary(raw) for raw in client.list_code_envs()]
        matched = all_envs
        if search:
            if search_mode == "exact":
                matched = [env for env in matched if env["name"] == search]
            else:
                query = search.casefold()
                matched = [env for env in matched if query in env["name"].casefold()]
        if language is not None:
            matched = [env for env in matched if env["language"] == language]
        if packages is not None:
            rows = []
            for env in matched:
                code_env = client.get_code_env(env["language"], env["name"])
                raw = code_env.get_settings().get_raw()
                details = _serialize_code_env_details(raw)
                requested = _requested_package_names(raw, env["language"])
                query = {
                    _normalize_package_name(package, env["language"])
                    for package in packages
                }
                if query <= requested:
                    rows.append(details if include_details else env)
            matched = rows
        matched.sort(key=lambda env: (env["name"].casefold(), env["name"]))
        page = matched[offset : offset + limit]
        if include_details and packages is None:
            rows = []
            for env in page:
                code_env = client.get_code_env(env["language"], env["name"])
                row = _serialize_code_env_details(code_env.get_settings().get_raw())
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
        "code_envs": columnar(
            rows, _DETAIL_COLUMNS if include_details else _SUMMARY_COLUMNS
        ),
    }
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
    packages and Jupyter support are always enabled. Container images are built
    when container or Spark build targets are supplied.

    Args:
        language: Environment language: ``PYTHON`` or ``R``.
        name: New environment name.

    See the Code Environments skill reference for parameter details and operating
    guidance.
    """
    language = _require_allowed_value(language, "language", _LANGUAGES)
    name = _require_non_empty_string(name, "name")
    if language == "R" and python_interpreter is not None:
        raise ValueError("python_interpreter is only supported for PYTHON environments")
    if python_interpreter is not None:
        python_interpreter = _require_allowed_value(
            python_interpreter, "python_interpreter", _PYTHON_INTERPRETERS
        )
    build_images = any(
        value is not None
        for value in (
            all_container_configurations,
            container_configurations,
            all_spark_kubernetes_configurations,
            spark_kubernetes_configurations,
        )
    )
    await ctx.info(f"Creating Dataiku code environment '{name}'...")

    def _run():
        client = get_dss_client()
        params = (
            {"pythonInterpreter": python_interpreter} if python_interpreter else None
        )
        code_env = client.create_code_env(
            language, name, "DESIGN_MANAGED", params=params
        )
        settings = code_env.get_settings()
        _apply_changes(
            settings,
            owner=owner,
            usable_by_all=usable_by_all,
            group_permissions=group_permissions,
            requested_packages=requested_packages,
            all_container_configurations=all_container_configurations,
            container_configurations=container_configurations,
            all_spark_kubernetes_configurations=all_spark_kubernetes_configurations,
            spark_kubernetes_configurations=spark_kubernetes_configurations,
            baseline=True,
        )
        settings.save()
        package_result = code_env.update_packages()
        jupyter_result = code_env.set_jupyter_support(True)
        image_result = code_env.update_images() if build_images else None
        raw_settings = code_env.get_settings().get_raw()
        details = _serialize_code_env_details(raw_settings)
        return details, package_result, jupyter_result, image_result

    details, package_result, jupyter_result, image_result = await run_blocking(_run)
    return compact_json(
        {
            "code_env": details,
            "package_update": package_result,
            "jupyter_update": jupyter_result,
            "image_update": image_result,
        }
    )


@mcp.tool()
async def update_code_env(
    language: str,
    name: str,
    ctx: Context,
    requested_packages: list[str] | None = None,
    owner: str | None = None,
    usable_by_all: bool | None = None,
    group_permissions: list[CodeEnvGroupPermission] | None = None,
    all_container_configurations: bool | None = None,
    container_configurations: list[str] | None = None,
    all_spark_kubernetes_configurations: bool | None = None,
    spark_kubernetes_configurations: list[str] | None = None,
    force_rebuild: bool = False,
) -> str:
    """Patch a Design-node code environment and rebuild affected artifacts.

    Requires global Create code envs or Manage all code envs permission. Supplied
    group_permissions replace the complete group permission list. Package changes
    are supported only for managed Design-node environments; they update the local
    environment and rebuild images. Build-target changes rebuild images.
    ``force_rebuild`` forces a rebuild of the local environment.

    Omitted fields are preserved. Empty lists intentionally clear their setting.

    Args:
        language: Environment language: ``PYTHON`` or ``R``.
        name: Existing environment name.

    See the Code Environments skill reference for parameter details and operating
    guidance.
    """
    language = _require_allowed_value(language, "language", _LANGUAGES)
    name = _require_non_empty_string(name, "name")
    package_spec_changed = requested_packages is not None
    build_targets_changed = any(
        value is not None
        for value in (
            all_container_configurations,
            container_configurations,
            all_spark_kubernetes_configurations,
            spark_kubernetes_configurations,
        )
    )
    await ctx.info(f"Updating Dataiku code environment '{name}'...")

    def _run():
        code_env = get_dss_client().get_code_env(language, name)
        settings = code_env.get_settings()
        if (
            requested_packages is not None
            and settings.get_raw().get("deploymentMode") != "DESIGN_MANAGED"
        ):
            raise ValueError(
                "requested_packages can only be changed for DESIGN_MANAGED "
                "code environments"
            )
        _apply_changes(
            settings,
            owner=owner,
            usable_by_all=usable_by_all,
            group_permissions=group_permissions,
            requested_packages=requested_packages,
            all_container_configurations=all_container_configurations,
            container_configurations=container_configurations,
            all_spark_kubernetes_configurations=all_spark_kubernetes_configurations,
            spark_kubernetes_configurations=spark_kubernetes_configurations,
        )
        settings.save()
        package_result = (
            code_env.update_packages(force_rebuild_env=force_rebuild)
            if package_spec_changed or force_rebuild
            else None
        )
        image_result = (
            code_env.update_images()
            if package_spec_changed or build_targets_changed
            else None
        )
        raw_settings = code_env.get_settings().get_raw()
        details = _serialize_code_env_details(raw_settings)
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
    """Delete one Dataiku code environment.

    Requires global Manage all code envs permission. The tool refuses deletion when
    Dataiku reports current usages and returns ``deleted: false``, the usages, and
    remediation guidance instead of deleting the environment.
    """
    language = _require_allowed_value(language, "language", _LANGUAGES)
    name = _require_non_empty_string(name, "name")
    await ctx.info(f"Deleting Dataiku code environment '{name}'...")
    code_env = await run_blocking(lambda: get_dss_client().get_code_env(language, name))
    usages = await run_blocking(code_env.list_usages)
    if usages:
        return compact_json(
            {
                "name": name,
                "language": language,
                "deleted": False,
                "error": "Code environment cannot be deleted because it has current usages.",
                "usages": usages,
                "hint": "Remove or replace all listed code-environment usages, then retry deletion.",
            }
        )
    await run_blocking(code_env.delete)
    return compact_json({"name": name, "language": language, "deleted": True})
