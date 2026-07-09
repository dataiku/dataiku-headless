---
name: join-recipe-settings-and-payload-reference
description: "Settings and payload reference for join recipes, including join clauses, projection, filters, and unmatched output roles."
---

# Join Recipe Settings And Payload Reference

Use this reference for `join` payload edits (`get_recipe_settings` + `set_recipe_settings` action `set_payload`).

## Payload Model

A join recipe payload is usually composed of these blocks:

- `joins`: join clauses between table indices.
- `selectedColumns`: output projection and optional aliases.
- `virtualInputs`: per-input options (pre-filters, projection mode, computed columns).
- `postFilter`: filter applied after join output is formed.
- `engineParams`: engine/runtime settings block.
- `resolvedSelectedColumns`, `computedColumns`, `enableAutoCastInJoinConditions`: DSS-controlled/supporting fields.

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
| `enableAutoCastInJoinConditions` | no | `boolean` | Auto-cast toggle for join conditions. |

## `joins[]` Matrix

| Param | Required | Domain | Allowed values | Notes |
| --- | --- | --- | --- | --- |
| `table1` | yes | `integer` | Input table index | Left-side table index. |
| `table2` | yes | `integer` | Input table index | Right-side table index. |
| `conditionsMode` | yes | `enum` | `AND` | Boolean aggregator for `on[]`. |
| `type` | yes | `enum` | `INNER` \| `LEFT` \| `RIGHT` \| `FULL` \| `LEFT_ANTI` \| `RIGHT_ANTI` \| `CROSS` \| `ADVANCED` | Join type selector. |
| `on` | yes | `list<object>` | See `joins[].on[]` matrix | Join conditions. |
| `outerJoinOnTheLeft` | no | `boolean` | `true` \| `false` | DSS orientation flag. |
| `rightLimit` | conditional | `object` | Advanced join limit policy | Used with advanced joins. |

### `joins[].on[]` Matrix

| Param | Required | Domain | Allowed values | Notes |
| --- | --- | --- | --- | --- |
| `column1` | yes | `object<column_ref>` | `{ "name": "...", "table": n }` | Left condition operand. |
| `column2` | yes | `object<column_ref>` | `{ "name": "...", "table": n }` | Right condition operand. |
| `type` | yes | `enum` | `EQ` \| `WITHIN_RANGE` \| `LT` \| `LTE` \| `GT` \| `GTE` \| `NE` | Comparator. |
| `dateDiffUnit` | no | `enum` | `DAY` \| `SECOND` | Date/window-aware joins. |
| `windowFrom` | no | `integer` | Any integer | Lower bound for window matching. |
| `windowTo` | no | `integer` | Any integer | Upper bound for window matching. |
| `maxMatches` | no | `integer` | Positive integer | Per-row match cap hint. |
| `caseInsensitive` | no | `boolean` | `true` \| `false` | Text comparator toggle. |
| `normalizeText` | no | `boolean` | `true` \| `false` | Text normalization toggle. |
| `maxDistance` | no | `integer` | Non-negative integer | Tolerance for compatible comparators. |
| `strict` | no | `boolean` | `true` \| `false` | Strict comparator behavior. |

### `rightLimit` (Advanced Join) Param Matrix

| Param | Required | Domain | Allowed values | Notes |
| --- | --- | --- | --- | --- |
| `enabled` | yes | `boolean` | `true` \| `false` | Activates right-side limiting behavior. |
| `type` | yes | `enum` | Example: `KEEP_LARGEST` | Limiting policy. |
| `maxMatches` | yes | `integer` | Positive integer | Maximum matches to keep. |
| `strict` | no | `boolean` | `true` \| `false` | Strict limiting behavior. |
| `decisionColumn` | yes | `object<column_ref>` | `{ "name": "...", "table": n }` | Column used to choose kept matches. |

## `selectedColumns[]` Matrix

| Param | Required | Domain | Notes |
| --- | --- | --- | --- |
| `name` | yes | `string<column_name>` | Source column name. |
| `table` | yes | `integer` | Source table index. |
| `type` | yes | `string` | Output type/meaning. |
| `alias` | no | `string<column_name>` | Optional output rename. |

## Handling Duplicate Column Names

When source datasets share column names (e.g., both have a `STATUS` column), `AUTO_NON_CONFLICTING` mode silently drops duplicates. To control which source wins:

