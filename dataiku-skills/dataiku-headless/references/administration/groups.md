---
name: groups
description: List and administer Dataiku DSS instance groups, external mappings, and global permissions.
---

# Groups

Use these tools for instance-level DSS group administration. They require administrator credentials and are not routed through Cobuild.

## Workflow

1. Use `list_groups` to locate groups by name, source type, or administrator status. It returns five groups by default and at most ten.
2. Use `include_permissions=True` only when inspecting the global permissions of the returned page; it retrieves each returned group's full definition.
3. Before updating or deleting, confirm the exact group name and inspect permissions when the requested change affects access.
4. Use `create_group`, `update_group`, or `delete_group` for the requested change.
5. Verify the result with `list_groups` using the exact group name.

## Source Types And Mappings

- Use raw DSS source types. SSO-backed groups use `LOCAL_NO_AUTH` and `sso_group_names`.
- External mapping lists are complete replacements on create and update. An empty list clears that mapping; an omitted update field preserves it.
- `ldap_group_names`, `azure_ad_group_names`, `sso_group_names`, and `custom_group_names` contain the external groups that map to the DSS group.

## Safety Rules

- Group names are immutable; create a replacement group instead of renaming one.
- Global permissions are security-sensitive. Inspect current permissions before changing them and set only the permissions requested.
- The API-ticket cookie regex is intentionally not exposed by these tools and is preserved during updates.
