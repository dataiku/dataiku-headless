# Visual recipe payloads

Durable JSON shapes for configuring visual recipes beyond the `create-*` flags.
Get flags from `--help`; open this only for payload shapes.

## Read → edit → write

```bash
dku --format json recipe get-settings R -P PROJ          # full recipe object; config is under `payload`
dku recipe set-definition R --payload '{...}' -P PROJ              # shallow merge (replaces top-level keys)
dku recipe set-definition R --payload '{...}' --deep-merge -P PROJ  # merge nested objects
```

`--deep-merge` merges dicts but **replaces arrays entirely** — for any array
field (`values[]`, `keys[]`, `joins[]`, `orders[]`) do a full read-edit-write.
When writing back, pass the `payload` contents directly (not re-wrapped).

In `get-settings` JSON output, `payload` arrives **already parsed** (an object)
for visual recipes — no `jq fromjson` / `json.loads` step (that raw-dataikuapi
habit raises "only strings can be parsed"). Code recipes return it as a string
(the script body).

Engine only: `dku recipe set-engine R --engine SQL -P PROJ` — no payload
surgery needed.

## The 4-stage pipeline

`INPUT → preFilter → computedColumns → ACTION → postFilter → OUTPUT`. Where
each stage lives:

| Stage | Group / Window / Distinct / TopN / Sort | Join |
|---|---|---|
| preFilter | top-level `preFilter` | per-input `virtualInputs[i].preFilter` |
| computedColumns | top-level `computedColumns` | per-input `virtualInputs[i].computedColumns` |
| action | `keys`+`values` / `windows`+`values` / `keys` / `orders`+`topN` / `orders` | `joins[]` |
| postFilter | top-level `postFilter` | top-level `postFilter` |
| output | `outputColumnNameOverrides`, `selectAllColumns` | `selectedColumns` |

`engineType` is a TOP-LEVEL field (`DSS|SQL|SPARK_SQL|IMPALA|HIVE`), distinct
from `engineParams.<engine>.executionEngine` — `engineType` wins. Preserve
`$`-prefixed metadata (`$status`, `$idx`, `$latestOperator`, `$filterOptions`,
`$showList`) on round-trip; DSS regenerates them. `distinct:true` inside a
filter object is NOT metadata — it dedupes the output in the same stage.

## Visual conditions (shared filter schema)

Used in filter `filterCondition`, every recipe's pre/postFilter, Split
conditions, Prepare VisualIfRule.

> **Never filter rows with the Sampling recipe.** Its natural-looking
> `uiData.expression` is silently rewritten to `{mode:"CUSTOM",conditions:[]}` — a
> match-all no-op. To keep rows matching a condition use `create-filter` (Prepare +
> `FilterOnCustomFormula`, below). Use `create-sampling` only for actual sampling.

```json
{"enabled": true, "distinct": false,
 "uiData": {"mode": "&&", "conditions": [
   {"input": "status", "operator": "== [string]", "string": "active"},
   {"input": "age",    "operator": ">= [number]", "num": 18}]}}
```

**`uiData.mode` selects which field DSS evaluates** — the central trap:

| mode | evaluates | syntax |
|---|---|---|
| `"&&"` / `"\|\|"` | `uiData.conditions[]` | per-condition objects (AND/OR) |
| `"CUSTOM"` | top-level `expression` | GREL (`val("col") != 0`); every engine |
| `"SQL"` | top-level `expression` | raw SQL (`"col" = 'A'`); SQL engine only |

Setting `expression` while `mode` stays `"&&"` → DSS evaluates the (empty)
`conditions[]` and silently ignores your formula = no-op match-all. Canonical
formula-mode shape:

```json
{"enabled": true, "distinct": false,
 "uiData": {"mode": "CUSTOM", "$latestOperator": "&&", "$filterOptions": "CUSTOM", "conditions": []},
 "expression": "amount_sum >= 300 && status == 'A'"}
```

**Operators** (note trailing spaces in numeric ops):
- String: `== [string]`, `!= [string]`, `== [string]i`, `contains`,
  `not contains`, `contains [string]i`, `starts with`, `ends with`, `regex`,
  `in [string]` / `not in [string]` (`items:[{"string":"v"}]`).
