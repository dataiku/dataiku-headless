---
name: geojoin-recipe-settings-and-payload-reference
description: "Settings and payload reference for geo join recipes, including geospatial join predicates, projection, and filters."
---

# Geo Join Recipe Settings And Payload Reference

Use this reference for `geojoin` payload edits (`get_recipe_settings` + `set_recipe_settings` action `set_payload`).

Geo join follows the same overall payload model as the standard `join` recipe for join structure, pre/post filters, and selected columns; the main difference is the geospatial condition model inside `joins[].on[]`.

## Payload Model

A geo join recipe payload is usually composed of these blocks:

- `joins`: join clauses between table indices.
- `selectedColumns`: output projection and optional aliases.
- `virtualInputs`: per-input options (pre-filters, projection mode, computed columns).
- `postFilter`: filter applied after join output is formed.
- `engineParams`: engine/runtime settings block.
- `resolvedSelectedColumns`, `computedColumns`: DSS-controlled/supporting fields.

Top-level payload matrix:

| Param | Required | Domain | Notes |
| --- | --- | --- | --- |
| `joins` | yes | `list<object>` | Join clauses between input tables. |
| `selectedColumns` | yes | `list<object>` | Output projection configuration. |
| `virtualInputs` | yes | `list<object>` | Per-input pre-filters and projection settings. |
| `engineParams` | no | `object` | Engine/runtime settings; preserve unless intentionally changing behavior. |
| `postFilter` | no | `object` | Post-join filter block. |
| `resolvedSelectedColumns` | no | `list<object>` | DSS-resolved metadata; preserve when present. |
| `computedColumns` | no | `list<object>` | Optional global computed columns block. |

## `joins[]` Matrix

| Param | Required | Domain | Allowed values | Notes |
| --- | --- | --- | --- | --- |
| `table1` | yes | `integer` | Input table index | Left-side table index. |
| `table2` | yes | `integer` | Input table index | Right-side table index. |
| `conditionsMode` | yes | `enum` | `AND` | Boolean aggregator for `on[]`. |
| `type` | yes | `enum` | `INNER` \| `LEFT` \| `RIGHT` \| `FULL` \| `CROSS` | Join type selector. Geo join supports the same join-type family as the standard `join` recipe. |
| `on` | yes | `list<object>` | See `joins[].on[]` matrix | Geospatial join conditions. |

### `joins[].on[]` Matrix

| Param | Required | Domain | Allowed values | Notes |
| --- | --- | --- | --- | --- |
| `column1` | yes | `object<column_ref>` | `{ "name": "...", "table": n }` | Left condition operand; must use a `geopoint` or `geometry` type column. |
| `column2` | yes | `object<column_ref>` | `{ "name": "...", "table": n }` | Right condition operand; must use a `geopoint` or `geometry` type column. |
| `type` | yes | `enum` | Observed: `CONTAINS` \| `DISJOINT` \| `DWITHIN` \| `BEYOND` \| `EQ` \| `INTERSECTS` \| `TOUCHES` \| `WITHIN` | Geospatial predicate. Do not guess beyond the observed set without a live reference recipe. |
| `unit` | conditional | `enum` | Observed: `METER` \| `KILOMETER` \| `MILE` \| `YARD` \| `FOOT` \| `NAUTICAL_MILE` | Distance unit. Observed in every live example, including topological predicates. Preserve unless intentionally changing behavior. |
| `threshold` | conditional | `number` | Non-negative number | Distance threshold. Observed in every live example. |
| `dateDiffUnit` | no | `enum` | Observed: `SECOND` | DSS/shared payload field observed in every live example. Preserve when present. |

Predicate meanings:

- `DISJOINT`: is disjoint from
- `WITHIN`: is contained within
- `BEYOND`: is beyond distance of
- `EQ`: is strictly equal to
- `CONTAINS`: contains
- `DWITHIN`: is within distance of
- `TOUCHES`: touches
- `INTERSECTS`: intersects

## Geospatial Column Expectations

Geo join operands must be geospatial columns (`geopoint` or `geometry`). If the user asks to geo-join columns that are not of type `geopoint` or `geometry`, first use a prepare recipe to create them. A prepare recipe can auto-cast string columns containing valid geopoint or geometry values as proper `geopoint` or `geometry` types, convert latitude/longitude scalar columns to a `geopoint` column with the `GeoPointCreator` processor, and more.

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

Always call `get_dataset_info` on each input before building the geo join payload to identify shared column names and preserve source schema order.

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

Geo join filters can be applied at two points:

1. Pre-join filter per input: `virtualInputs[i].preFilter`.
2. Post-join filter on joined rows: `postFilter`.

Filter block reference:

- [Filter payload reference](../../sampling/references/filter_payload.md)
- [Visual conditions params](../../references/visual_conditions_params.md)

These filter sections behave the same way as they do in the standard `join` recipe:

- `virtualInputs[i].preFilter` uses the same filter payload model as standard join pre-filters.
- `postFilter` uses the same filter payload model as standard join post-filters.
- Rules-mode, formula-mode, and SQL-mode filtering follow the same shared filter references.

## Selected Columns Behavior

