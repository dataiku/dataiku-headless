---
name: fuzzyjoin-recipe-settings-and-payload-reference
description: "Settings and payload reference for fuzzy join recipes, including fuzzy-distance conditions, normalization options, projection, filters, and diagnostic flags."
---

# Fuzzy Join Recipe Settings And Payload Reference

Use this reference for `fuzzyjoin` payload edits (`get_recipe_settings` + `set_recipe_settings` action `set_payload`).

## Payload Model

A fuzzy join recipe payload is usually composed of these blocks:

- `joins`: join clauses between the two input tables.
- `selectedColumns`: output projection and optional aliases.
- `virtualInputs`: per-input options (pre-filters, projection mode, computed columns).
- `postFilter`: filter applied after join output is formed.
- `engineParams`: engine/runtime settings block.
- `withMetaColumn`: whether to emit fuzzy-match detail JSON in a `meta` column.
- `debugMode`: whether to force debug-style cross-join behavior.
- `resolvedSelectedColumns`, `computedColumns`: DSS-controlled/supporting fields.

Top-level payload matrix:

| Param | Required | Domain | Notes |
| --- | --- | --- | --- |
| `joins` | yes | `list<object>` | Join clauses between the two input tables. |
| `selectedColumns` | yes | `list<object>` | Output projection configuration. |
| `virtualInputs` | yes | `list<object>` | Per-input pre-filters and projection settings. |
| `engineParams` | no | `object` | Engine/runtime settings; preserve unless intentionally changing behavior. |
| `postFilter` | no | `object` | Post-join filter block. |
| `withMetaColumn` | no | `boolean` | Output fuzzy-match details in a `meta` column. |
| `debugMode` | no | `boolean` | Debug mode; forces cross-join-style exploration and enables meta output. |
| `resolvedSelectedColumns` | no | `list<object>` | DSS-resolved metadata; preserve when present. |
| `computedColumns` | no | `list<object>` | Optional global computed columns block. |

## `joins[]` Matrix

| Param | Required | Domain | Allowed values | Notes |
| --- | --- | --- | --- | --- |
| `table1` | yes | `integer` | Input table index | Left-side table index. |
| `table2` | yes | `integer` | Input table index | Right-side table index. |
| `conditionsMode` | yes | `enum` | `AND` | Boolean aggregator for `on[]`. |
| `type` | yes | `enum` | `INNER` \| `LEFT` \| `RIGHT` \| `FULL` | Join type selector. Live examples in this repo currently cover `LEFT`. |
| `on` | yes | `list<object>` | See `joins[].on[]` matrix | Fuzzy join conditions. |

### `joins[].on[]` Matrix

| Param | Required | Domain | Allowed values | Notes |
| --- | --- | --- | --- | --- |
| `column1` | yes | `object<column_ref>` | `{ "name": "...", "table": n }` | Left condition operand. |
| `column2` | yes | `object<column_ref>` | `{ "name": "...", "table": n }` | Right condition operand. |
| `fuzzyMatchDesc` | yes | `object` | See matrix below | Match-distance definition. |
| `normaliseDesc` | conditional | `object` | See matrix below | Text-normalization settings; observed only on text-distance examples. |

### `joins[].on[].fuzzyMatchDesc` Matrix

| Param | Required | Domain | Allowed values | Notes |
| --- | --- | --- | --- | --- |
| `distanceType` | yes | `enum` | Observed: `EXACT` \| `EUCLIDEAN` \| `LEVENSHTEIN` \| `HAMMING` \| `COSINE` \| `JACCARD` | Distance / matching mode. DSS docs also describe geospatial distance for geopoint columns. |
| `threshold` | yes | `number` | Non-negative number | Match threshold. |
| `relativeTo` | no | `enum` | Observed: `0` | Relative-threshold denominator selector. Preserve when present. DSS docs describe relative thresholds against either side. |

### `joins[].on[].normaliseDesc` Matrix

| Param | Required | Domain | Allowed values | Notes |
| --- | --- | --- | --- | --- |
| `unicodeCasting` | no | `boolean` | `true` \| `false` | Remove punctuation / extra-space style normalization behavior in observed payloads. |
| `clearSalutations` | no | `boolean` | `true` \| `false` | Remove salutations such as Mr / Dr in supported languages. |
| `sortAlphabetically` | no | `boolean` | `true` \| `false` | Alphabetically sort words before matching. |
| `caseInsensitive` | no | `boolean` | `true` \| `false` | Ignore case when matching text. |
| `language` | no | `string` | Observed: `english` | Language context for stop-word removal and stemming. |
| `clearStopWords` | no | `boolean` | `true` \| `false` | Remove stop words for the configured language. |
| `transformToStem` | no | `boolean` | `true` \| `false` | Stem words to base forms. |
| `normaliseText` | no | `boolean` | `true` \| `false` | General text normalization toggle in observed payloads. |

