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

"""Dataiku group administration tools."""

from typing import Annotated

from fastmcp import Context
from pydantic import Field

from ..server import mcp
from ..auth import get_dss_client, require_admin
from ..executors import run_blocking
from .utils.identity_sources import IdentitySourceType
from .utils.serialization import columnar, compact_json
from .utils.validation import (
    require_non_empty_string as _require_non_empty_string,
    require_non_empty_strings as _require_non_empty_strings,
    require_non_negative_int as _require_non_negative_int,
    require_positive_int as _require_positive_int,
)

LdapGroupNames = Annotated[
    list[str] | None, Field(description="External groups mapped in; LDAP source only.")
]
AzureAdGroupNames = Annotated[
    list[str] | None,
    Field(description="External groups mapped in; AZURE_AD source only."),
]
SsoGroupNames = Annotated[
    list[str] | None,
    Field(description="External groups mapped in; LOCAL_NO_AUTH source only."),
]
CustomGroupNames = Annotated[
    list[str] | None,
    Field(description="External groups mapped in; CUSTOM source only."),
]

_BASIC_GROUP_FIELDS = {
    "name": "name",
}
_GROUP_FIELDS = {
    **_BASIC_GROUP_FIELDS,
    "description": "description",
    "source_type": "sourceType",
    "is_admin": "admin",
}
_MAPPING_FIELDS = {
    "ldap_group_names": "ldapGroupNames",
    "azure_ad_group_names": "azureADGroupNames",
    "sso_group_names": "ssoGroupNames",
    "custom_group_names": "customGroupNames",
}
_PERMISSION_FIELDS = {
    "may_manage_udm": "mayManageUDM",
    "may_create_projects": "mayCreateProjects",
    "may_create_projects_from_macros": "mayCreateProjectsFromMacros",
    "may_create_projects_from_templates": "mayCreateProjectsFromTemplates",
    "may_create_projects_from_dataiku_apps": "mayCreateProjectsFromDataikuApps",
    "may_write_unsafe_code": "mayWriteUnsafeCode",
    "may_write_safe_code": "mayWriteSafeCode",
    "may_create_authenticated_connections": "mayCreateAuthenticatedConnections",
    "may_create_code_envs": "mayCreateCodeEnvs",
    "may_create_clusters": "mayCreateClusters",
    "may_create_code_studio_templates": "mayCreateCodeStudioTemplates",
    "may_develop_plugins": "mayDevelopPlugins",
    "may_edit_lib_folders": "mayEditLibFolders",
    "may_manage_code_envs": "mayManageCodeEnvs",
    "may_manage_clusters": "mayManageClusters",
    "may_manage_code_studio_templates": "mayManageCodeStudioTemplates",
    "may_view_indexed_hive_connections": "mayViewIndexedHiveConnections",
    "may_create_published_api_services": "mayCreatePublishedAPIServices",
    "may_create_published_projects": "mayCreatePublishedProjects",
    "may_write_in_root_project_folder": "mayWriteInRootProjectFolder",
    "may_create_active_web_content": "mayCreateActiveWebContent",
    "may_create_workspaces": "mayCreateWorkspaces",
    "may_share_to_workspaces": "mayShareToWorkspaces",
    "may_create_data_collections": "mayCreateDataCollections",
    "may_publish_to_data_collections": "mayPublishToDataCollections",
    "may_manage_feature_store": "mayManageFeatureStore",
    "may_manage_enterprise_asset_library": "mayManageEnterpriseAssetLibrary",
    "may_create_enterprise_asset_collections": "mayCreateEnterpriseAssetCollections",
}
_DETAIL_FIELDS = {**_GROUP_FIELDS, **_MAPPING_FIELDS, **_PERMISSION_FIELDS}


def _validate_group_names(names: list[str] | None, field_name: str) -> list[str] | None:
    if names is None:
        return None
    return _require_non_empty_strings(names, field_name)


def _sanitize_group(raw_group: dict, fields: dict[str, str]) -> dict:
    return {field: raw_group.get(raw_field) for field, raw_field in fields.items()}