Geo join uses the same selected-columns model as the standard `join` recipe:

- `selectedColumns[]` controls the output projection.
- `virtualInputs[].outputColumnsSelectionMode` uses the same `AUTO_NON_CONFLICTING` and `MANUAL` modes.
- Duplicate-column handling, aliasing, and manual projection patterns are the same as standard join.
- Source column order should still be preserved to avoid DSS UI normalization diffs.

## DSS UI Normalization Behavior

When a geo join recipe is opened in the DSS UI, DSS compares the live payload against its own normalized form. Any difference triggers a "save" prompt even if the user made no changes. Avoid this by writing payloads that already match DSS's normalized form:

### Column ordering in `selectedColumns[]`

DSS reorders `selectedColumns` entries to match each input dataset's column order when the recipe is saved through the UI. If you write them in a different order, DSS will detect a diff and prompt to save.

**Rule**: call `get_dataset_info` on every input dataset before building `selectedColumns[]`, and preserve the order columns appear in each source schema.

### Always include top-level `computedColumns: []`

DSS adds `"computedColumns": []` at the top level of the payload on the first UI save if it is absent. Omitting it causes DSS to detect a diff on the next open.

**Rule**: always include `"computedColumns": []` in every geo join payload you write.

### `postFilter.$status` (DSS-managed, do not write)

DSS populates `postFilter.$status` with a cached schema object after a UI save. This field is not needed in writes - DSS manages it automatically. Do not include it when writing payloads; its presence or absence does not trigger a save prompt.

### Summary checklist

| Concern | Rule |
| --- | --- |
| `selectedColumns[]` order | Match source dataset column order for each input |
| Top-level `computedColumns` | Always include `"computedColumns": []` |
| `postFilter.$status` | DSS-managed - omit from writes |

## Canonical Payload Examples

### Left geo join with distance threshold (`DWITHIN`)

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
          "column1": {"name": "pickup_geopoint", "table": 0},
          "column2": {"name": "store_geopoint", "table": 1},
          "type": "DWITHIN",
          "unit": "METER",
          "threshold": 100,
          "dateDiffUnit": "SECOND"
        }
      ]
    }
  ],
  "selectedColumns": [
    {"name": "order_id", "table": 0, "type": "bigint"},
    {"name": "pickup_geopoint", "table": 0, "type": "geopoint"},
    {"name": "store_id", "table": 1, "type": "bigint"}
  ],
  "virtualInputs": [
    {"index": 0, "outputColumnsSelectionMode": "MANUAL", "preFilter": {"distinct": false, "enabled": false}, "computedColumns": []},
    {"index": 1, "outputColumnsSelectionMode": "MANUAL", "preFilter": {"distinct": false, "enabled": false}, "computedColumns": []}
  ],
  "postFilter": {"distinct": false, "enabled": false},
  "computedColumns": []
}
```

### Right geo join with containment (`CONTAINS`)

```json
{
  "joins": [
    {
      "table1": 0,
      "table2": 1,
      "conditionsMode": "AND",
      "type": "RIGHT",
      "on": [
        {
          "column1": {"name": "region_geometry", "table": 0},
          "column2": {"name": "site_geopoint", "table": 1},
          "type": "CONTAINS",
          "unit": "METER",
          "threshold": 100,
          "dateDiffUnit": "SECOND"
        }
      ]
    }
  ],
  "selectedColumns": [
    {"name": "region_id", "table": 0, "type": "string"},
    {"name": "site_id", "table": 1, "type": "string"}
  ],
  "virtualInputs": [
    {"index": 0, "outputColumnsSelectionMode": "MANUAL", "preFilter": {"distinct": false, "enabled": false}, "computedColumns": []},
    {"index": 1, "outputColumnsSelectionMode": "AUTO_NON_CONFLICTING", "preFilter": {"distinct": false, "enabled": false}, "computedColumns": []}
  ],
  "postFilter": {"distinct": false, "enabled": false},
  "computedColumns": []
}
```

### Inner geo join with exclusion distance (`BEYOND`)

```json
{
  "joins": [
    {
      "table1": 0,
      "table2": 1,
      "conditionsMode": "AND",
      "type": "INNER",
      "on": [
        {
          "column1": {"name": "customer_geopoint", "table": 0},
          "column2": {"name": "warehouse_geopoint", "table": 1},
          "type": "BEYOND",
          "unit": "NAUTICAL_MILE",
          "threshold": 1,
          "dateDiffUnit": "SECOND"
        }
      ]
    }
  ],
  "selectedColumns": [
    {"name": "customer_id", "table": 0, "type": "bigint"},
    {"name": "warehouse_id", "table": 1, "type": "bigint"}
  ],
  "virtualInputs": [
    {"index": 0, "outputColumnsSelectionMode": "AUTO_NON_CONFLICTING", "preFilter": {"distinct": false, "enabled": false}, "computedColumns": []},
    {"index": 1, "outputColumnsSelectionMode": "AUTO_NON_CONFLICTING", "preFilter": {"distinct": false, "enabled": false}, "computedColumns": []}
  ],
  "postFilter": {"distinct": false, "enabled": false},
  "computedColumns": []
}
```