1. Set `outputColumnsSelectionMode: "MANUAL"` on the inputs with conflicting columns.
2. Explicitly list every desired column in `selectedColumns[]`, specifying the `table` index for each.
3. Any column name appearing in `selectedColumns[]` from only one table is unambiguous; columns listed from both tables will be disambiguated by table index.

```json
"virtualInputs": [
  {"index": 0, "outputColumnsSelectionMode": "MANUAL", ...},
  {"index": 1, "outputColumnsSelectionMode": "MANUAL", ...}
],
"selectedColumns": [
  {"name": "STATUS", "table": 0, "type": "string"},
  {"name": "AMOUNT", "table": 1, "type": "double"}
]
```

Always call `get_dataset_info` on each input before building the join payload to identify shared column names.

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

## Join Output Roles (`create_recipe.outputs[].role`)

Use these role values for join outputs:

- `main`: primary joined output.
- `unmatchedLeft`: unmatched rows from the left side.
- `unmatchedRight`: unmatched rows from the right side.

Role source: `dataikuapi.dss.recipe.DSSJoinRecipeSettings.set_unmatched_output`.

Important semantics:

- These outputs represent unmatched rows from one input dataset, not rows from the main join output where right- or left-side projected columns are null.
- For outer joins, the built-in unmatched output is side-constrained by DSS.
- If the user wants unmatched rows from the preserved side of an outer join, that is a different requirement and generally needs an additional downstream recipe rather than the built-in unmatched toggle.

## Valid Unmatched Output Roles By Join Type

Use this matrix before configuring `create_recipe.outputs[].role` or `set_recipe_settings` outputs.

| Join type | Preserved side in main output | Valid unmatched output roles | Notes |
| --- | --- | --- | --- |
| `LEFT` | Left | `unmatchedRight` only | Right-side lookup rows with no left match. |
| `RIGHT` | Right | `unmatchedLeft` only | Left-side lookup rows with no right match. |
| `INNER` | None | `unmatchedLeft`, `unmatchedRight`, or both | Either side may emit unmatched rows. |
| `FULL` | Both | Require live verification before use | Do not assume built-in unmatched role behavior from this reference alone. |
| `LEFT_ANTI` | Left unmatched only | Do not configure extra unmatched outputs | The recipe itself already represents unmatched-left semantics. |
| `RIGHT_ANTI` | Right unmatched only | Do not configure extra unmatched outputs | The recipe itself already represents unmatched-right semantics. |
| `CROSS` | N/A | Unsupported | No meaningful unmatched-side concept. |
| `ADVANCED` | Depends on config | Require live verification before use | Do not assume unmatched-role support from this reference alone. |

Explicit warning:

- `LEFT` join plus `unmatchedLeft` is invalid.
- `RIGHT` join plus `unmatchedRight` is invalid.
- "Left join unmatched `job_postings` rows" is not the same thing as `unmatchedRight` when `job_postings` is the left input; in that case the requested rows are on the preserved side and are not what the built-in unmatched toggle emits.

## Join Filter Integration

Join filters can be applied at two points:

1. Pre-join filter per input: `virtualInputs[i].preFilter`.
2. Post-join filter on joined rows: `postFilter`.

Filter block reference:

- [Filter payload reference](../../sampling/references/filter_payload.md)
- [Visual conditions params](../../references/visual_conditions_params.md)

## Canonical Join Type Matrix

| Join type | Behavior |
| --- | --- |
| `INNER` | Keep rows with matches on both sides. |
| `LEFT` | Keep all left rows; match right when available. |
| `RIGHT` | Keep all right rows; match left when available. |
| `FULL` | Keep all rows from both sides. |
| `LEFT_ANTI` | Keep left rows with no right match. |
| `RIGHT_ANTI` | Keep right rows with no left match. |
| `CROSS` | Cartesian-style join configuration. |
| `ADVANCED` | Advanced matching with optional right-side limiting policy. |

Interpretation note:

- The left and right sides are determined by input order and `joins[].table1` / `joins[].table2`, not by dataset importance or naming.
- When the user asks for unmatched rows, resolve the dataset side first, then apply the valid unmatched-role matrix above.

## DSS UI Normalization Behavior

When a join recipe is opened in the DSS UI, DSS compares the live payload against its own normalized form. Any difference triggers a "save" prompt even if the user made no changes. Avoid this by writing payloads that already match DSS's normalized form:

### Column ordering in `selectedColumns[]`

