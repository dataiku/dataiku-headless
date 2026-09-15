# Govern blueprint authoring

Use the `govern` tool described in [Govern](../govern.md). A blueprint stores identity
and presentation metadata. Its versions hold fields, workflow, views, hooks, and
actions. Blueprint design operations need blueprint designer rights on the API key.

## Inspect, fork, edit, publish

Inspect with `get_blueprint`, `list_blueprint_versions`, `get_blueprint_version`
(definition plus trace), and `list_signoff_configurations`.

Prefer forking a suitable existing version when changing the structure, so the
required system fields and behavior survive:

1. `create_blueprint_version` with `blueprint_id`, `new_identifier`, `name`, and
   `origin_version_id`. The new version is DRAFT and invisible to users.
2. `get_blueprint_version` and edit the returned `definition` locally, preserving
   everything not requested.
3. `update_blueprint_version` with the complete `definition`. Leave
   `danger_zone_accepted` unset.
4. `create_signoff_configuration` per gated step; see [Signoffs](./signoffs.md).
5. `set_blueprint_version_status` to `ACTIVE` when activation is part of the task.
   Check `trace.status` in the result.

For a new blueprint, `create_blueprint` with `new_identifier` and a `blueprint`
body holding `name`, `icon`, `color`, and `backgroundColor`, without an `id`. Do
not assume a system version exists on a new blueprint or invent an origin ID.
`update_blueprint` replaces that metadata only.

On a version used by artifacts, removing fields or changing types blocks the save.
A blocked save calls for a new version or an explicit decision covering that data
loss; do not retry with `danger_zone_accepted: true` on your own. Deleting a
version (`delete_blueprint_version`) requires removing its artifacts first; do not
cascade-delete them just to unblock a schema operation.

## Definition structure

| Key | Purpose and checks |
| --- | --- |
| `id` | Preserve the `{blueprintId, versionId}` of the target version. |
| `fieldDefinitions` | Dictionary keyed by field ID; inspect `fieldType`, `sourceType`, and list or required constraints. See [Artifacts](./artifacts.md). |
| `workflowDefinition` | Contains ordered `stepDefinitions`; preserve stable step IDs referenced by signoffs and UI definitions. |
| `uiDefinition` | Layout structure varies by release: inspect `views`, `uiStepDefinitions`, and the artifact page or tab configuration. Workflow and UI step IDs must match. |
| `logicalHookList` | Pre-phase hooks for validation and computed fields before commit. |
| `postLogicalHookList` | Govern 15 post-phase hooks for work after commit. Preserve both hook lists when editing unrelated settings. |
| `actions` | Action definitions keyed by action ID; a UI action component must reference the action for it to be visible. |

An accepted definition can still render an empty artifact page. Check that the
configured artifact tabs or page and workflow steps resolve to nonempty views, and
that editable fields appear in the intended views. Older definitions may use
`artifactPageViewId`; Govern 15 definitions can use `tabs` and
`artifactStructureTabIds` instead. The optional `customRightPanel` and
`rightPanelTabIds` configure the selection panel independently. A custom tab can
be shared by the artifact page and right panel; its ID and view remain shared.
System tabs such as Workflow, Timeline, and Role assignments belong only on the
artifact page. Preserve stable tab IDs used in navigation, and check both orders
and separators. See [page structure](https://doc.dataiku.com/dss/latest/governance/blueprint-designer/blueprint-version-design.html#design-the-item-page-structure).

Reuse components from an inspected definition rather than inventing UI keys.
Govern 15 text components have separate display settings (Markdown or plain text)
and editor settings (rich text, single-line, or multiline); configure these on the
view component without changing the field's `TEXT` type. State separately whether
layout was inspected in the UI or only checked structurally.

Required field constraints apply globally; hiding a required field does not make
it optional. A hidden workflow step can bypass its mandatory signoff. Review view
and step visibility conditions when they affect the requested approval behavior.

Field and workflow saves alone do not create review gates; use the signoff
configuration operations in [Signoffs](./signoffs.md).

## Choose the hook phase

Hooks select lifecycle events (`CREATE`, `UPDATE`, `DELETE`) and when to run:

- Pre-phase hooks run before commit. Use them to validate changes or populate
  computed fields. The operation can still fail afterward; keep external side
  effects and API writes to other items out of these hooks. To schedule related
  items' UPDATE hooks after commit, use `handler.artifactIdsToUpdate`.
- Govern 15 post-phase hooks run after commit. Use them for work that requires
  persisted state, such as an authorized notification or external synchronization.
  They cannot validate or veto an action that has already committed. Check the
  saved item and any downstream effect separately before retrying.

Use the target release's [hook documentation and editor samples](https://doc.dataiku.com/dss/latest/governance/blueprint-designer/blueprint-version-design.html#set-rules-with-hooks)
for the handler context. Older examples may emulate post-create work with threads
and polling; use native post-phase hooks on Govern 15 when that is the intent.
Treat scripts as executable changes, and verify execution as well as saved configuration.

## Export and import boundary

A local JSON snapshot can hold the full version definition, trace, and signoff
configurations read above. Keep it outside the plugin and protect sensitive content.
A definition alone is not a complete transferable blueprint package.

The catalog has no blueprint version import operation, because the public SDK has
none. For a cross-instance import or artifact-version migration, report the missing
operation and use the Govern UI as the handoff. Do not claim that a JSON snapshot
supplies import parity.
