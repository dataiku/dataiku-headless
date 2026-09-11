# Govern supporting objects

Use the connected `client` and public-method discovery described in [Govern](../govern.md).
These operations use Govern credentials and permissions. The identically named
DSS user/group MCP tools target DSS and must not be used here.

## Roles, identities, and pages

| Task | SDK entry point |
| --- | --- |
| Roles and role assignments | `client.get_roles_permissions_handler()` |
| Read custom pages | `client.list_custom_pages()`; `client.get_custom_page(page_id)` |
| Create or modify custom pages | `client.get_custom_pages_handler()` |
| Users | `client.list_users()`; `client.get_user(login)`; `client.get_own_user()` |
| User administration | `client.create_user(...)`; `client.create_users(...)`; `client.edit_users(...)`; `client.delete_users(...)` |
| User activity | `client.list_users_activity()` |
| Groups | `client.list_groups()`; `client.get_group(name)`; `client.create_group(...)` |

Use `help()` on the specific handle for argument and payload shapes. Read the
existing definition before saving and re-read afterward. Role definitions and
blueprint role assignments are separate resources. Updating one role's binding
must preserve other roles; deleting a blueprint's assignments removes all bindings.

For role bindings, the CLI uses `roleAssignmentsRules[role_id]` containing rules
with `criteria`, `userContainers`, and `fieldIds`. An unconditional binding has
empty `criteria` and `fieldIds` lists and the selected user/group containers in
`userContainers`. Inspect a matching rule and verify the saved membership; do not
replace the whole assignment definition to change one role.

Custom pages can display artifact views or custom HTML. Preserve the page type and
definition, and treat HTML/scripts as executable content. An external embed needs
a browser-accessible URL and compatible authentication; an API save does not prove
that the embedded page renders.

## Attachments and time series

- Upload with `client.upload_file(file_name, binary_file_handle)`; retain the
  returned `uploaded_file_id`. Inspect with
  `client.get_uploaded_file(file_id).get_description()` and download with its
  `download()` stream. Choose an explicit local destination and close streams;
  the server-provided filename must not decide where a local file is overwritten.
- Attach the returned file ID to the appropriate artifact field through its full
  definition, then re-read the field. Uploading alone does not attach it.
- Create with `client.create_time_series(datapoints=datapoints)` and retain
  `time_series_id`. Use `client.get_time_series(time_series_id)` for subsequent
  `get_values()`, `push_values()`, and `delete()` calls.
- Datapoints contain `timestamp` in epoch **milliseconds** and `value`.
  `push_values(..., upsert=True)` can overwrite existing timestamps; choose the
  mode deliberately. Read the affected interval after a write. `delete()` removes
  values in its timestamp range, or all values when neither bound is supplied.
