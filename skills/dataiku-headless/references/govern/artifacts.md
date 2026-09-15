# Govern artifacts

Use the `govern` tool described in [Govern](../govern.md). Identifiers such as
`blueprint_id`, `version_id`, and `artifact_id` come from discovery or the user.

## Discover and inspect

Blueprints and versions:

- `list_blueprints` returns envelopes; the blueprint is nested under `blueprint`.
- `list_blueprint_versions` with `blueprint_id` lists versions and their status.
- `get_blueprint_version` with `blueprint_id` and `version_id` returns
  `definition` (the schema, with `fieldDefinitions`) and `trace` (status, origin).

Artifacts:

- `search_artifacts` with `blueprint_ids`, `blueprint_version_ids`, `artifact_ids`,
  `field_filters`, `archived`, and `sort`. Each hit nests the record under
  `artifact`. The result carries `count` and `has_more`; when `has_more` is true,
  raise `max_results` or narrow the filters before calling the inventory complete.
  A field filter is `{"condition_type": "CONTAINS", "condition": "churn"}` for the
  name, or adds `field_id` for one field.
- `get_artifact` with `artifact_id` returns the full definition: `name`, `fields`,
  `workflow`, and `blueprintVersionId`.

For an existing artifact, inspect its own blueprint version; another version of
the same blueprint can have different fields.

Govern 15 also exposes creation and last-modification metadata, including the actor
and timestamp. Inspect `creationRevision` and `lastModificationRevision` when the
task needs provenance; preserve server-managed metadata when editing other fields.
These values describe creation and the latest change, not a complete audit history.

## Create or update

Create on an ACTIVE version after reading its `fieldDefinitions`:

```json
{"operation": "create_artifact",
 "params": {"blueprint_id": "bp.system.govern_project", "version_id": "bv.system.default",
            "name": "Churn model", "fields": {"description": "Quarterly churn scoring"}}}
```

Retain the returned `id` and re-read with `get_artifact`.

For a partial edit, use `update_artifact_fields` with `artifact_id` and `fields`
(and `name` when it changes). It merges the given fields and preserves the rest.
Compare the returned `fields` with the request; a field that did not persist means
the value was rejected silently, for example a scalar sent to a list field.

For a structural edit (workflow state, archived flag, blueprint reference), use
`update_artifact` with the complete `definition` read from `get_artifact`, changed
only where requested. A partial definition loses unrelated state.

`delete_artifact` removes the record; confirm the ID first.

## Field rules

- Fields are keyed by ID in `fieldDefinitions`; the type key is `fieldType`.
  Use the actual field ID, not its display label. User-entered values belong in
  `sourceType: STORE` fields; preserve computed fields.
- `listConfig` makes a field a list, even if the configuration is empty. Send an
  array for one value as well. CATEGORY values must match the defined categories,
  case-sensitively.
- REFERENCE values are artifact IDs, including references to user and group
  artifacts; they are not logins or group names. Inspect `allowedBlueprints`
  before selecting them.
- DATE values use an ISO-8601 datetime with timezone, for example
  `2026-06-01T00:00:00.000Z`. Uploaded files and time series use IDs from
  `upload_file` and `create_time_series`; see [Supporting objects](./supporting-objects.md).
- `required` is enforced on every artifact whatever the workflow step or the view.

For workflow transitions or approvals, follow [Signoffs](./signoffs.md). An artifact
field edit is not a substitute for submitting feedback or approval.
