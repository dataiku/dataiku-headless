---
name: groups
description: List and administer Dataiku DSS instance groups, external mappings, and global permissions.
---

# Groups

Use these tools for instance-level DSS group administration. They require administrator credentials and are not routed through Cobuild.

## Workflow

1. Use `list_groups` to locate groups by name, source type, or administrator status. It returns five groups by default and at most ten.
2. Use `include_permissions=True` only when inspecting the global permissions of the returned page; it includes the exposed permission and mapping fields in the returned rows when DSS provides them.
3. Before updating or deleting, confirm the exact group name and inspect permissions when the requested change affects access.
4. Use `create_group`, `update_group`, or `delete_group` for the requested change.
5. Verify the result with `list_groups` using the exact group name.

## Source Types And Mappings

- Use raw DSS source types. SSO-backed groups use `LOCAL_NO_AUTH` and `sso_group_names`.
- External mapping lists are complete replacements on create and update. An empty list clears that mapping; an omitted update field preserves it.
- `ldap_group_names`, `azure_ad_group_names`, `sso_group_names`, and `custom_group_names` contain the external groups that map to the DSS group.

## Implied Permissions

Some permissions have implied parent-child relationships that may not match the raw stored booleans returned by the API or these tools. For example:

- `may_create_projects = true` implies `may_create_projects_from_macros`, `may_create_projects_from_templates`, and `may_create_projects_from_dataiku_apps`
- `may_write_unsafe_code = true` implies `may_write_safe_code`
- `may_manage_code_envs = true` implies `may_create_code_envs`
- `may_manage_clusters = true` implies `may_create_clusters`
- `may_manage_code_studio_templates = true` implies `may_create_code_studio_templates`

In the DSS UI, these implied child permissions may appear enabled even when their stored values remain `false`.

## Safety Rules

- Group names are immutable; create a replacement group instead of renaming one.
- Global permissions are security-sensitive. Inspect current permissions before changing them and set only the permissions requested.
- The API-ticket cookie regex is intentionally not exposed by these tools and is preserved during updates.
