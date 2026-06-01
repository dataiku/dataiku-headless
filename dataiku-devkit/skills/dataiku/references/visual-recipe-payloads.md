# Visual Recipe Payloads

JSON payload structure for configuring visual recipes beyond CLI flags. Use when `create-join`, `create-group`, etc. don't cover your configuration need.

## Why this file matters: every visual recipe is a 4-stage pipeline

Every visual recipe (Group, Window, Join, Distinct, TopN, Pivot) runs an internal pipeline. Picture the stages:

```
INPUT → preFilter → computedColumns → THE ACTION → postFilter → OUTPUT
                                       (group / window /
                                        join / topN / …)
```

Where they live in the payload:

| Stage | Group / Window / Distinct / TopN | Join |
|---|---|---|
| preFilter | top-level `preFilter` | per-input: `virtualInputs[i].preFilter` |
| computedColumns | top-level `computedColumns` (Group/Window/TopN; not Distinct) | per-input: `virtualInputs[i].computedColumns` |
| The action | `keys + values` (Group), `windows + values` (Window), `joins` (Join), `keys` (Distinct), `orders + topN` (TopN) | `joins[]` |
| postFilter | top-level `postFilter` | top-level `postFilter` |
| Output | top-level `outputColumnNameOverrides` (rename), `selectAllColumns` / `retrievedColumns` (project) | `selectedColumns` |

**Why this matters for migration and flow design:** a chain of `Filter → Prepare(formula) → Group → Filter` collapses into ONE Group recipe with `preFilter + computedColumns + values + postFilter` populated. That's 1 recipe + 1 output dataset instead of 4 recipes + 3 intermediate datasets — fewer artifacts, faster builds (one engine pass), and a flow that's actually readable. Always check whether the next recipe you're about to add could fit as a stage of the previous one.

The CLI shortcuts (`create-group`, `create-window`, `create-join`, …) only set up the action stage. The pre/computed/post stages require the read → edit → write payload pattern below.

> **Filter-mode gotcha — set `uiData.mode` to match the field you're populating:**
>
> - To use `uiData.conditions[]` (visual mode): set `uiData.mode: "&&"` or `"||"`
> - To use `expression` (formula mode): set `uiData.mode: "CUSTOM"` (the value DSS itself produces in the UI)
>
> Setting `expression` while `uiData.mode` is still `"&&"` makes DSS evaluate `conditions[]` (probably empty) and silently ignore your formula. Empirically verified on a Group recipe — see `visual-conditions.md` for the canonical CUSTOM-mode shape.

## Workflow: Read → Edit → Write

Always follow this pattern for payload updates:

```bash
# 1. Read current payload
dku recipe get-settings RECIPE -P PROJ -o json

# 2. Edit the payload fields you need (see schemas below)

# 3. Write back — shallow merge (default) or deep merge
dku recipe set-definition RECIPE --payload '{"field": "value"}' -P PROJ
dku recipe set-definition RECIPE --payload '{"nested": {"field": true}}' --deep-merge -P PROJ
```

**Use `--deep-merge`** when patching nested objects (filters, individual aggregations) to avoid losing sibling fields. Use default shallow merge for replacing top-level keys.

**Important:** `dku recipe get-settings` returns the full recipe object. The visual recipe config (joins, keys, values, filters) is inside the `payload` key — NOT at the top level. When reading settings for JSON manipulation:
```python
settings = json.load(...)        # full recipe object
payload = settings['payload']    # ← visual recipe config lives here
joins = payload['joins']         # e.g. for join recipes
```
When writing back with `set-definition --payload`, pass the payload contents directly (not wrapped in another `payload` key).

---

## Join Recipe

**CLI creates:** `dku recipe create-join NAME -i ds1 -i ds2 --output-ds out --join-key col -P PROJ`
**Use payload for:** Additional join conditions, pre/post-filters, column selection, unmatched outputs.

### Key Payload Fields

| Field | Type | Description |
|-------|------|-------------|
| `virtualInputs` | array | Input tables with preFilter, column selection |
| `joins` | array | Join conditions between tables |
| `postFilter` | object | Filter applied after join (see `visual-conditions.md`) |
| `selectedColumns` | object | Which columns to include per input |
| `computedColumns` | array | Columns computed from join results |
| `engineParams` | object | Execution engine settings |

### Join Condition Structure

