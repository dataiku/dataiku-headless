# Recipe Examples & Data Reshaping

Detailed examples for visual recipes, plugin recipes, and data reshaping patterns. For the recipe decision tree and selection guide, see the main SKILL.md.

## Join Example (replaces Python merge)

```bash
# Upload two datasets, then join them visually
dku dataset create customers --type UploadedFiles -P PROJ && \
dku dataset upload customers /tmp/customers.csv -P PROJ && \
dku dataset create orders --type UploadedFiles -P PROJ && \
dku dataset upload orders /tmp/orders.csv -P PROJ && \

# Visual join with explicit key (auto-detects if --join-key omitted)
dku recipe create-join join_orders_customers \
  -i orders -i customers \
  --output-ds enriched_orders \
  --join-key customer_id \
  -P PROJ && \

# Build (schema auto-applied by create-join)
dku dataset build enriched_orders -P PROJ --wait
```

## Group Example (replaces Python groupby)

```bash
# Aggregate orders by customer with SUM and AVG — DSS visual recipe
dku recipe create-group summarize_by_customer \
  -i orders \
  --output-ds customer_summary \
  -k customer_id \
  --agg "amount:sum,avg" \
  --agg "order_id:count" \
  -P PROJ && \

# Build (schema auto-applied by create-group)
dku dataset build customer_summary -P PROJ --wait
```

## First/Last Row Per Group

Use **TopN per group** to get the first or last row per group:

```bash
# First row per group (e.g., earliest transaction per stock)
dku recipe create-topn first_per_stock \
  -i transactions \
  --output-ds first_transactions \
  --n 1 \
  --rank-by date \
  -k stock \
  -P PROJ

# Last row per group (latest transaction per stock)
dku recipe create-topn last_per_stock \
  -i transactions \
  --output-ds last_transactions \
  --n 1 \
  --rank-by date:desc \
  -k stock \
  -P PROJ
```

Alternative with Window + Filter (when you need row_number for other purposes):

```bash
# Add row number partitioned by stock, ordered by date
dku recipe create-window add_rank -i data --output-ds ranked \
  -k stock --order-key date --compute 'rowNumber::rn' -P PROJ && \
# Filter to keep only first row per group
dku recipe create-filter keep_first -i ranked --output-ds first_per_group -P PROJ
# Configure filter condition (rn == 1) via DSS UI or:
# dku recipe set-definition keep_first --payload '{"filterConditions": ...}' -P PROJ
```

## Window Functions — Quick Guide

Window recipes compute per-row values within partitions without reducing row count.

| Compute | Syntax (`--compute`) | Use case |
|---------|---------------------|----------|
| Row number | `'rowNumber::rn'` | Sequential numbering within group |
| Rank (gaps) | `'rank::rnk'` | 1,2,2,4 ranking |
| Dense rank | `'denseRank::drnk'` | 1,2,2,3 ranking (no gaps) |
| Lag | `'lag:col:1::prev_val'` | Previous row's value |
| Lead | `'lead:col:1::next_val'` | Next row's value |
| Running sum | `'sum:amount::running_total'` | Cumulative totals |
| Running count | `'count:::running_count'` | Cumulative counts |
| Running avg | `'avg:amount::running_avg'` | Moving averages |

**Pattern — first/last per group:** `create-topn --n 1 --rank-by date:desc -k group_col` is simpler than Window + Filter. Use Window only when you need the rank column for other purposes.

## Plugin Source Recipes (No Input)

Some plugin recipes (e.g. `generate-rows`) are source recipes with no input role. Omit `-i` — the CLI skips input wiring:

```bash
dku recipe create gen_data -t CustomCode_my-plugin_generate-rows \
  --output-ds generated -P PROJ
```

## Plugin Recipes with Named Roles

When using `set-definition` with plugin recipes that have named roles (not `main`), **pre-create the output dataset** before `recipe create`. The `--output-ds` auto-create wires to `main` role; `set-definition` rewires to plugin role names, orphaning the dataset:

```bash
# RIGHT — pre-create, then wire to named role
dku dataset create output_ds --type Filesystem -c filesystem_managed -P PROJ && \
dku recipe create my_step -t CustomCode_plugin_recipe -i input --output-ds output_ds --output-role output_role_name -P PROJ
```

> **Note on Filesystem datasets:** If you need to manually create a Filesystem dataset (rare — usually recipe create does this), you MUST specify `--connection`: `dku dataset create NAME --type Filesystem -c filesystem_managed -P PROJ`. Without `-c`, it errors. Run `dku connection list` to find available connections.

## Deleting Datasets and Projects

Both `dku dataset delete` and `dku project delete` support `--yes` / `-y` to skip confirmation:

```bash
# Dataset delete (prompts without --yes)
dku dataset delete my_data -P MY_PROJ --yes

# Project delete (requires --confirm, --yes, or -y)
dku project delete MY_PROJ --yes
```

## Adding Extra Inputs/Outputs to a Recipe

`add-input` and `add-output` take the dataset as a positional argument:

```bash
# Add a second input (e.g., for a join or lookup)
dku recipe add-input my_recipe second_dataset -P PROJ

# Add with a custom role (default is "main")
dku recipe add-input my_recipe lookup_table --role lookup -P PROJ

# Add an extra output
dku recipe add-output my_recipe extra_output -P PROJ
```

## Data Reshaping Patterns

### Wide-to-Long (Unpivot/Fold)

When columns like `jan`, `feb`, `mar` need to become rows with `month` + `value`:

```bash
# Create prepare recipe, add fold step, build
dku recipe create reshape --type prepare -i wide_data --output-ds long_data -c filesystem_managed -P PROJ && \
dku recipe add-fold reshape --columns "jan,feb,mar" --key-column month --value-column sales -P PROJ && \
dku job run --target long_data --auto-update-schema --wait -P PROJ
```

