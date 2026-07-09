---
name: sync-recipe-settings-and-payload-reference
description: "Settings and payload reference for sync recipes, including schema mode controls from params."
---

# Sync Recipe Settings And Payload Reference

Use this reference for `sync` recipe edits (`get_recipe_settings` + `set_recipe_settings` action `set_params`).

## Observed Settings Shape

In these recipes:

- `params` controls sync behavior.
- `payload` is an empty object (`{}`).

Observed top-level `params` keys:

- `schemaMode`
- `forcePipelineableForTests`
- `engineParams`

## Params Matrix

| Param | Required | Domain | Notes |
| --- | --- | --- | --- |
| `schemaMode` | yes | `enum` | Observed values: `STRICT_SYNC`, `FREE_SCHEMA_NAME_BASED`. |
| `forcePipelineableForTests` | no | `boolean` | Observed default: `false`; keep unchanged unless test-specific work is requested. |
| `engineParams` | no | `object` | Engine/runtime block; preserve unless explicitly changing execution behavior. |

## `schemaMode` Semantics (Observed)

| `schemaMode` | Practical effect |
| --- | --- |
| `STRICT_SYNC` | Keep output schema strictly aligned with sync operation expectations. |
| `FREE_SCHEMA_NAME_BASED` | Allow schema matching by column names with more flexibility. |

## Engine Params Guidance

`engineParams` contains nested engine/runtime configuration blocks (for example Spark SQL, Hive, Impala, SQL pipeline, container selection).

Safe rule:

- keep the existing `engineParams` object unchanged unless the user explicitly asks for engine behavior changes.

## Canonical Params Examples

### Strict schema sync

```json
{
  "schemaMode": "STRICT_SYNC",
  "forcePipelineableForTests": false,
  "engineParams": {
    "...": "preserve existing engine params"
  }
}
```

### Name-based flexible schema sync

```json
{
  "schemaMode": "FREE_SCHEMA_NAME_BASED",
  "forcePipelineableForTests": false,
  "engineParams": {
    "...": "preserve existing engine params"
  }
}
```

## Recommended Update Pattern

1. Read current settings with `get_recipe_settings`.
2. Copy current `params`.
3. Edit only intended keys (usually `schemaMode`).
4. Write full `params` with `set_recipe_settings` action `set_params` and `merge=false`.
5. Re-read settings to confirm only intended keys changed.