```json
{
  "joins": [
    {
      "table1": 0,
      "table2": 1,
      "conditionsMode": "AND",
      "type": "LEFT",
      "outerJoinOnTheLeft": true,
      "on": [
        {
          "column1": {"name": "customer_id", "table": 0},
          "column2": {"name": "cust_id", "table": 1},
          "type": "EQ",
          "maxDistance": 0,
          "normalizeText": false,
          "strict": false
        }
      ]
    }
  ]
}
```

- `type`: `INNER`, `LEFT`, `RIGHT`, `FULL`, `CROSS`, `LEFT_ANTI`, `RIGHT_ANTI`, `ADVANCED`
- `on[].type`: `EQ` (exact), `LT`, `LTE`, `GT`, `GTE`, `NE`, `WITHIN_RANGE` (fuzzy/distance)
- `table1`/`table2`: 0-based index into `virtualInputs` array
- `selectedColumns[]`: `{"name": "col", "table": 0, "type": "string"}` — optional `alias` for rename. **Self-join trap:** when joining a dataset with itself (or any join where both sides have a same-named non-key column you need to keep both copies of), the default `outputColumnsSelectionMode: AUTO_NON_CONFLICTING` SILENTLY drops one side's column — output schema looks correct (no warning, no error) but rows of `right.X` collapse into `left.X` and you get only ONE column where you needed two. Fix: set `outputColumnsSelectionMode: MANUAL` on **both** `virtualInputs[]` and explicitly enumerate `selectedColumns` with `alias` for the conflicting names: `[{"name":"X","table":0,"alias":"left_X"},{"name":"X","table":1,"alias":"right_X"}]`. The CLI has no flag for this — read → edit → write the payload.
- `virtualInputs[]`: `index` (int), `outputColumnsSelectionMode` (`AUTO_NON_CONFLICTING` or `MANUAL`), `preFilter`, `computedColumns[]`

### Per-input Computed Columns (`virtualInputs[i].computedColumns`)

Use to derive columns **inside the Join recipe** instead of adding an upstream Prepare recipe per input. Verified shape (UI-built recipe round-trip):

```json
{
  "virtualInputs": [
    {
      "index": 0,
      "outputColumnsSelectionMode": "AUTO_NON_CONFLICTING",
      "preFilter": {"distinct": false, "enabled": false},
      "computedColumns": [
        {
          "mode": "GREL",
          "name": "grandparent_artifact_name",
          "expr": "artifact_name",
          "type": "string"
        },
        {
          "mode": "GREL",
          "name": "weighted_score",
          "expr": "score * weight",
          "type": "double"
        }
      ]
    }
  ]
}
```

Field meanings:
- `mode` — `"GREL"` (DSS formula language) or `"SQL"` (raw SQL pushdown). Note: `dataikuapi`'s `add_computed_column` docstring contains a `CUSTOM` typo — the actual on-disk value DSS produces is `GREL`, verified against UI-built joins.
- `name` — output column name (must not collide with input columns from this side).
- `expr` — formula (mode-dependent). GREL bareword `score` references an input column; quote with `numval("Sales Rep")` for hyphenated/spaced numeric columns.
- `type` — DSS column type (`string`, `double`, `bigint`, `boolean`, `date`, …) — lowercase.

Use cases:
- Join keys derived from a formula (e.g. `lower(strval("Customer ID"))` to normalize before equi-join).
- Per-row weights computed inline so a downstream Group can `SUM(weighted_score)` without an upstream Prepare.
- Renaming/recasting a single column in one input only — cheaper than a per-input AlteryxSelect-style Prepare.

The CLI doesn't have a flag for this — read → edit → write the payload via `set-definition --deep-merge`.

### Adding a Post-Filter to Existing Join

```bash
dku recipe set-definition my_join --payload '{
  "postFilter": {
    "enabled": true,
    "distinct": false,
    "uiData": {
      "mode": "&&",
      "conditions": [
        {"input": "amount", "operator": ">  [number]", "num": 0}
      ]
    }
  }
}' --deep-merge -P PROJ
```

---

## Group Recipe

**CLI creates:** `dku recipe create-group NAME -i ds --output-ds out -k col --agg 'amount:sum,avg' -P PROJ`
**Use payload for:** Additional aggregations, pre/post-filters, custom ordering for first/last.

### Key Payload Fields

