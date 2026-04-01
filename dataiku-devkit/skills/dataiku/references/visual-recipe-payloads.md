# Visual Recipe Payloads

JSON payload structure for configuring visual recipes beyond CLI flags. Use when `create-join`, `create-group`, etc. don't cover your configuration need.

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
- `selectedColumns[]`: `{"name": "col", "table": 0, "type": "string"}` — optional `alias` for rename
- `virtualInputs[]`: `index` (int), `outputColumnsSelectionMode` (`AUTO_NON_CONFLICTING` or `MANUAL`), `preFilter`, `computedColumns[]`

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

Set aggregation flags to `true`/`false`. For `first`/`last`/`firstLastNotNull`, also set `orderColumn` for deterministic ordering.

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
| `retrievedColumnsSelectionMode` | string | `ALL` or `EXPLICIT` |

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