def _apply_changes(definition: dict, changes: dict) -> None:
    """Updates a Dataiku group `definition` with `changes` (except immutable group "name")."""
    for field, raw_field in _GROUP_FIELDS.items():
        if field != "name" and changes[field] is not None:
            definition[raw_field] = changes[field]
    for field, raw_field in _MAPPING_FIELDS.items():
        if changes[field] is not None:
            definition[raw_field] = changes[field]
    for field, raw_field in _PERMISSION_FIELDS.items():
        if changes[field] is not None:
            definition[raw_field] = changes[field]


@mcp.tool(
    title="List Groups",
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "openWorldHint": False,
    },
)
async def list_groups(
    ctx: Context,
    search: Annotated[
        str, Field(description="Substring matched against group names.")
    ] = "",
    source_type: IdentitySourceType | None = None,
    is_admin: Annotated[
        bool | None, Field(description="Keeps only admin, or only non-admin, groups.")
    ] = None,
    include_permissions: Annotated[
        bool, Field(description="Adds each group's global permissions. Admin only.")
    ] = False,
    offset: Annotated[
        int, Field(description="Zero-based offset into the matches.")
    ] = 0,
    limit: Annotated[int, Field(description="Capped at 10.")] = 5,
) -> str:
    """Find group names to assign; admins also see permissions and mappings."""
    search = search.strip()
    offset = _require_non_negative_int(offset, "offset")
    limit = min(_require_positive_int(limit, "limit"), 10)

    try:
        await require_admin()
    except PermissionError:
        if (source_type is not None) or (is_admin is not None) or include_permissions:
            raise PermissionError(
                "The `source_type`, `is_admin` and `include_permissions` options require "
                "global administrator."
            )
        fields = _BASIC_GROUP_FIELDS
        raw_groups = await run_blocking(
            lambda: [group.get_raw() for group in get_dss_client().list_groups_info()]
        )
    else:
        fields = _DETAIL_FIELDS if include_permissions else _GROUP_FIELDS
        raw_groups = await run_blocking(lambda: get_dss_client().list_groups())

    await ctx.info("Listing Dataiku groups...")
    total_groups = len(raw_groups)
    groups = [_sanitize_group(group, fields) for group in raw_groups]

    if search:
        query = search.casefold()
        groups = [
            group
            for group in groups
            if query in str(group.get("name") or "").casefold()
        ]
    if source_type is not None:
        groups = [group for group in groups if group.get("source_type") == source_type]
    if is_admin is not None:
        groups = [group for group in groups if group.get("is_admin") == is_admin]

    groups.sort(
        key=lambda group: (
            str(group["name"]).casefold(),
            str(group["name"]),
        )
    )
    matched_groups = len(groups)
    page = groups[offset : offset + limit]
    returned_groups = len(page)
    next_offset = (
        offset + returned_groups if offset + returned_groups < matched_groups else None
    )

    return compact_json(
        {
            "total_groups": total_groups,
            "matched_groups": matched_groups,
            "returned_groups": returned_groups,
            "next_offset": next_offset,
            "groups": columnar(page, list(fields)),
        }
    )


