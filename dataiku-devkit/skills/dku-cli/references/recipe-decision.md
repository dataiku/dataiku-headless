# Recipe Decision Reference

Complete decision tree and code examples for creating recipes.

## Decision Tree

```
Is the task a join/merge?           → create-join --join-key col  (NEVER pd.merge)
Is the task aggregation/groupby?    → create-group -k col1 -k col2 --agg col:sum,avg  (NEVER df.groupby)
Is the task stacking/union/concat?  → create-stack  (NEVER pd.concat)
Is the task dedup/distinct?         → create-distinct  (NEVER df.drop_duplicates)
Is the task sorting?                → create-sort  (NEVER df.sort_values)
Is the task filtering rows?         → create-filter  (NEVER df[condition])
Is the task window/rank function?   → create-window --compute 'rowNumber::rn'  (NEVER df.groupby().transform)
Is the task top/bottom N?           → create-topn --n 10 --rank-by col:desc  (NEVER df.nlargest)
Is the task top N per group?        → create-topn --n 1 --rank-by col:desc -k group_col  (NEVER groupby().first)
Is the task wide-to-long (unpivot)? → Prepare recipe + add-fold  (if UnavailableTypeException → Python pd.melt)
Is the task long-to-wide (pivot)?   → create-pivot --agg-type SUM  (NEVER df.pivot_table)
Is the task random sampling?        → create-sampling  (NEVER df.sample)
Is the task row expansion?          → create-join --join-type CROSS  (NEVER nested loops)
Is the task a passthrough/copy?     → create -t sync  (NEVER Python passthrough)
Is the task cross-connection move?  → create -t sync --connection TARGET_CONN  (NEVER Python passthrough)
None of the above?                  → THEN use Python: create NAME -t python
```

## Visual Recipe Selection Guide

| Task | Command | NOT this |
|------|---------|----------|
| **Join datasets** | `dku recipe create-join NAME -i ds1 -i ds2 --output-ds out -P PROJ` | ~~pd.merge()~~ |
| **Aggregate/group by** | `dku recipe create-group NAME -i ds --output-ds out -k col1 -k col2 --agg 'amount:sum,avg' -P PROJ` | ~~df.groupby()~~ |
| **Stack/union** | `dku recipe create-stack NAME -i ds1 -i ds2 --output-ds out -P PROJ` | ~~pd.concat()~~ |
| **Deduplicate** | `dku recipe create-distinct NAME -i ds --output-ds out -P PROJ` | ~~df.drop_duplicates()~~ |
| **Sort** | `dku recipe create-sort NAME -i ds --output-ds out -P PROJ` | ~~df.sort_values()~~ |
| **Filter rows** | `dku recipe create-filter NAME -i ds --output-ds out -P PROJ` | ~~df[df.x > y]~~ |
| **Window functions** | `dku recipe create-window NAME -i ds --output-ds out -k grp --order-key date --compute 'rowNumber::rn' -P PROJ` | ~~df.groupby().transform()~~ |
| **Top N** | `dku recipe create-topn NAME -i ds --output-ds out --n 10 --rank-by col:desc -P PROJ` | ~~df.nlargest()~~ |
| **Top N per group** | `dku recipe create-topn NAME -i ds --output-ds out --n 1 --rank-by date:desc -k stock -P PROJ` | ~~groupby().first()~~ |
| **Split by condition** | `dku recipe create-split NAME -i ds --output-ds out_a -P PROJ && dku recipe add-output NAME out_b -P PROJ && dku recipe set-definition NAME --payload @split.json -P PROJ` (create-split alone is a stub — attach more outputs and configure split conditions via `set-definition`) | ~~manual filtering~~ |
| **Pivot (long->wide)** | `dku recipe create-pivot NAME -i ds --output-ds out --row-key id --column-key month --value-column val --agg-type SUM -P PROJ` | ~~df.pivot_table()~~ |
| **Unpivot (wide->long)** | `dku recipe add-fold PREP --columns "jan,feb,mar" --key-column month --value-column val -P PROJ` | ~~pd.melt()~~ |
| **Random sample** | `dku recipe create-sampling NAME -i ds --output-ds out --size 1000 -P PROJ` | ~~df.sample()~~ |
| **Cross join (cartesian)** | `dku recipe create-join NAME -i A -i B --output-ds out --join-type CROSS -P PROJ` | ~~itertools.product()~~ |
| **Cross-connection move** | `dku recipe create NAME -t sync -i ds --output-ds out --connection TARGET_CONN -P PROJ` | ~~Python passthrough~~ |
| **Custom logic ONLY** | `dku recipe create NAME -t python -i ds --output-ds out -P PROJ` | Last resort |

## Join Design: Multi-Input > Cascading

One `create-join -i A -i B -i C -i D` with index-prefixed keys is ALWAYS better than cascading A+B → temp → temp+C → out.

```bash
dku recipe create-join enrich_sales \
  -i sales -i customers -i products -i regions \
  --output-ds enriched_sales \
  --join-key customer_id \
  --join-key 1:product_id \
  --join-key 2:region_code=code \
  --join-type LEFT \
  -P PROJ
```

### Join Types

| Type | Flag | Keeps | Use when... |
|------|------|-------|-------------|
| **LEFT** | `--join-type LEFT` | All left rows, matched right | Enriching |
| **INNER** | `--join-type INNER` (default) | Only matched rows | Both sides must match |
| **RIGHT** | `--join-type RIGHT` | All right rows | Rare |
| **FULL** | `--join-type FULL` | All rows from both | Reconciliation |
| **CROSS** | `--join-type CROSS` | Cartesian product | Row expansion |

**Default is INNER.** If task says "enrich", use **LEFT**.

## Python Recipe (Last Resort)

```bash
dku recipe create compute_risk_score -t python -i customer_features --output-ds risk_scores -P PROJ && \
dku recipe set-code compute_risk_score -P PROJ --code @score.py
```

### Python ID Casting Pattern

```python
df["ACCOUNT_SK"] = pd.to_numeric(df["ACCOUNT_SK"], errors="coerce")
df = df.dropna(subset=["ACCOUNT_SK"])
df["ACCOUNT_SK"] = df["ACCOUNT_SK"].astype("int64")
```

Direct `.astype("int64")` on dirty data fails with `IntCastingNaNError`.

## Common Mistakes

| Mistake | Fix |
|--------|-----|
| Cascading joins | One `create-join -i A -i B -i C` |
| LEFT join when INNER needed | `--join-type INNER` |
| Python `groupby` | Use `create-group -k col --agg` |
| Python `nlargest` | Use `create-topn --n N` |
| TopN without ordering | `--rank-by col:desc` |
| Prepare recipe without output | Pre-create output dataset |
| Plugin recipe SELECT wrong case | Values are case-sensitive |
| GREL for columns with spaces | Use `add-rename` first |

> For payload schemas, see `dataiku` skill's `references/visual-recipe-payloads.md`.