| Field | Type | Description |
|-------|------|-------------|
| `keys` | array | Group-by columns: `[{"column": "col", "type": "string"}]` |
| `values` | array | Aggregated columns with flag-per-aggregation |
| `globalCount` | boolean | Add a `count` column per group |
| `preFilter` | object | Filter before grouping (see `visual-conditions.md`) |
| `postFilter` | object | Filter after grouping |
| `outputColumnNameOverrides` | object | Rename map: `{"amount_sum": "total_amount"}` |
| `engineParams` | object | Execution engine settings — preserve unless intentionally changing |

### Values (Aggregation) Structure

Each entry in `values[]`:

```json
{
  "column": "amount",
  "type": "double",
  "sum": true,
  "avg": true,
  "count": false,
  "countDistinct": false,
  "min": false,
  "max": false,
  "first": false,
  "last": false,
  "firstLastNotNull": false,
  "stddev": false,
  "concat": false,
  "concatDistinct": false,
  "$idx": 0
}
```

Set aggregation flags to `true`/`false`. For `first`/`last`/`firstLastNotNull`, also set `orderColumn` for deterministic ordering. **`orderColumn` also applies to `concat` and `concatDistinct`** — without it, concat output row order is engine-dependent (Snowflake `LISTAGG` without `WITHIN GROUP`, Postgres `STRING_AGG` without `ORDER BY`). `concatSeparator` (default `,`) sets the join string. CLI: `--agg-order col=order_col` and `--agg-separator col=','` on `create-group`.

### Custom aggregations (SQL expressions in `values[]`)

The same `values[]` array also accepts **custom aggregation entries** — arbitrary SQL aggregate expressions. They're distinguished from standard entries by having `customExpr` + `customName` instead of `column` + boolean flags:

```json
{
  "customExpr": "min(\"quantity\")",
  "customName": "custom_aggr_1",
  "type": "INT"
},
{
  "customExpr": "min(AAAA)",
  "customName": "custom_aggr_2",
  "type": "DOUBLE"
}
```

**This is the "Custom aggregations" panel from the DSS UI.** Use it for any aggregation not exposed by the boolean flags — `MAX(amount) - MIN(amount)`, `PERCENTILE_CONT(0.95)`, `STRING_AGG(...)`, conditional aggregations like `SUM(CASE WHEN ... THEN amount ELSE 0 END)`, etc.

**Critical pipeline insight:** custom aggregations can reference `computedColumns` by name. In the example above, `min(AAAA)` aggregates over the `AAAA` column that was just derived in the `computedColumns` stage. So **`computedColumns → custom aggregation` is a single-recipe pattern** for "compute a per-row derived value, then aggregate it" — no upstream Prepare recipe needed.

**Mechanics:**
- `customExpr` is SQL — column names go in double quotes (`"quantity"`) or unquoted if simple (`AAAA`). Format depends on the target SQL engine; the `$status.sql` field after save shows the compiled push-down SQL.
- `type` is the output column SQL type, uppercase: `INT`, `BIGINT`, `DOUBLE`, `STRING`, etc. (note: standard aggregations use lowercase `bigint`/`double` — custom ones use uppercase. UI artifact.)
- `customName` becomes the output column name. Cannot collide with standard-aggregation auto-names (`<col>_<func>`) or `keys[].column` names.
- Custom aggregations require a SQL engine — they don't run in the in-memory DSS engine.

### Read-only metadata fields (`$`-prefixed)

DSS embeds several metadata fields in saved payloads. They're read-only as far as evaluation is concerned (DSS regenerates them on save), but **preserve them when you read-modify-write** so the UI round-trips correctly.

#### `$status` — validation block (the "is this recipe correctly configured?" check)

Every filter slot (preFilter / postFilter) and the recipe itself can carry a `$status` block populated by DSS during validation. Read it after `set-settings` to confirm a recipe is actually wired up correctly **before** running it.

