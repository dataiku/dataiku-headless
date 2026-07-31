---
name: users
description: List and administer Dataiku users. Use when finding, creating, updating, disabling, or deleting instance users.
---

# Users

Use these tools for instance-level Dataiku user administration. They require credentials with administrator rights and are not routed through Cobuild.

## Workflow

1. Use `list_users` to return all users, or filter by login, display name, email, or group membership to identify the exact login. Multiple requested groups use any-of matching.
2. Before creating a user or changing its `profile`, read `./licensing.md` and call `get_licensing_status`.
3. Before updating or deleting, confirm the exact login and current core settings from the matching row.
4. Use `create_user`, `update_user`, or `delete_user` for the requested change.
5. Verify the result with `list_users` using the exact login as the search value.

## Preferred Tools

- `list_users`
- `create_user`
- `update_user`
- `delete_user`

## Safety Rules

- Treat `groups` on create and update as a complete membership list, not an additive list.
- Use passwords supplied by the user. Never invent, repeat, or expose passwords in the response.
- Passwords apply only to `LOCAL` users; LDAP, SSO, and Azure AD users authenticate externally.
- Use only profile names returned by `get_licensing_status`; do not invent profile types.
- User profiles are license-controlled capability tiers, not security boundaries. Use groups for access control.
- Do not delete a user until the exact login has been established.