DSS reorders `selectedColumns` entries to match each input dataset's column order when the recipe is saved through the UI. If you write them in a different order, DSS will detect a diff and prompt to save.

**Rule**: call `get_dataset_info` on every input dataset before building `selectedColumns[]`, and preserve the order columns appear in each source schema.

### Always include top-level `computedColumns: []`

DSS adds `"computedColumns": []` at the top level of the payload on the first UI save if it is absent. Omitting it causes DSS to detect a diff on the next open.

**Rule**: always include `"computedColumns": []` in every join payload you write.

### `postFilter.$status` (DSS-managed, do not write)

DSS populates `postFilter.$status` with a cached schema object after a UI save. This field is not needed in writes — DSS manages it automatically. Do not include it when writing payloads; its presence or absence does not trigger a save prompt.

### Summary checklist

| Concern | Rule |
| --- | --- |
| `selectedColumns[]` order | Match source dataset column order for each input |
| Top-level `computedColumns` | Always include `"computedColumns": []` |
| `postFilter.$status` | DSS-managed — omit from writes |

## Canonical Payload Examples

### Inner join with one equality key

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
          "column1": {"name": "id", "table": 0},
          "column2": {"name": "id", "table": 1},
          "type": "EQ"
        }
      ]
    }
  ],
  "selectedColumns": [
    {"name": "id", "table": 0, "type": "bigint"},
    {"name": "status", "table": 1, "type": "string"}
  ],
  "virtualInputs": [
    {"index": 0, "outputColumnsSelectionMode": "AUTO_NON_CONFLICTING", "preFilter": {"distinct": false, "enabled": false}, "computedColumns": []},
    {"index": 1, "outputColumnsSelectionMode": "AUTO_NON_CONFLICTING", "preFilter": {"distinct": false, "enabled": false}, "computedColumns": []}
  ],
  "postFilter": {"distinct": false, "enabled": false},
  "computedColumns": []
}
```

### Left join with valid right-side unmatched output

This configuration keeps all rows from the left dataset in the main output and sends unmatched right-side rows to a secondary dataset.

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
          "column1": {"name": "required_education", "table": 0},
          "column2": {"name": "education_level", "table": 1},
          "type": "EQ"
        }
      ]
    }
  ],
  "selectedColumns": [
    {"name": "job_id", "table": 0, "type": "bigint"},
    {"name": "required_education", "table": 0, "type": "string"},
    {"name": "median_weekly_earnings_usd", "table": 1, "type": "int"}
  ],
  "virtualInputs": [
    {"index": 0, "outputColumnsSelectionMode": "AUTO_NON_CONFLICTING", "preFilter": {"distinct": false, "enabled": false}, "computedColumns": []},
    {"index": 1, "outputColumnsSelectionMode": "MANUAL", "preFilter": {"distinct": false, "enabled": false}, "computedColumns": []}
  ],
  "postFilter": {"distinct": false, "enabled": false}
}
```

Output roles for this example:

- `main` -> joined left-preserving output
- `unmatchedRight` -> right-side rows with no left match

### Right join with valid left-side unmatched output

This configuration keeps all rows from the right dataset in the main output and sends unmatched left-side rows to a secondary dataset.

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
          "column1": {"name": "education_level", "table": 0},
          "column2": {"name": "required_education", "table": 1},
          "type": "EQ"
        }
      ]
    }
  ],
  "selectedColumns": [
    {"name": "education_level", "table": 0, "type": "string"},
    {"name": "job_id", "table": 1, "type": "bigint"},
    {"name": "required_education", "table": 1, "type": "string"}
  ],
  "virtualInputs": [
    {"index": 0, "outputColumnsSelectionMode": "MANUAL", "preFilter": {"distinct": false, "enabled": false}, "computedColumns": []},
    {"index": 1, "outputColumnsSelectionMode": "AUTO_NON_CONFLICTING", "preFilter": {"distinct": false, "enabled": false}, "computedColumns": []}
  ],
  "postFilter": {"distinct": false, "enabled": false}
}
```

Output roles for this example:

- `main` -> joined right-preserving output
- `unmatchedLeft` -> left-side rows with no right match

### Inner join with unmatched outputs on both sides

This configuration keeps only matched rows in the main output and can emit unmatched rows from both inputs.

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
          "column1": {"name": "id", "table": 0},
          "column2": {"name": "id", "table": 1},
          "type": "EQ"
        }
      ]
    }
  ],
  "selectedColumns": [
    {"name": "id", "table": 0, "type": "bigint"},
    {"name": "status", "table": 1, "type": "string"}
  ],
  "virtualInputs": [
    {"index": 0, "outputColumnsSelectionMode": "AUTO_NON_CONFLICTING", "preFilter": {"distinct": false, "enabled": false}, "computedColumns": []},
    {"index": 1, "outputColumnsSelectionMode": "AUTO_NON_CONFLICTING", "preFilter": {"distinct": false, "enabled": false}, "computedColumns": []}
  ],
  "postFilter": {"distinct": false, "enabled": false}
}
```