- Numeric: `>  [number]`, `<  [number]`, `>= [number]`, `<= [number]`,
  `== [number]`, `!= [number]`, `>< [number]` (between, `num`+`num2`).
- Null: `is empty`, `not empty`. Date: `== [date]`, `>  [date]`, `<  [date]`
  (`date`). Column-vs-column: `== [column]`, `!= [column]`, `>  [column]` (`col`).

VisualIfRule caveat: `regex`, `in [string]`, date, and geo operators silently
return False when created via API — use GREL in a `FilterOnCustomFormula` step.

## Join (`join`)

```json
{"joins": [{
  "table1": 0, "table2": 1, "conditionsMode": "AND", "type": "LEFT", "outerJoinOnTheLeft": true,
  "on": [{"column1": {"name": "customer_id", "table": 0},
          "column2": {"name": "cust_id", "table": 1},
          "type": "EQ", "maxDistance": 0, "normalizeText": false}]}],
 "selectedColumns": [{"name": "amount", "table": 0, "alias": "left_amount"}],
 "virtualInputs": [{"index": 0, "outputColumnsSelectionMode": "AUTO_NON_CONFLICTING",
   "preFilter": {"enabled": false},
   "computedColumns": [{"mode": "GREL", "name": "weighted", "expr": "score * weight", "type": "double"}]}]}
```

- `type`: `INNER`, `LEFT`, `RIGHT`, `FULL`, `CROSS`, `LEFT_ANTI`, `RIGHT_ANTI`,
  `ADVANCED`. `on[].type`: `EQ`, `LT`, `LTE`, `GT`, `GTE`, `NE`, `WITHIN_RANGE`.
  EQ/LT/LTE/GT/GTE/NE need no payload edit — `create-join --join-key` operator
  syntax emits them (`'a>=b'` → GTE).
- `table1`/`table2` are 0-based indexes into `virtualInputs`.
- **Conditions are pairwise-only.** A pair's `on[]` may only reference its own
  `table1`/`table2`; a condition touching a third table fails at build — and
  the error message names the wrong dataset, so don't chase the named one.
  Fix: split into a second join pair (or a cascaded join) so every condition
  stays within its declared pair.
- **Self-join / same-named column trap:** default `AUTO_NON_CONFLICTING`
  silently drops one side's column (no error). Set
  `outputColumnsSelectionMode: "MANUAL"` on **both** virtualInputs and enumerate
  `selectedColumns` with `alias` for the collisions.
- **Join keys can survive a `--cols` exclusion** — DSS may keep the key in the
  output even when the projection omits it. If the key is internal-only,
  delete it in a downstream Prepare (`add-delete-columns`).
- **Any payload round-trip ⇒ go MANUAL.** A get-settings → patch →
  set-settings/set-definition cycle can lose the column projection
  (`--cols`) and re-resolve under `AUTO_NON_CONFLICTING`, silently dropping a
  real column (benchmark: the surviving join lost `rate` → products of 0, no
  error). After patching any join payload, set
  `outputColumnsSelectionMode: "MANUAL"` + explicit `selectedColumns` on every
  virtualInput, then re-read and diff.
- `virtualInputs[i].preFilter`: same canonical CUSTOM shape as the 4-stage
  pipeline (top-level `expression`, `uiData.mode: "CUSTOM"` — § Visual
  conditions). Malformed variants (`expression` only inside `uiData`, or mode
  `"&&"` with empty `conditions`) do NOT error — they **silently match all
  rows**; a "filter must have at least one condition" error means the filter
  fell into the conditions path. `create-join --pre-filter 'INDEX:EXPR'`
  writes the canonical shape for you.
- `virtualInputs[i].computedColumns`: derive a column inside one input —
  `mode` is `"GREL"` (the dataikuapi `CUSTOM` docstring is a typo) or `"SQL"`,
  `type` lowercase. Payload-level `computedColumns` is **post-join** and sees
  BOTH sides' output columns — cross-input math (`amount * rate`) belongs
  here, not in a downstream Prepare. Payload-level `postFilter` also works.
  All four stages are reachable from `create-join`
  (`--pre-filter`/`--computed-col`/`--post-filter`) without payload editing.

