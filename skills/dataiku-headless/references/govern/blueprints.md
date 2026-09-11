# Govern blueprint authoring

Use the connected `client` from [Govern](../govern.md). A blueprint stores identity
and presentation metadata. Its versions hold fields, workflow, views, hooks, and
actions. The ordinary blueprint handle is read-only; authoring uses the designer.
For a basic blueprint listing, use [Govern discovery](../govern.md#discover-blueprints).

## Inspect, fork, edit, publish

```python
designer = client.get_blueprint_designer()
blueprint = designer.get_blueprint(blueprint_id)
versions = [item.get_raw() for item in blueprint.list_versions()]
version = blueprint.get_version(version_id)
definition = version.get_definition()
raw = definition.get_raw()
trace = version.get_trace().get_raw()
signoff_configs = [item.get_raw() for item in version.list_signoff_configurations()]
```

Use discovered IDs. Prefer forking a suitable existing version of that blueprint
when changing its structure so required system fields and behavior survive:

```python
version = blueprint.create_version(
    new_identifier, name=version_name, origin_version_id=source_version_id
)
definition = version.get_definition()
raw = definition.get_raw()
# Apply the requested changes to raw, preserving the remaining definition.
definition.save()
saved = version.get_definition().get_raw()
```

Creation identifiers are bare names; returned handles carry the full IDs. For a
new blueprint, use `designer.create_blueprint(new_identifier, blueprint_metadata)`
without an `id` in the metadata body. Do not assume a system version exists on a
new blueprint or invent an origin ID.

A new version is DRAFT. Compare the saved definition with the intended edit, inspect
its signoff configurations, and publish when activation is part of the task:

```python
version.get_trace().set_status("ACTIVE")
status = version.get_trace().get_raw()["status"]
if status != "ACTIVE":
    raise RuntimeError("Blueprint version was not activated")
```

Keep `danger_zone_accepted` unset for normal saves. On a version used by artifacts,
removing fields or changing types can discard their data. A blocked save calls for
a new version or an explicit decision covering that data loss; do not automatically
retry with `danger_zone_accepted=True`. Deleting a version requires removing its
artifacts first; do not cascade-delete them just to unblock a schema operation.

## Definition structure

| Key | Purpose and checks |
| --- | --- |
| `id` | Preserve the `{blueprintId, versionId}` belonging to the target handle. |
| `fieldDefinitions` | Dictionary keyed by field ID; inspect `fieldType`, `sourceType`, and list/required constraints. See [Artifacts](./artifacts.md). |
| `workflowDefinition` | Contains ordered `stepDefinitions`; preserve stable step IDs referenced by signoffs and UI definitions. |
| `uiDefinition` | Layout structure varies by release: inspect `views`, `uiStepDefinitions`, and the artifact page or tab configuration. Workflow and UI step IDs must match. |
| `logicalHookList` | Lifecycle hooks; preserve phases and scripts when the task does not change them. |
| `actions` | Action definitions keyed by action ID; a UI action component must reference the action for it to be visible. |

An accepted definition can still render an empty artifact page. Check that the
configured artifact tabs/page and workflow steps resolve to nonempty views, and
editable fields appear in the intended views. Older definitions may use
`artifactPageViewId`; Govern 15 definitions can use `tabs` and
`artifactStructureTabIds` instead. Reuse components from a matching field type in
the inspected definition rather than inventing UI component names or adding legacy keys.
State separately whether layout was inspected in the UI or only checked structurally.

Required field constraints apply globally; hiding a required field does not make
it optional. A hidden workflow step can bypass its mandatory signoff. Review view
and step visibility conditions when they affect the requested approval behavior.

Use [Signoffs](./signoffs.md) for the separate signoff configuration API. Field and
workflow saves alone do not create review gates. For hook authoring, use the
target release's [Govern documentation](https://doc.dataiku.com/dss/latest/govern/index.html):
hooks run before commit, so avoid external side effects or API writes to neighboring
artifacts from a hook. Treat scripts as executable changes, not descriptive fields.

## Export and import boundary

A local JSON snapshot can include the full version definition, trace, and signoff
configurations read above. Keep it outside the plugin and protect any sensitive
content. A definition alone is not a complete transferable blueprint package.

The CLI assembles export envelopes itself and uses a private endpoint for import.
SDK 14.7.2 has no public blueprint-version import method. For a cross-instance import
or artifact-version migration, report the missing public operation and use the
Govern UI as the handoff unless the target SDK documents support. Do not reproduce
the CLI's private REST calls or claim that a JSON snapshot supplies import parity.
