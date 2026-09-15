# Govern supporting objects

Use the `govern` tool described in [Govern](../govern.md). These operations use the
Govern credentials and permissions. The identically named DSS user and group MCP
tools target DSS and must not be used here.

## Roles, permissions, and identities

| Task | Operations |
| --- | --- |
| Roles | `list_roles`, `get_role`, `create_role`, `update_role`, `delete_role` |
| Role assignments per blueprint | `list_role_assignments`, `get_role_assignments`, `create_role_assignments`, `update_role_assignments`, `delete_role_assignments` |
| Blueprint permissions | `get_default_blueprint_permissions`, `update_default_blueprint_permissions`, `list_blueprint_permissions`, `get_blueprint_permissions`, `create_blueprint_permissions`, `update_blueprint_permissions`, `delete_blueprint_permissions` |
| Users | `list_users`, `get_user`, `create_user`, `update_user`, `delete_user`, `get_own_user` |
| Groups | `list_groups`, `get_group`, `create_group`, `update_group`, `delete_group` |

Read the existing definition before saving and re-read afterward. Role definitions
and blueprint role assignments are separate resources. Updating one role's binding
must preserve the other roles; `delete_role_assignments` removes every binding of
the blueprint. For global permissions on Govern 15, use `isGovernArchitect`; the
deprecated `mayManageGovern` key was removed. Discover existing permissions before
changing them.

Role bindings live in `roleAssignmentsRules[role_id]`, a list of rules with
`criteria`, `userContainers`, and `fieldIds`. An unconditional binding has empty
`criteria` and `fieldIds` lists and the selected user or group containers in
`userContainers`. Inspect a matching rule and verify the saved membership; change
one role's rules inside the full assignment definition, never replace the whole
definition to change one role.

`update_user` and `update_group` merge the given keys into the current settings or
definition. `create_user` needs a `password` for LOCAL users; other keys are optional.

## Custom pages

- `list_custom_pages` and `get_custom_page` show pages as the authenticated user
  sees them.
- `get_custom_page_definition`, `create_custom_page`, `update_custom_page`,
  `delete_custom_page`, `get_custom_pages_order`, and `update_custom_pages_order`
  are designer operations.

Custom pages can display artifact views or custom HTML. Discover the target
release's page types from an existing page; built-in `standard-page` entries are not
creatable custom pages. Preserve the page type and definition, and treat HTML and
scripts as executable content. An external embed needs a browser-accessible URL and
compatible authentication; a saved definition does not prove that the embedded page
renders.

### Govern 15 grid pages and charts

Prefer native grid pages for dashboards over Govern items. A `grid` page can contain
multiple tabs with table, chart, HTML, and nested subgrid tiles. Copy the payload
structure from a matching page read with `get_custom_page_definition` instead of
guessing nested keys.

Build the chart's data settings before its appearance:

1. Filter the intended items and add projections for the needed fields. By default,
   only item IDs are projected. Table tiles fetch their own columns, so a working
   table does not prove that a chart has the data it needs.
2. Define breakdown dimensions and measures, then select that breakdown and measure
   in the chart. A subgrid inherits its parent's data settings unless overridden.
3. Use standard charts when they fit. Chart selections filter tables and charts
   sharing the same data settings. Converting to a custom JavaScript or ECharts
   chart cannot be reverted to the standard chart configuration.

Re-read the saved definition, then check the page with real data: displayed counts
and measures, drill-down targets, and selection-panel behavior. A preview using
sample data does not validate the real query. Create pages hidden while validating
them, and make them visible when publication is part of the task. See
[custom page design](https://doc.dataiku.com/dss/latest/governance/custom-pages.html)
for the current tile, projection, aggregation, and chart options.

## Files and time series

- `upload_file` with a local `file_path` returns the file description; retain its
  `id`. `get_uploaded_file` reads the description, `download_uploaded_file` writes
  the content to an explicit `output_path` and never overwrites unless `overwrite`
  is true, `delete_uploaded_file` removes it.
- Attach the returned file ID to the appropriate artifact field through
  `update_artifact_fields`, then re-read the field. Uploading alone does not attach it.
- `create_time_series` returns `time_series_id`; retain it. Use
  `get_time_series_values`, `push_time_series_values`, and
  `delete_time_series_values` afterward.
- Datapoints contain `timestamp` in epoch **milliseconds** and `value`.
  `push_time_series_values` with `upsert: true` (the default) overwrites existing
  timestamps; choose the mode deliberately. Read the affected interval after a
  write. `delete_time_series_values` removes values in its timestamp window, or all
  values when neither bound is supplied; it does not delete the time-series object.
  Verify boundary behavior before a range deletion: Govern 15.0.1 excludes both
  endpoint timestamps from reads and deletes.