| Field | Type | Meaning | Use it to… |
|-------|------|---------|------------|
| `validated` | boolean | DSS finished validating the configuration | Detect whether validation has actually run yet (false = stale write, hasn't been re-checked) |
| `ok` | boolean | The configuration is valid overall | The single yes/no check after a write — gate downstream steps on this |
| `fullyTranslated` | boolean | All expressions translated to the target engine | Catch silent push-down gaps — `ok: true, fullyTranslated: false` means part of the formula falls back to the in-memory engine, breaking SQL-only flows |
| `message` | string | Last validation message — may be a parse error, warning, or just info | Read when `ok: false`. **Caveat: can be stale** — observed on a working recipe whose `message` still complained about a long-fixed parse error from earlier UI edits |
| `sql` | string | Compiled SQL pushed down to the engine | Authoritative source for "what is this filter actually running" — see `dku-cli/references/recipe-survey.md` § Debugging tip |
| `schema` (postFilter only) | object | Output schema as DSS sees it after the recipe action | Confirms which columns are available to filter against in `postFilter` (custom-aggregation `customName`s, `globalCount`'s `count`, etc.) |

**Programmatic post-write check:**

```bash
# After dku recipe set-settings, verify the recipe is OK before running
dku recipe get-settings g_orders -P PROJ -o json \
  | jq '.payload | {pre: .preFilter."$status".ok, post: .postFilter."$status".ok}'
# → {"pre": true, "post": true}  → safe to run
# → either false                 → read .message before running
```

#### `$idx` — entry ordering in `values[]`

Each entry in a Group recipe's `values[]` carries a `$idx` integer (0, 1, 2, …) reflecting its UI display order. DSS regenerates these on save, but **preserve them when re-writing the array** to avoid the UI re-shuffling rows on next open. New entries you append should get a `$idx` higher than any existing one.

#### `$latestOperator` / `$filterOptions` — UI mode-toggle round-tripping

Inside a filter's `uiData`, two UI-housekeeping fields:
- `$latestOperator` — `"&&"` or `"||"` — the visual-mode operator the user last had set, kept around so toggling away from `"CUSTOM"` mode and back restores their original choice.
- `$filterOptions` — mirrors `mode` (typically `"CUSTOM"` when in formula mode).

Neither affects evaluation. Preserve them on read-modify-write; you can omit them when constructing a fresh filter from scratch (DSS will populate them on the next UI open).

#### `$showList` — per-condition UI hint

Inside `uiData.conditions[i]`. Boolean. Controls whether the UI shows a "list of values" picker for that condition. Doesn't affect filter evaluation; preserve on round-trip.

#### `distinct` — filter + dedupe in a single stage

The `distinct` flag inside a filter object (`preFilter.distinct`, `postFilter.distinct`) is **not metadata — it changes evaluation**. When `true`, the filter ALSO drops duplicate rows from the output. Use to fold a "filter then distinct" pair into one operation. Default `false`. Visible in the DSS UI as the "Distinct" checkbox in the filter panel.

### Output column controls

| Field | Type | Description |
|-------|------|-------------|
| `outputColumnNameOverrides` | object | Rename standard auto-named outputs: `{"amount_sum": "total_amount"}` (does not apply to custom aggregations — they use `customName` directly) |
| `selectAllColumns` | boolean | When `true`, also project every input column straight through (no aggregation). When `false`, output contains only `keys` + the values entries that have a flag set or a `customExpr` |
| `globalCount` | boolean | Add a `count` column per group (rows-per-group). Set `false` for SQL/PROC SQL/Summarize parity |
| `enlargeYourBits` | boolean | Promote int aggregation outputs to bigint to avoid overflow. Default `true` — keep it unless you have a specific reason to widen behaviour |

### Adding an Aggregation to Existing Group

```bash
# Read current, then deep-merge a new values entry
# Note: deep merge on arrays REPLACES the array — for arrays, do a full read-edit-write cycle
dku recipe get-settings my_group -P PROJ -o json
# ... add to values[] array manually ...
dku recipe set-definition my_group --payload @updated_payload.json -P PROJ
```

---

## Window Recipe

**CLI creates:** `dku recipe create-window NAME -i ds --output-ds out -k grp --order-key date --compute 'rowNumber::rn' -P PROJ`
**Use payload for:** Multiple windows, additional computations, lag/lead, custom frame bounds.

### Key Payload Fields

| Field | Type | Description |
|-------|------|-------------|
| `windows` | array | Window definitions with partition/ordering/limits |
| `values` | array | Per-column computation flags |
| `preFilter` | object | Filter before windowing |
| `postFilter` | object | Filter after windowing |
| `rowNumber` | boolean | Add ROW_NUMBER column |
| `rank` | boolean | Add RANK column |
| `denseRank` | boolean | Add DENSE_RANK column |
| `cumeDist` | boolean | Add CUME_DIST column |
| `ntile` | boolean | Add NTILE column |
| `ntileValues` | string | Comma-separated list of N for NTILE (e.g. `"4,10"` to add quartile + decile columns). Required when `ntile: true`. |
| `globalAggregations` | array | Window-wide aggregates that run AFTER the per-row window. Same `{column, sum, avg, …, $idx}` shape as `values[]`. Use to compute "fraction of grand total" without a downstream Group + Join. |
| `legacyUnboundedWindowStreamBehavior` | boolean | Compatibility flag for windows on streamed (non-SQL) inputs. Defaults `false` on new recipes; only present on recipes copied from very old projects. |
| `retrievedColumnsSelectionMode` | string | `ALL` (default) or `EXPLICIT`. With `EXPLICIT`, set `retrievedColumns: [{column: "x", value: true}, ...]` — output drops every column with `value: false`. Replaces a downstream Prepare ColumnsSelector. |

### Window Definition Structure

Each entry in `windows[]`:

```json
{
  "enablePartitioning": true,
  "partitioningColumns": ["customer_id"],
  "enableOrdering": true,
  "orders": [{"column": "order_date", "desc": false}],
  "enableLimits": false,
  "windowLowerBound": {"unbounded": true},
  "windowUpperBound": {"unbounded": true}
}
```

- `enablePartitioning`: MUST be `true` for `partitioningColumns` to take effect
- `enableOrdering`: MUST be `true` for `orders` to take effect
- `enableLimits`: Enable frame bounds (ROWS BETWEEN ... AND ...)
- `windowLowerBound`/`windowUpperBound`: `{"unbounded": true}` or `{"offset": N}`

### Values (Computation) Structure

Each entry in `values[]`:

```json
{
  "column": "amount",
  "sum": true,
  "avg": false,
  "min": false,
  "max": false,
  "count": false,
  "first": false,
  "last": false,
  "lag": false,
  "lead": false,
  "lagDiff": false,
  "leadDiff": false,
  "concatDistinct": false,
  "$idx": 0
}
```

For `lag`/`lead`: set `lagValues`/`leadValues` (comma-separated offset strings, e.g. `"1,2"`) and provide ordering via `orderColumn`. For `first`/`last`: also set `orderColumn` for deterministic results.

### Adding Row Number + Rank to Existing Window

```bash
dku recipe set-definition my_window --payload '{"rowNumber": true, "rank": true}' --deep-merge -P PROJ
```

---

## Filter Recipe

**CLI creates:** `dku recipe create-filter NAME -i ds --output-ds out --filter-formula "price > 100" -P PROJ`
**Use payload for:** Visual conditions (not formula-based), complex AND/OR groups.

### Key Payload Fields

| Field | Type | Description |
|-------|------|-------------|
| `filterCondition` | object | The filter condition (see `visual-conditions.md`) |

### Visual Condition Mode

```json
{
  "filterCondition": {
    "enabled": true,
    "distinct": false,
    "uiData": {
      "mode": "&&",
      "conditions": [
        {"input": "status", "operator": "== [string]", "string": "active"},
        {"input": "age", "operator": ">= [number]", "num": 18}
      ]
    }
  }
}
```

### Formula Mode

```json
{
  "filterCondition": {
    "enabled": true,
    "expression": "price > 100 && category == 'Electronics'"
  }
}
```

When `expression` is set, it takes precedence over `uiData.conditions`.

---

## TopN Recipe

**CLI creates:** `dku recipe create-topn NAME -i ds --output-ds out --n 10 --rank-by col:desc -P PROJ`
**Use payload for:** Partition keys (top N per group), additional sort columns.

### Key Payload Fields

| Field | Type | Description |
|-------|------|-------------|
| `topN` | integer | Display value (shown in UI) |
| `firstRows` | integer | Actual row limit |
| `keys` | array | Partition columns (string array, NOT dict array): `["customer_id"]` |
| `orders` | array | Sort order: `[{"column": "price", "desc": true}]` |
| `preFilter` | object | Filter before TopN |
| `postFilter` | object | Filter after TopN |

Note: TopN `keys` is a **string array** (unlike Group/Window which use `[{"column": "col"}]` dict arrays).

### Canonical Example

```json
{
  "topN": 5,
  "firstRows": 5,
  "keys": ["department"],
  "orders": [{"column": "salary", "desc": true}]
}
```

`firstRows` (top-N) is mutually exclusive with `lastRows` (bottom-N). Set the
unused one to 0. `rank` / `denseRank` / `rowNumber` / `duplicateCount` are
top-level booleans that emit ranking columns alongside the kept rows.
`retrievedColumnsSelectionMode: "SELECTED"` + `retrievedColumns: [...]`
projects the output (avoids a downstream Prepare). `outputColumnNameOverrides`
renames generated columns.

---

## Stack Recipe (`vstack`)

Vertically concatenates 2+ inputs. Five `mode` values:

- `"UNION"` (default): output schema = superset of all input columns.
- `"INTERSECT"`: only columns present in ALL inputs.
- `"FROM_DATASET"` + `copySchemaFromDatasetWithName: "<input name>"`: copy schema from one named input.
- `"FROM_INDEX"` + `selectedColumnsIndexes: ["<N>"]`: copy schema from input at position N. Useful when input names are templated (e.g. `${TENANT}_X`) and a name reference would break across environments.
- `"REMAP"` + `selectedColumns: [...]` + per-`virtualInputs[i].columnsMatch[]`: define a custom output schema and positionally align each input's source columns to it. Eliminates N upstream `ColumnRenamer` recipes.

Per-input pre-filter: `virtualInputs[i].preFilter.{enabled,distinct,uiData}` (same shape as Join's). Per-input rename label for the origin column: `virtualInputs[i].originLabel`. Top-level `addOriginColumn: true` + `originColumnName` writes a "source" column. Top-level `selectedColumns` projects the output. `postFilter` runs after the union.

```json
{
  "mode": "REMAP",
  "selectedColumns": ["id", "amount", "date"],
  "virtualInputs": [
    {"originLabel": "orders", "columnsMatch": ["order_id", "total", "order_date"]},
    {"originLabel": "sales",  "columnsMatch": ["sale_id", "price", "sold_at"]}
  ],
  "addOriginColumn": true,
  "originColumnName": "source"
}
```

`FROM_INDEX:N` example payload:
```json
{
  "mode": "FROM_INDEX",
  "selectedColumnsIndexes": ["0"],
  "copySchemaFromDatasetWithName": "<dataset name at position 0>",
  "selectedColumns": []
}
```

---

## Sort Recipe (`sort`)

Sort-only is `payload.orders[]`. Sort recipes carry the same 4-stage pipeline
as Group/Window: `preFilter → computedColumns → orders → postFilter`, plus
top-level `rank` / `denseRank` / `rowNumber` boolean flags that emit ranking
columns alongside the sorted rows. `outputColumnNameOverrides` renames any
generated column (e.g. `rank → priority_rank`).

A Sort with `rank: true` and no row cap is essentially a 1-window TopN.

```json
{
  "orders": [{"column": "revenue", "desc": true}],
  "rank": true,
  "denseRank": false,
  "rowNumber": false,
  "preFilter": {"enabled": false},
  "computedColumns": [],
  "postFilter": {"enabled": false},
  "outputColumnNameOverrides": {}
}
```

---

## Distinct Recipe (`distinct`)

Default behavior: deduplicate on ALL columns of the input (matches `df.drop_duplicates()`). Pass `keys: [{column: …}]` to dedup on a subset; pair with `selectAllColumns: true` so all original columns are still emitted (otherwise DSS silently projects to just the key columns — a footgun).

```json
{
  "keys": [{"column": "customer_id"}, {"column": "order_date"}],
  "selectAllColumns": true,
  "globalCount": false,
  "preFilter": {"enabled": false},
  "postFilter": {"enabled": false},
  "computedColumns": [],
  "outputColumnNameOverrides": {}
}
```

---

## Split Recipe (`split`)

`payload.mode` ∈ `{"VALUES", "RANDOM", "RANGE", "FILTERS", "CENTILE", "RANDOM_COLUMNS"}`.
Note: the payload key is `"FILTERS"` (plural) even though the `--mode` flag and the dataikuapi enum are `FILTER`. The CLI maps `FILTER` → `"FILTERS"` automatically; only relevant if you hand-write the payload.

| Mode | Required fields | Notes |
|---|---|---|
| VALUES | `column`, `valueSplits[].{outputIndex,value}` | Discriminator-column mode (one row per match → its `outputIndex` bucket). |
| RANDOM | `randomSplits[].{outputIndex,share}`, `seed` | Percent shares per output, sum to ≤ 100. |
| RANGE | `column`, `rangeSplits[].{outputIndex,min?,max?,include_min,include_max}`, `rangeSetTime: false` | Numeric range bucketing. |
| FILTERS | `filterSplits[].{outputIndex, filter:{uiData}}` | Per-output GREL formula (rows matching → that bucket). |
| CENTILE | `centileOrders[].{column,desc}`, `centileSplits[].{outputIndex,share}`, `centileTDigest`, `centileShuffle` | Centile-based partitioning. |

Common shared fields: `defaultOutputIndex` (catch-all bucket for unmatched rows), `seed`, `computedColumns`, `writeComputedColumnsInOutput`, `preFilter`, `postFilter`.

---

## Update Recipe (`update`) — UPSERT

Maintains an existing target dataset by merging rows from the input on a
unique key. Migration target: SQL `MERGE`, Alteryx Append Fields, SAS
`proc append`. Config lives under `recipe.params` (NOT in the JSON
payload — different from the SQL-only `upsert` recipe type which keys on
`payload.keys`).

```json
{
  "params": {
    "uniqueKey": ["customer_id"],
    "addMissingRows": true,
    "deleteMissingRows": false,
    "addMissingCols": true,
    "deleteMissingCols": false,
    "filter": {"distinct": false, "enabled": false}
  }
}
```

Output dataset MUST already exist — Update operates in-place. CLI:
`dku recipe create-update NAME -i delta --output-ds master --unique-key customer_id`.

---

## Extract Failed Rows Recipe (`extract_failed_rows`)

Quarantines rows that violated checks defined on the input dataset. Migration target: Alteryx Data Cleansing fail-bucket, SAS `PROC SQL VALIDATE`.

`payload.columnRules[].{ruleColumn, ruleId, isSelected}` — references rules defined in the **input dataset's** `checks[]`. Use `dku dq list-checks DATASET -P PROJ` to discover ruleIds. Empty `columnRules[]` extracts failures for ALL enabled rules.

```json
{
  "columnRules": [
    {"ruleColumn": "customer_id", "ruleId": "customer_id_not_null", "isSelected": true},
    {"ruleColumn": "email", "ruleId": "email_format_regex", "isSelected": true}
  ]
}
```

---

## Geo Join Recipe (`geojoin`)

Spatial joins. `payload.joins[i].{table1, table2, type, on, geoJoin, geoOperator, geoDistance, geoUnit, geoColumn1, geoColumn2, rightLimit}`.

`geoOperator`: `WITHIN_DISTANCE`, `BEYOND_DISTANCE`, `INTERSECTS`, `CONTAINS`. Distance + unit only used for `*_DISTANCE`. `type`: `LEFT`, `INNER`, `RIGHT`, `FULL`.

`rightLimit.{enabled, maxMatches, type}` caps right-side matches per left row. `type` ∈ `{KEEP_LARGEST, KEEP_SMALLEST, KEEP_FIRST, KEEP_LAST}`. **Default `enabled: false` → INTERSECTS can fan out left rows when N polygons intersect.** Set `enabled: true` + `maxMatches: 1` + `type: KEEP_LARGEST` for the typical "tag each store with its census tract" pattern.

```json
{
  "joins": [{
    "table1": 0,
    "table2": 1,
    "type": "LEFT",
    "geoJoin": true,
    "geoOperator": "INTERSECTS",
    "rightLimit": {"enabled": true, "maxMatches": 1, "type": "KEEP_LARGEST"}
  }]
}
```

---

## Pivot Recipe (`pivot`) — additional fields

Beyond the basic `pivots[0].{keyColumns, valueColumns}`:

- `otherColumns[]` — auto-aggregations on columns that aren't a row-key, column-key, or value column. Same `{column, last, first, sum, ...}` boolean schema as Group's `values[]`. Common pattern with timestamped sensor data: `{column: "equipment_id", type: "string", last: true, orderColumn: "timestamp"}` carries the most recent equipment_id through the pivot.
- `customAggregates[]` — like Group's, GREL or SQL expressions per column.
- `computedColumns[]` — input transforms applied before pivoting.
- `identifierColumnsSelection`: `"AUTO"` (DSS infers from non-pivoted columns) or `"EXPLICIT"` + `explicitIdentifiers: [...]`.
- `valueLimit` ∈ `{"TOP_N", "NO_LIMIT", "AT_LEAST_N_OCC", "EXPLICIT"}`. **Use `"EXPLICIT"` (NOT `"EXPLICIT_VALUES"`)** — the wrong spelling silently falls back to `TOP_N` with `topnLimit=20`, truncating the modality whitelist. With `"EXPLICIT"`, also set `pivots[0].explicitValues` as an **array of single-element arrays**: `[["2024"], ["2025"]]`. The flat form `["2024", "2025"]` is also silently ignored. CLI: `--value-limit EXPLICIT --explicit-values 2024 --explicit-values 2025`.
- `modalitySlugification` ∈ `{"NONE", "SOFT_SLUGIFY", "HARD_SLUGIFY"}` — controls generated column names. `SOFT_SLUGIFY` is the UI default.
- `sortModalities: bool` — sort generated column ordering.

A "count-only pivot" (no value column, just a cross-tab of counts) sets `valueColumns: []` + `globalCount: true` — distinct from `valueColumns: [{count: true}]` which adds an explicit count column.

**Output column naming.** DSS auto-names pivot output columns `<modality>_<value-col>_<agg>` (e.g. `HBO_active_base_flg_max`). To get bare modality names (e.g. `HBO`) — common when migrating SAS PROC TRANSPOSE or Alteryx CrossTab whose downstream code references unmodified modality names — chain a Prepare with `add-rename --mappings '{"HBO_active_base_flg_max":"HBO", ...}'` (one bulk step). `payload.outputColumnNameOverrides` is read by Group/Window/TopN but NOT by Pivot (the `dku recipe create-pivot --rename` flag writes the field correctly, but DSS Pivot ignores it). Pin the modality set with `--value-limit EXPLICIT --explicit-values m1 --explicit-values m2 …` when the source migration specifies the wanted modalities (e.g. SAS `keep=` clause); avoids drifting columns when input data adds new values.

---

## List Folder Contents Recipe (`list_folder_contents`)

Built-in DSS recipe (NOT a plugin) that emits one row per file in a managed folder. Migration target: Alteryx Directory tool, SAS `dopen()`/`pipe ls`.

`recipe.params` (NOT payload):
```json
{
  "path": true,
  "basename": true,
  "extension": true,
  "size": true,
  "lastModified": true,
  "levelMapping": []
}
```

`levelMapping` exposes parent-folder names as columns (one entry per level). The exact inner shape isn't fully reverse-engineered yet — set it via `dku recipe set-settings` if you need it; CLI flag coverage is intentionally limited.

`new_recipe()` does NOT dispatch this type — use raw `create_recipe(proto, {"rawCreation": True})` if you're building it via the Python API. CLI: `dku recipe create-list-folder-contents`.

---

## Merge Folder Recipe (`merge_folder`)

Built-in DSS folder-to-folder recipe — combines files from N source folders into one destination. Migration target: Alteryx Output-to-Folder with multiple branches.

`recipe.params`:
```json
{
  "clearBeforeCopy": true,
  "conflictHandling": "OVERWRITE"
}
```

`conflictHandling` ∈ `{"OVERWRITE", "SKIP", "FAIL"}` decides what happens when the same path exists in multiple sources. Same `new_recipe()` caveat as `list_folder_contents`. CLI: `dku recipe create-merge-folder -i F1 -i F2 --output-folder OUT`.

---

## Common Patterns

### Pre/Post Filters (All Visual Recipes)

Every visual recipe supports `preFilter` (before operation) and `postFilter` (after operation). See `references/visual-conditions.md` for the full condition schema.

```bash
# Add a pre-filter to any visual recipe
dku recipe set-definition RECIPE --payload '{
  "preFilter": {
    "enabled": true,
    "uiData": {"mode": "&&", "conditions": [{"input": "status", "operator": "== [string]", "string": "active"}]}
  }
}' --deep-merge -P PROJ
```

### Engine Params

Most visual recipes have `engineParams` controlling execution engine (DSS, Spark, SQL). Generally leave unchanged unless you need to force a specific engine.

### Array Fields Require Full Replacement

`--deep-merge` works recursively on dicts but **replaces arrays entirely**. For array fields (`values[]`, `keys[]`, `joins[]`, `orders[]`), always do a full read-edit-write cycle:

```bash
# 1. Read current settings
dku recipe get-settings RECIPE -P PROJ -o json > /tmp/settings.json

# 2. Edit the array in /tmp/settings.json

# 3. Write back the full payload
dku recipe set-definition RECIPE --payload @/tmp/payload.json -P PROJ
```