## Group (`grouping`)

```json
{"keys": [{"column": "region", "type": "string"}],
 "values": [{"column": "amount", "type": "double", "sum": true, "avg": true,
             "count": false, "min": false, "max": false, "first": false, "last": false,
             "firstLastNotNull": false, "stddev": false, "concat": false, "concatDistinct": false,
             "orderColumn": "ts", "concatSeparator": ",", "$idx": 0},
            {"customExpr": "max(\"price\") - min(\"price\")", "customName": "price_range", "type": "DOUBLE"}],
 "globalCount": false, "selectAllColumns": false, "enlargeYourBits": true,
 "outputColumnNameOverrides": {"amount_sum": "total_amount"}}
```

- Standard agg flags are booleans; standard `type` lowercase (`double`/`bigint`).
- `orderColumn` required for `first`/`last`/`firstLastNotNull` AND for
  deterministic `concat`/`concatDistinct` ordering.
- **Custom aggregations**: `customExpr`+`customName` instead of `column`+flags,
  `type` UPPERCASE (`INT`/`DOUBLE`/`STRING`). SQL engine only. Can reference a
  `computedColumns` name → "derive then aggregate" in one recipe.
- `globalCount:true` adds a per-group `count` (set `false` for SQL/PROC/Summarize
  parity). `selectAllColumns:true` also projects every input column through.

## Window (`window`)

```json
{"windows": [{"enablePartitioning": true, "partitioningColumns": ["customer_id"],
   "enableOrdering": true, "orders": [{"column": "order_date", "desc": false}],
   "enableLimits": false, "windowLowerBound": {"unbounded": true}, "windowUpperBound": {"unbounded": true}}],
 "values": [{"column": "amount", "sum": true, "lag": false, "lead": false, "lagDiff": false,
             "leadDiff": false, "first": false, "last": false, "lagValues": "1,2", "orderColumn": "order_date", "$idx": 0}],
 "rowNumber": false, "rank": false, "denseRank": false, "cumeDist": false,
 "ntile": false, "ntileValues": "4,10",
 "globalAggregations": [], "legacyUnboundedWindowStreamBehavior": false,
 "retrievedColumnsSelectionMode": "ALL"}
```

- `enablePartitioning`/`enableOrdering` MUST be `true` for
  `partitioningColumns`/`orders` to take effect.
- **The DSS engine silently ignores frame bounds** — ROWS
  (`enableLimits`+`precedingRows`/`followingRows`) and RANGE bounds save into
  the payload but execute as current-row-only or cumulative/whole-partition;
  only the two extremes work (verified live: `precedingRows:2, followingRows:0`
  → cumulative sum). Frame bounds only take effect on a SQL engine. Rolling-N
  on the DSS engine → range self-join + Group (pattern in
  `playbooks/tabular-flow.md` § Visual recipe decision).
- `lag`/`lead`: set `lagValues`/`leadValues` (comma string `"1,2"`) + `orderColumn`.
- Window aggs (`sum`/`max`/`last`) default to a **current-row-only** frame, not
  unbounded. `sum` IS cumulative with an order-key and no partition. For a
  full-partition aggregate (same value every row), set the window's
  `enableLimits:true` + both bounds non-limited + top-level
  `legacyUnboundedWindowStreamBehavior:true` (all three; CLI `--frame-unbounded`).
- **`last` is NOT forward-fill** — it returns the current row's own value. For
  forward-fill of *monotonic* ordinals (sortable years/IDs/dates) use `max`
  (empties sort before non-empties, so cumulative max carries the latest value;
  fails on non-monotonic like `'08'→'09'→'08'`). General forward-fill needs two
  Windows: (a) cumulative `sum(is_set)` → `group_id`, (b) partition by `group_id`
  + `max` (one row per group holds the value).
- `globalAggregations[]` (same shape as `values[]`) computes window-wide
  aggregates → "fraction of grand total" without a downstream Group+Join.
- `retrievedColumnsSelectionMode: "EXPLICIT"` + `retrievedColumns:[{column,value}]`
  projects output (replaces a downstream ColumnsSelector).

