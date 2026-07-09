---
name: prepare-recipe-settings-and-payload-reference
description: "Settings and payload reference for shaker (prepare) recipes."
---

# Prepare Recipe Settings And Payload Reference

Use this reference for `shaker` (prepare) payload edits (`get_recipe_settings` + `set_recipe_settings` action `set_payload`).

## Payload Model

A Prepare recipe payload contains `steps` that are ordered arrays of processors.

## Shared Step Envelope for All Processors

Each `steps[]` entry usually has:

- `type`: processor type name (required)
- `params`: processor parameters (required; shape comes from matching processor reference)
- `metaType`: typically `PROCESSOR` (often set by DSS)
- `preview`: optional boolean
- `disabled`: optional boolean
- `comment`: optional human note
- `alwaysShowComment`: optional UI hint

Envelope fields reference:

| Field | Required | Domain | Allowed values | Notes |
| --- | --- | --- | --- | --- |
| `type` | yes | `string<any>` | Any valid processor type name | Must map to a processor reference. |
| `params` | yes | `object<any>` | Any object matching the selected processor reference param matrix | Read shared scope params every time when resolving `params`. |
| `metaType` | no | `enum` | `PROCESSOR` | Standard DSS step marker. Preserve unless DSS sets otherwise. |
| `preview` | no | `boolean` | `true` \| `false` | Preview-only execution toggle. |
| `disabled` | no | `boolean` | `true` \| `false` | Step disabled state. |
| `comment` | no | `string<any>` | Any text string | Human-readable note about step intent. |
| `alwaysShowComment` | no | `boolean` | `true` \| `false` | UI behavior for comment visibility. |

Canonical step envelope:

```json
{
  "preview": false,
  "metaType": "PROCESSOR",
  "disabled": false,
  "comment": "Optional human note",
  "type": "ProcessorTypeHere",
  "params": {},
  "alwaysShowComment": true
}
```

## `params` Resolution Rule

1. Read `type` in the step envelope.
2. Open the matching processor reference.
3. Read [shared scope params (`appliesTo`, `columns`)](shared_scope_params.md) for every step.
4. If the processor is formula-based (for example `CreateColumnWithGREL`, `FlagOnCustomFormula`, `FilterOnCustomFormula`, `FormulaToNumber`), read [shared formula language](dataiku_formula_language.md).
5. Treat the processor reference param matrix plus required shared references as the source of truth for `params`.