## Distance-Type Guidance

- `EXACT`: strict equality.
- `EUCLIDEAN`: numeric distance; DSS docs also describe relative thresholds for numeric columns.
- `LEVENSHTEIN`, `HAMMING`, `COSINE`, `JACCARD`: text-oriented fuzzy matching.
- Geopoint columns are documented to support geospatial distance, but that pattern is not represented in the current live example set for this repo. Inspect a live recipe first before writing it from scratch.

Practical guardrail:

- If using `EUCLIDEAN` on numeric columns, ensure the join-key columns do not contain nulls, or pre-filter those null rows first.

If all conditions are `EXACT` with zero thresholds, prefer a regular `join` recipe for performance unless the user explicitly wants fuzzy join.

## `selectedColumns[]` Matrix

| Param | Required | Domain | Notes |
| --- | --- | --- | --- |
| `name` | yes | `string<column_name>` | Source column name. |
| `table` | yes | `integer` | Source table index. |
| `type` | yes | `string` | Output type/meaning. |
| `alias` | no | `string<column_name>` | Optional output rename. |

## Handling Duplicate Column Names

When source datasets share column names, `AUTO_NON_CONFLICTING` mode silently drops duplicates. To control which source wins:

1. Set `outputColumnsSelectionMode: "MANUAL"` on the inputs with conflicting columns.
2. Explicitly list every desired column in `selectedColumns[]`, specifying the `table` index for each.
3. Any column name appearing in `selectedColumns[]` from only one table is unambiguous; columns listed from both tables will be disambiguated by table index.

```json
"virtualInputs": [
  {"index": 0, "outputColumnsSelectionMode": "MANUAL", ...},
  {"index": 1, "outputColumnsSelectionMode": "MANUAL", ...}
],
"selectedColumns": [
  {"name": "status", "table": 0, "type": "string"},
  {"name": "status", "table": 1, "type": "string", "alias": "status_right"}
]
```

Always call `get_dataset_info` on each input before building the fuzzy join payload to identify shared column names.

## `virtualInputs[]` Matrix

| Param | Required | Domain | Allowed values | Notes |
| --- | --- | --- | --- | --- |
| `index` | yes | `integer` | Input table index | Must align with input order. |
| `outputColumnsSelectionMode` | yes | `enum` | `AUTO_NON_CONFLICTING` \| `MANUAL` | Per-input projection mode. |
| `preFilter` | no | `object` | Filter payload | Filter before join for that input. |
| `computedColumns` | no | `list<object>` | Computed column definitions | Per-input computed columns. |
| `originLabel` | no | `string<any>` | Any string | DSS display label. |
| `prefix` | no | `string<any>` | Any string | Optional disambiguation prefix. |

### `virtualInputs[].computedColumns[]` Param Matrix

| Param | Required | Domain | Allowed values | Notes |
| --- | --- | --- | --- | --- |
| `mode` | yes | `enum` | `GREL` \| `SQL` | Expression engine. |
| `name` | yes | `string<column_name>` | Any valid output column name | Computed column name. |
| `expr` | yes | `string<any>` | Any formula/SQL expression | Column expression text. |
| `type` | yes | `string<meaning_or_storage_type>` | Any valid output type | Output type/meaning. |

## Join Filter Integration

Fuzzy join filters can be applied at two points:

1. Pre-join filter per input: `virtualInputs[i].preFilter`.
2. Post-join filter on joined rows: `postFilter`.

Filter block reference:

- [Filter payload reference](../../sampling/references/filter_payload.md)
- [Visual conditions params](../../references/visual_conditions_params.md)

These filter sections behave the same way as they do in the standard `join` recipe.

## Diagnostic Flags

### `withMetaColumn`

When `withMetaColumn=true`, DSS adds a `meta` column containing fuzzy-match details.

### `debugMode`

When `debugMode=true`, DSS activates a cross join and also enables meta-column generation. It can create very large outputs.

## Engine Support

Fuzzy join supports only the DSS engine.

## DSS UI Normalization Behavior

When a fuzzy join recipe is opened in the DSS UI, DSS compares the live payload against its own normalized form. Any difference triggers a "save" prompt even if the user made no changes. Avoid this by writing payloads that already match DSS's normalized form:

### Column ordering in `selectedColumns[]`

DSS reorders `selectedColumns` entries to match each input dataset's column order when the recipe is saved through the UI.

**Rule**: call `get_dataset_info` on every input dataset before building `selectedColumns[]`, and preserve source schema order.

### Always include top-level `computedColumns: []`

DSS adds `"computedColumns": []` at the top level of the payload on the first UI save if it is absent.

**Rule**: always include `"computedColumns": []` in every fuzzy join payload you write.