Possible output roles for this example:

- `main`
- `unmatchedLeft`
- `unmatchedRight`

### Non-example: invalid unmatched-side configuration

Do not treat this as valid:

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
          "column1": {"name": "required_education", "table": 0},
          "column2": {"name": "education_level", "table": 1},
          "type": "EQ"
        }
      ]
    }
  ]
}
```

With output role:

```json
{"name": "unmatched_rows", "role": "unmatchedLeft"}
```

Reason:

- For `LEFT` joins, `unmatchedLeft` is incompatible with DSS unmatched-output semantics.
- If the user wants left-side rows whose right-side columns are null, create a downstream recipe instead of using the built-in unmatched output.

### Advanced join with right-side limiting

```json
{
  "joins": [
    {
      "table1": 0,
      "table2": 1,
      "conditionsMode": "AND",
      "type": "ADVANCED",
      "rightLimit": {
        "enabled": true,
        "type": "KEEP_LARGEST",
        "maxMatches": 1,
        "strict": true,
        "decisionColumn": {"name": "value_num", "table": 1}
      },
      "on": [
        {
          "column1": {"name": "group_key", "table": 0},
          "column2": {"name": "group_key", "table": 1},
          "type": "EQ"
        }
      ]
    }
  ]
}
```

### Three-table join with manual projection and alias

```json
{
  "joins": [
    {
      "table1": 0,
      "table2": 1,
      "conditionsMode": "AND",
      "type": "INNER",
      "on": [
        {"column1": {"name": "group_key", "table": 0}, "column2": {"name": "group_key", "table": 1}, "type": "EQ"}
      ]
    },
    {
      "table1": 0,
      "table2": 2,
      "conditionsMode": "AND",
      "type": "LEFT",
      "on": [
        {"column1": {"name": "group_key", "table": 0}, "column2": {"name": "group_key", "table": 2}, "type": "EQ"}
      ]
    }
  ],
  "selectedColumns": [
    {"name": "id_a", "table": 0, "type": "bigint"},
    {"name": "group_key", "table": 1, "type": "string", "alias": "group_key_b"},
    {"name": "event_date", "table": 2, "type": "dateonly"}
  ],
  "virtualInputs": [
    {"index": 0, "outputColumnsSelectionMode": "AUTO_NON_CONFLICTING", "preFilter": {"distinct": false, "enabled": false}},
    {"index": 1, "outputColumnsSelectionMode": "MANUAL", "preFilter": {"distinct": false, "enabled": false}},
    {"index": 2, "outputColumnsSelectionMode": "AUTO_NON_CONFLICTING", "preFilter": {"distinct": false, "enabled": false}}
  ]
}
```

### Join with post-join filter

```json
{
  "postFilter": {
    "uiData": {
      "mode": "&&",
      "$latestOperator": "&&",
      "$filterOptions": "rules",
      "conditions": [
        {"input": "amount", "operator": ">  [number]", "num": 0}
      ]
    },
    "$status": {},
    "distinct": false,
    "enabled": true
  }
}
```

### Join with pre-join filter on one input

```json
{
  "virtualInputs": [
    {
      "index": 0,
      "outputColumnsSelectionMode": "AUTO_NON_CONFLICTING",
      "preFilter": {
        "uiData": {
          "mode": "&&",
          "$latestOperator": "&&",
          "$filterOptions": "rules",
          "conditions": [
            {"input": "id", "operator": ">  [number]", "num": 0}
          ]
        },
        "$status": {},
        "distinct": false,
        "enabled": true
      }
    },
    {
      "index": 1,
      "outputColumnsSelectionMode": "AUTO_NON_CONFLICTING",
      "preFilter": {"distinct": false, "enabled": false}
    }
  ]
}
```