For pattern-based folding (all columns matching a regex):
```bash
dku recipe add-fold reshape --pattern ".*-25" --key-column month --value-column value -P PROJ
```

### Long-to-Wide (Pivot)

```bash
dku recipe create-pivot pivot_monthly -i long_data --output-ds wide_data \
  --row-key customer_id --column-key month --value-column sales -P PROJ
```

### Cross Join (Row Expansion)

Generate all combinations (e.g., records x future months):
```bash
dku recipe create-join expand -i records -i months --output-ds expanded --join-type CROSS -P PROJ
```

### Multi-Input Join (2-5 datasets in one recipe)

**ALWAYS prefer one multi-input join over cascading joins.**

```bash
# Join main with 3 lookups — each with different join keys
dku recipe create-join enrich \
  -i main -i lookup_a -i lookup_b -i lookup_c \
  --output-ds enriched \
  --join-key entity=company \
  --join-key 1:platform \
  --join-key 2:channel=Channel \
  -P PROJ
```

**Index prefix rules:**
- Unprefixed `--join-key col` -> applies to join 0 (main <-> first `-i` after main)
- `1:col` -> join 1 (main <-> second `-i`)
- `2:col` -> join 2 (main <-> third `-i`)
- `col=other_col` -> left column `col` matches right column `other_col`
- Same column name on both sides? Just `--join-key col`

```bash
# Example: enrich sales with customer, product, and region lookups
dku recipe create-join enrich_sales \
  -i sales -i customers -i products -i regions \
  --output-ds enriched_sales \
  --join-key customer_id \
  --join-key 1:product_id \
  --join-key 2:region_code=code \
  --join-type LEFT \
  -P PROJ
```

### Random Sampling

```bash
dku recipe create-sampling sample_1k -i big_data --output-ds sample --method RANDOM_FIXED_NB --size 1000 -P PROJ
```

Methods: `RANDOM_FIXED_NB`, `RANDOM_FIXED_RATIO` (use `--ratio 0.1`), `HEAD_SEQUENTIAL`, `STRATIFIED`.

## Detailed Cascading vs Multi-Input Comparison

**Anti-pattern: Cascading joins** — joining A+B -> temp1, then temp1+C -> temp2, then temp2+D -> output:
- 3 recipes instead of 1
- 2 unnecessary intermediate datasets
- 3x schema propagation
- Column name explosion (prefixed at every step: `temp1_customers_name`)
- 3x build time

```bash
# BAD — cascading joins (3 recipes, 2 intermediate datasets)
dku recipe create-join join_ab -i A -i B --output-ds temp1 --join-key id -P PROJ && \
dku recipe create-join join_abc -i temp1 -i C --output-ds temp2 --join-key id -P PROJ && \
dku recipe create-join join_abcd -i temp2 -i D --output-ds final --join-key id -P PROJ

# GOOD — one multi-input join (1 recipe, 0 intermediate datasets)
dku recipe create-join enrich_all \
  -i A -i B -i C -i D \
  --output-ds final \
  --join-key id \
  --join-key 1:id \
  --join-key 2:id \
  -P PROJ
```

**When cascading IS acceptable:** Different join types per step (e.g., LEFT join for A+B, then INNER join for result+C), or when intermediate datasets are reused by other recipes.

## Split Aggregation: Numeric + Text (Snowflake)

When a Snowflake dataset has both numeric columns to aggregate and large text/JSON columns to merge, **do not** use `--agg "col:concat"` on the text columns. Snowflake's `LISTAGG()` (which DSS compiles `concat` to) has a per-group result size limit that fails with error 300002 on large text values.

Split the work: visual group for numerics, Python recipe for text/JSON merging.

```bash
# Step 1: Visual group for numeric columns (runs as Snowflake GROUP BY — fast, precise)
dku recipe create-group aggregate_numerics \
  -i raw_reports \
  --output-ds usage_grouped \
  -k ACCOUNT_SK -k MONTH \
  --agg "NB_PROJECTS:sum" \
  --agg "NB_DATASETS:sum" \
  --agg "NB_USERS:sum" \
  -P PROJ && \
dku dataset build usage_grouped -P PROJ --wait

# Step 2: Python recipe ONLY for JSON dict merging (what SQL can't do)
dku recipe create merge_json -t python \
  -i raw_reports -i usage_grouped \
  --output-ds usage_final \
  -P PROJ && \
dku recipe set-code merge_json -P PROJ --code @merge_json.py
```

Sample `merge_json.py`:

```python
import dataiku
import pandas as pd
import json
from collections import Counter

raw = dataiku.Dataset("raw_reports").get_dataframe()
grouped = dataiku.Dataset("usage_grouped").get_dataframe()

def merge_dicts(series):
    merged = Counter()
    for val in series.dropna():
        try:
            merged.update(json.loads(val) if isinstance(val, str) else val)
        except (json.JSONDecodeError, TypeError):
            continue
    return json.dumps(dict(merged)) if merged else None

json_agg = raw.groupby(["ACCOUNT_SK", "MONTH"])["RECIPE_TYPES_JSON"].apply(merge_dicts).reset_index()
json_agg.columns = ["ACCOUNT_SK", "MONTH", "RECIPE_TYPES_JSON"]

result = grouped.merge(json_agg, on=["ACCOUNT_SK", "MONTH"], how="left")
dataiku.Dataset("usage_final").write_with_schema(result)
```

**Why not all-Python?** The visual group runs as a Snowflake `GROUP BY` — orders of magnitude faster than pulling all rows into Python, preserves bigint precision, and gives visual lineage in the flow. Python handles only the JSON merging that SQL has no native operation for.