## Filter (`sampling` Prepare form via `create-filter`)

```json
{"filterCondition": {"enabled": true, "distinct": false,
   "uiData": {"mode": "&&", "conditions": [{"input": "age", "operator": ">= [number]", "num": 18}]}}}
```

Formula mode: set `expression` + `uiData.mode: "CUSTOM"`. `expression` (in
CUSTOM/SQL mode) takes precedence over `conditions`.

## TopN (`topn`)

```json
{"topN": 5, "firstRows": 5, "lastRows": 0,
 "keys": ["department"], "orders": [{"column": "salary", "desc": true}],
 "rank": false, "denseRank": false, "rowNumber": false, "duplicateCount": false}
```

`keys` is a **string array** (unlike Group/Window's dict arrays). `firstRows`
(top-N) is mutually exclusive with `lastRows` (bottom-N) — set the unused to 0.

## Stack (`vstack`)

`mode`: `UNION` (default, superset of columns), `INTERSECT` (columns in all),
`FROM_DATASET`+`copySchemaFromDatasetWithName`, `FROM_INDEX`+`selectedColumnsIndexes`
(templated input names), `REMAP` (custom output schema, positional column
alignment — eliminates N upstream ColumnRenamers).

```json
{"mode": "REMAP", "selectedColumns": ["id", "amount", "date"],
 "virtualInputs": [{"originLabel": "orders", "columnsMatch": ["order_id", "total", "order_date"]},
                   {"originLabel": "sales",  "columnsMatch": ["sale_id", "price", "sold_at"]}],
 "addOriginColumn": true, "originColumnName": "source"}
```

`addOriginColumn`+`originColumnName` writes a source-tag column (replaces N
tag-only Prepare recipes). Per-input `virtualInputs[i].preFilter`; top-level
`postFilter`. There is no flag-level mutator for a per-input filter after
creation — edit `virtualInputs[i].preFilter` via read-edit-write, or
delete+recreate the recipe (the expected path for a wrong `--input-filter`).

## Sort (`sort`) & Distinct (`distinct`)

Sort: `orders[]` + top-level `rank`/`denseRank`/`rowNumber` booleans + the full
4-stage pipeline. Distinct dedupes on ALL columns by default; for a subset set
`keys: [{column}]` **with `selectAllColumns: true`** (else DSS silently projects
to only the key columns).

```json
{"keys": [{"column": "customer_id"}, {"column": "order_date"}], "selectAllColumns": true, "globalCount": false}
```

### Sort computed columns

`computedColumns` in sort/dedup/stack/window recipes must use GREL-only functions.
`toDouble()` does NOT exist — use `toNumber()`. WRONG: `--computed-col 'unit_price=toDouble(unit_price):double'`
→ CORRECT: `--computed-col 'unit_price=toNumber(unit_price):double'`.

After editing a computed column, re-`apply-schema` and rebuild — stale schema
produces corrupted gzip output ("Unexpected end of ZLIB input stream") on rebuild.

## Split (`split`)

`mode` ∈ `VALUES`, `RANDOM`, `RANGE`, `FILTERS` (payload plural — CLI `FILTER`
maps to it), `CENTILE`, `RANDOM_COLUMNS`.

| mode | required |
|---|---|
| VALUES | `column`, `valueSplits[].{outputIndex,value}` |
| RANDOM | `randomSplits[].{outputIndex,share}`, `seed` |
| RANGE | `column`, `rangeSplits[].{outputIndex,min?,max?,include_min,include_max}` |
| FILTERS | `filterSplits[].{outputIndex, filter:{uiData}}` |
| CENTILE | `centileOrders[].{column,desc}`, `centileSplits[].{outputIndex,share}` |

Shared: `defaultOutputIndex` (catch-all), `seed`, `computedColumns`,
`preFilter`, `postFilter`.

## Update / UPSERT (`update`) — config in `recipe.params`, NOT payload

```json
{"params": {"uniqueKey": ["customer_id"], "addMissingRows": true, "deleteMissingRows": false,
            "addMissingCols": true, "deleteMissingCols": false}}
```

Output dataset MUST already exist (operates in-place).

## Pivot (`pivot`)

Base: `pivots[0].{keyColumns, valueColumns}`. Plus:
- `otherColumns[]` (Group-`values`-shaped) carry non-pivot columns through;
  `{column, last:true, orderColumn:"ts"}` = keep latest per group.
- `valueLimit` ∈ `TOP_N`, `NO_LIMIT`, `AT_LEAST_N_OCC`, `EXPLICIT`. Use
  `"EXPLICIT"` (NOT `"EXPLICIT_VALUES"` — silently falls back to TOP_N/20) with
  `pivots[0].explicitValues` as **array of single-element arrays** `[["2024"],["2025"]]`.
- `modalitySlugification` ∈ `NONE`, `SOFT_SLUGIFY` (UI default), `HARD_SLUGIFY`.
- `outputColumnNameOverrides` is IGNORED by Pivot — rename via a downstream
  Prepare `add-rename` instead.
- Count-only cross-tab: `valueColumns: []` + `globalCount: true`.

## Geo Join (`geojoin`)

```json
{"joins": [{"table1": 0, "table2": 1, "type": "LEFT", "geoJoin": true, "geoOperator": "INTERSECTS",
   "rightLimit": {"enabled": true, "maxMatches": 1, "type": "KEEP_LARGEST"}}]}
```

`geoOperator`: `WITHIN_DISTANCE`, `BEYOND_DISTANCE` (both use `geoDistance`+
`geoUnit`), `INTERSECTS`, `CONTAINS`. **Default `rightLimit.enabled:false` lets
INTERSECTS fan out left rows** when N polygons match — set
`enabled:true, maxMatches:1, type:KEEP_LARGEST` for "tag each left row once".
`rightLimit.type` ∈ `KEEP_LARGEST`, `KEEP_SMALLEST`, `KEEP_FIRST`, `KEEP_LAST`.
Geo columns must be **typed** `geopoint`/`geometry`, not a `string` that merely
holds WKT — a string-typed geo column makes the build fail (no/aborted match).
Type it first: `dku dataset set-schema DS -d '... geom geopoint ...'` (or
`add-geopoint` from lat/lon). WKT is `POINT(lon lat)`, longitude first, EPSG:4326;
reproject with `ChangeCRSProcessor`.

## Fuzzy Join (`fuzzyjoin`)

Create with `dku recipe create-fuzzy-join`; payload reference for edits:

```json
{"joins": [{"table1": 0, "table2": 1, "type": "LEFT", "conditionsMode": "AND",
   "on": [{"column1": {"name": "name", "table": 0}, "column2": {"name": "ref_name", "table": 1},
           "type": "FUZZY", "fuzzyMatchDesc": {"distanceType": "LEVENSHTEIN", "threshold": 2}}]}]}
```

`distanceType` ∈ `EXACT`, `LEVENSHTEIN`, `EUCLIDEAN`, `HAMMING`, `COSINE`,
`JACCARD`; an exact key is a `distanceType:"EXACT", threshold:0` condition.
Two silent traps (build exits 0, wrong rows):
- Join-level `fuzzyJoinMethod`/`fuzzyJoinMaxDistance` keys are **persisted but
  ignored** — the recipe quietly degrades to exact matching.
- A condition without `"type":"FUZZY"` (e.g. `fuzzyMatchDesc` alone) is
  **dropped** — the join degrades to a near-cross join (every left × right).
Optional per-condition `normaliseDesc` (`caseInsensitive`, `clearStopWords`,
`transformToStem`, `sortAlphabetically`, `language`) applies text normalization
before distance.

## Extract Failed Rows (`extract_failed_rows`)

```json
{"columnRules": [{"ruleColumn": "email", "ruleId": "email_format_regex", "isSelected": true}]}
```

References ruleIds in the input dataset's `checks[]` (`dku dq list-checks DS`).
Empty `columnRules[]` extracts failures for ALL enabled rules.

## List Folder Contents / Merge Folder — `recipe.params`, NOT payload

```json
{"path": true, "basename": true, "extension": true, "size": true, "lastModified": true}
```

Merge: `{"clearBeforeCopy": true, "conflictHandling": "OVERWRITE"}` (∈ `OVERWRITE`,
`SKIP`, `FAIL`).