@mcp.tool(
    title="Create Group",
    annotations={
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
async def create_group(
    name: Annotated[
        str, Field(description="Special characters beyond . _ - @ are rejected.")
    ],
    ctx: Context,
    source_type: IdentitySourceType = "LOCAL",
    description: str = "",
    is_admin: Annotated[
        bool, Field(description="Grants instance-wide administrative privileges.")
    ] = False,
    ldap_group_names: LdapGroupNames = None,
    azure_ad_group_names: AzureAdGroupNames = None,
    sso_group_names: SsoGroupNames = None,
    custom_group_names: CustomGroupNames = None,
    may_manage_udm: bool = False,
    may_create_projects: bool = False,
    may_create_projects_from_macros: bool = False,
    may_create_projects_from_templates: bool = False,
    may_create_projects_from_dataiku_apps: bool = False,
    may_write_unsafe_code: bool = False,
    may_write_safe_code: bool = False,
    may_create_authenticated_connections: bool = False,
    may_create_code_envs: bool = False,
    may_create_clusters: bool = False,
    may_create_code_studio_templates: bool = False,
    may_develop_plugins: bool = False,
    may_edit_lib_folders: bool = False,
    may_manage_code_envs: bool = False,
    may_manage_clusters: bool = False,
    may_manage_code_studio_templates: bool = False,
    may_view_indexed_hive_connections: bool = False,
    may_create_published_api_services: bool = False,
    may_create_published_projects: bool = False,
    may_write_in_root_project_folder: bool = False,
    may_create_active_web_content: bool = False,
    may_create_workspaces: bool = False,
    may_share_to_workspaces: bool = False,
    may_create_data_collections: bool = False,
    may_publish_to_data_collections: bool = False,
    may_manage_feature_store: bool = False,
    may_manage_enterprise_asset_library: bool = False,
    may_create_enterprise_asset_collections: bool = False,
) -> str:
    """Add a group with its global permissions and external mappings. Admin only."""
    name = _require_non_empty_string(name, "name")
    mappings = {
        "ldap_group_names": _validate_group_names(ldap_group_names, "ldap_group_names")
        or [],
        "azure_ad_group_names": _validate_group_names(
            azure_ad_group_names, "azure_ad_group_names"
        )
        or [],
        "sso_group_names": _validate_group_names(sso_group_names, "sso_group_names")
        or [],
        "custom_group_names": _validate_group_names(
            custom_group_names, "custom_group_names"
        )
        or [],
    }
    permissions = {
        "may_manage_udm": may_manage_udm,
        "may_create_projects": may_create_projects,
        "may_create_projects_from_macros": may_create_projects_from_macros,
        "may_create_projects_from_templates": may_create_projects_from_templates,
        "may_create_projects_from_dataiku_apps": may_create_projects_from_dataiku_apps,
        "may_write_unsafe_code": may_write_unsafe_code,
        "may_write_safe_code": may_write_safe_code,
        "may_create_authenticated_connections": may_create_authenticated_connections,
        "may_create_code_envs": may_create_code_envs,
        "may_create_clusters": may_create_clusters,
        "may_create_code_studio_templates": may_create_code_studio_templates,
        "may_develop_plugins": may_develop_plugins,
        "may_edit_lib_folders": may_edit_lib_folders,
        "may_manage_code_envs": may_manage_code_envs,
        "may_manage_clusters": may_manage_clusters,
        "may_manage_code_studio_templates": may_manage_code_studio_templates,
        "may_view_indexed_hive_connections": may_view_indexed_hive_connections,
        "may_create_published_api_services": may_create_published_api_services,
        "may_create_published_projects": may_create_published_projects,
        "may_write_in_root_project_folder": may_write_in_root_project_folder,
        "may_create_active_web_content": may_create_active_web_content,
        "may_create_workspaces": may_create_workspaces,
        "may_share_to_workspaces": may_share_to_workspaces,
        "may_create_data_collections": may_create_data_collections,
        "may_publish_to_data_collections": may_publish_to_data_collections,
        "may_manage_feature_store": may_manage_feature_store,
        "may_manage_enterprise_asset_library": may_manage_enterprise_asset_library,
        "may_create_enterprise_asset_collections": may_create_enterprise_asset_collections,
    }
    changes = {
        "description": description,
        "source_type": source_type,
        "is_admin": is_admin,
        **mappings,
        **permissions,
    }
    await require_admin()
    await ctx.info(f"Creating Dataiku group '{name}'...")

    def _run():
        client = get_dss_client()
        group = client.create_group(
            name, description=description, source_type=source_type
        )
        definition = group.get_definition()
        _apply_changes(definition, changes)
        group.set_definition(definition)
        return _sanitize_group(group.get_definition(), _DETAIL_FIELDS)

    return compact_json({"group": await run_blocking(_run)})


@mcp.tool(
    title="Update Group",
    annotations={
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def update_group(
    name: str,
    ctx: Context,
    description: str | None = None,
    source_type: IdentitySourceType | None = None,
    is_admin: Annotated[
        bool | None,
        Field(description="Grants instance-wide administrative privileges."),
    ] = None,
    ldap_group_names: LdapGroupNames = None,
    azure_ad_group_names: AzureAdGroupNames = None,
    sso_group_names: SsoGroupNames = None,
    custom_group_names: CustomGroupNames = None,
    may_manage_udm: bool | None = None,
    may_create_projects: bool | None = None,
    may_create_projects_from_macros: bool | None = None,
    may_create_projects_from_templates: bool | None = None,
    may_create_projects_from_dataiku_apps: bool | None = None,
    may_write_unsafe_code: bool | None = None,
    may_write_safe_code: bool | None = None,
    may_create_authenticated_connections: bool | None = None,
    may_create_code_envs: bool | None = None,
    may_create_clusters: bool | None = None,
    may_create_code_studio_templates: bool | None = None,
    may_develop_plugins: bool | None = None,
    may_edit_lib_folders: bool | None = None,
    may_manage_code_envs: bool | None = None,
    may_manage_clusters: bool | None = None,
    may_manage_code_studio_templates: bool | None = None,
    may_view_indexed_hive_connections: bool | None = None,
    may_create_published_api_services: bool | None = None,
    may_create_published_projects: bool | None = None,
    may_write_in_root_project_folder: bool | None = None,
    may_create_active_web_content: bool | None = None,
    may_create_workspaces: bool | None = None,
    may_share_to_workspaces: bool | None = None,
    may_create_data_collections: bool | None = None,
    may_publish_to_data_collections: bool | None = None,
    may_manage_feature_store: bool | None = None,
    may_manage_enterprise_asset_library: bool | None = None,
    may_create_enterprise_asset_collections: bool | None = None,
) -> str:
    """Patch a group's permissions and mappings; supplied lists replace. Admin only."""
    name = _require_non_empty_string(name, "name")
    mappings = {
        "ldap_group_names": _validate_group_names(ldap_group_names, "ldap_group_names"),
        "azure_ad_group_names": _validate_group_names(
            azure_ad_group_names, "azure_ad_group_names"
        ),
        "sso_group_names": _validate_group_names(sso_group_names, "sso_group_names"),
        "custom_group_names": _validate_group_names(
            custom_group_names, "custom_group_names"
        ),
    }
    permissions = {
        "may_manage_udm": may_manage_udm,
        "may_create_projects": may_create_projects,
        "may_create_projects_from_macros": may_create_projects_from_macros,
        "may_create_projects_from_templates": may_create_projects_from_templates,
        "may_create_projects_from_dataiku_apps": may_create_projects_from_dataiku_apps,
        "may_write_unsafe_code": may_write_unsafe_code,
        "may_write_safe_code": may_write_safe_code,
        "may_create_authenticated_connections": may_create_authenticated_connections,
        "may_create_code_envs": may_create_code_envs,
        "may_create_clusters": may_create_clusters,
        "may_create_code_studio_templates": may_create_code_studio_templates,
        "may_develop_plugins": may_develop_plugins,
        "may_edit_lib_folders": may_edit_lib_folders,
        "may_manage_code_envs": may_manage_code_envs,
        "may_manage_clusters": may_manage_clusters,
        "may_manage_code_studio_templates": may_manage_code_studio_templates,
        "may_view_indexed_hive_connections": may_view_indexed_hive_connections,
        "may_create_published_api_services": may_create_published_api_services,
        "may_create_published_projects": may_create_published_projects,
        "may_write_in_root_project_folder": may_write_in_root_project_folder,
        "may_create_active_web_content": may_create_active_web_content,
        "may_create_workspaces": may_create_workspaces,
        "may_share_to_workspaces": may_share_to_workspaces,
        "may_create_data_collections": may_create_data_collections,
        "may_publish_to_data_collections": may_publish_to_data_collections,
        "may_manage_feature_store": may_manage_feature_store,
        "may_manage_enterprise_asset_library": may_manage_enterprise_asset_library,
        "may_create_enterprise_asset_collections": may_create_enterprise_asset_collections,
    }
    changes = {
        "description": description,
        "source_type": source_type,
        "is_admin": is_admin,
        **mappings,
        **permissions,
    }
    if all(value is None for value in changes.values()):
        raise ValueError("Provide at least one group field to update")

    await require_admin()
    await ctx.info(f"Updating Dataiku group '{name}'...")

    def _run():
        group = get_dss_client().get_group(name)
        definition = group.get_definition()
        _apply_changes(definition, changes)
        group.set_definition(definition)
        return _sanitize_group(group.get_definition(), _DETAIL_FIELDS)

    return compact_json({"group": await run_blocking(_run)})


@mcp.tool(
    title="Delete Group",
    annotations={
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
async def delete_group(name: str, ctx: Context) -> str:
    """Remove a group from the instance. Admin only."""
    name = _require_non_empty_string(name, "name")
    await require_admin()
    await ctx.info(f"Deleting Dataiku group '{name}'...")
    await run_blocking(lambda: get_dss_client().get_group(name).delete())
    return compact_json({"name": name, "deleted": True})