### `postFilter.$status` (DSS-managed, do not write)

DSS populates `postFilter.$status` with a cached schema object after a UI save. Do not include it when writing payloads.

### Summary checklist

| Concern | Rule |
| --- | --- |
| `selectedColumns[]` order | Match source dataset column order for each input |
| Top-level `computedColumns` | Always include `"computedColumns": []` |
| `postFilter.$status` | DSS-managed - omit from writes |

## Canonical Payload Examples

### Left fuzzy join with numeric distance and exact date match

```json
{
  "joins": [
    {
      "table1": 0,
      "table2": 1,
      "conditionsMode": "AND",
      "type": "LEFT",
      "on": [
        {
          "column1": {"name": "id", "table": 0},
          "column2": {"name": "id", "table": 1},
          "fuzzyMatchDesc": {
            "distanceType": "EUCLIDEAN",
            "relativeTo": 0,
            "threshold": 0.5
          }
        },
        {
          "column1": {"name": "signup_date", "table": 0},
          "column2": {"name": "signup_date", "table": 1},
          "fuzzyMatchDesc": {
            "distanceType": "EXACT",
            "threshold": 0
          }
        }
      ]
    }
  ],
  "selectedColumns": [
    {"name": "id", "table": 0, "type": "double"},
    {"name": "email", "table": 0, "type": "string"},
    {"name": "signup_date", "table": 0, "type": "dateonly"}
  ],
  "virtualInputs": [
    {"index": 0, "outputColumnsSelectionMode": "MANUAL", "preFilter": {"distinct": false, "enabled": false}, "computedColumns": []},
    {"index": 1, "outputColumnsSelectionMode": "AUTO_NON_CONFLICTING", "preFilter": {"distinct": false, "enabled": false}, "computedColumns": []}
  ],
  "withMetaColumn": false,
  "debugMode": false,
  "postFilter": {"distinct": false, "enabled": false},
  "computedColumns": []
}
```

### Left fuzzy join with text normalization

```json
{
  "joins": [
    {
      "table1": 0,
      "table2": 1,
      "conditionsMode": "AND",
      "type": "LEFT",
      "on": [
        {
          "column1": {"name": "full_name", "table": 0},
          "column2": {"name": "full_name", "table": 1},
          "fuzzyMatchDesc": {
            "distanceType": "HAMMING",
            "threshold": 2
          },
          "normaliseDesc": {
            "unicodeCasting": true,
            "clearSalutations": true,
            "sortAlphabetically": true,
            "caseInsensitive": true,
            "language": "english",
            "clearStopWords": true,
            "transformToStem": true,
            "normaliseText": true
          }
        }
      ]
    }
  ],
  "selectedColumns": [
    {"name": "full_name", "table": 0, "type": "string"},
    {"name": "email", "table": 0, "type": "string"}
  ],
  "virtualInputs": [
    {"index": 0, "outputColumnsSelectionMode": "MANUAL", "preFilter": {"distinct": false, "enabled": false}, "computedColumns": []},
    {"index": 1, "outputColumnsSelectionMode": "AUTO_NON_CONFLICTING", "preFilter": {"distinct": false, "enabled": false}, "computedColumns": []}
  ],
  "withMetaColumn": false,
  "debugMode": false,
  "postFilter": {"distinct": false, "enabled": false},
  "computedColumns": []
}
```

### Left fuzzy join with matching details enabled

```json
{
  "joins": [
    {
      "table1": 0,
      "table2": 1,
      "conditionsMode": "AND",
      "type": "LEFT",
      "on": [
        {
          "column1": {"name": "full_name", "table": 0},
          "column2": {"name": "full_name", "table": 1},
          "fuzzyMatchDesc": {
            "distanceType": "COSINE",
            "relativeTo": 0,
            "threshold": 0.5
          },
          "normaliseDesc": {
            "unicodeCasting": true,
            "clearSalutations": true,
            "sortAlphabetically": true,
            "caseInsensitive": true,
            "language": "english",
            "clearStopWords": true,
            "transformToStem": true,
            "normaliseText": true
          }
        }
      ]
    }
  ],
  "selectedColumns": [
    {"name": "full_name", "table": 0, "type": "string"},
    {"name": "email", "table": 0, "type": "string"}
  ],
  "virtualInputs": [
    {"index": 0, "outputColumnsSelectionMode": "MANUAL", "preFilter": {"distinct": false, "enabled": false}, "computedColumns": []},
    {"index": 1, "outputColumnsSelectionMode": "AUTO_NON_CONFLICTING", "preFilter": {"distinct": false, "enabled": false}, "computedColumns": []}
  ],
  "withMetaColumn": true,
  "debugMode": false,
  "postFilter": {"distinct": false, "enabled": false},
  "computedColumns": []
}
```
