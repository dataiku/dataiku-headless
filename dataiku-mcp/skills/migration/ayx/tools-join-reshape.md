# Alteryx Join & Reshape Tools → Dataiku

Join, JoinMultiple, AppendFields, Union/Stack, Summarize, CrossTab, Transpose, and collapse patterns.

## Join

Alteryx Join has **three outputs** — `Left` (left-only), `Join` (matched), `Right` (right-only); each output can fan out independently. Map **one DSS Join recipe per output table**; each Alteryx `Join+Union(…)` pair collapses to a single typed Join. `create-join -j` supports `INNER, LEFT, RIGHT, FULL, CROSS, LEFT_ANTI, RIGHT_ANTI`. Key format `'leftcol=rightcol'`.

The 7 SQL joins (Alteryx outputs unioned):

| SQL join (Alteryx outputs unioned) | DSS recipe |
|---|---|
| INNER (`Join`) | `create-join -i L -i R -k 'lk=rk' -j INNER` |
| LEFT (`Join`+`Left`) | `-i L -i R -j LEFT` — one recipe, no Union |
| RIGHT (`Join`+`Right`) | `-i L -i R -j RIGHT` |
| FULL (`Join`+`Left`+`Right`) | `-i L -i R -j FULL` — but see FULL-engine gotcha |
| LEFT-anti / left-only (`Left`) | `-i L -i R -j LEFT_ANTI` — emits only left columns (matches Alteryx `Left`; right side not appended) |
| RIGHT-anti / right-only (`Right`) | swap inputs: `-i R -i L -k 'rk=lk' -j LEFT_ANTI` — emits only R's columns (cleaner than `-j RIGHT_ANTI`, which keeps left column slots) |
| FULL-anti / outer-excluding-inner (`Left`+`Right`) | `create-stack -i out_left_anti -i out_right_anti` — schema-union fills absent side with nulls |

DSS LEFT_ANTI keeps only the surviving (left) side, so anti-join output columns match Alteryx — no downstream column-drop needed.

**FULL outer join engine gotcha (OWNER).** On filesystem/uploaded inputs, `-j FULL` at the default engine may auto-pick an unavailable engine (Spark → `DSS integration to version 1.X is no longer supported`); forcing `--engine DSS` throws H2 `Syntax error in SQL statement "EXPLAIN SELECT …"` when a join/output column name contains a space. INNER/LEFT/RIGHT/LEFT_ANTI are unaffected — only FULL hits it. **Engine-free workaround: build FULL as `Stack(LEFT, RIGHT_ANTI)`** — LEFT holds inner+left-only rows, right-anti adds right-only rows; one Stack, no FULL engine. FULL-anti = `Stack(LEFT_ANTI, RIGHT_ANTI)`. Alternatively sync to a SQL connection and run FULL there.

**Caveats:**
- Column collision: both sides with `name` → right comes through as `name_1`. Rename upstream.
- Alteryx Join and DSS Join both silently drop rows where the key is null on either side (SQL semantics).
- `--cols 'INDEX:c1,c2,c3'` is **silently ignored** (writes `selectedColumns` as a plain string list; DSS Join needs `[{"name","table","type"},…]` dicts and falls back to AUTO). Drop unwanted columns via downstream Prepare `add-step ColumnsSelector keep=false`. See `../../dku-cli/playbooks/tabular-flow.md`.

**Positional join** (`joinByRecordPos="True"`) — Alteryx aligns by record index; DSS has no positional-join visual recipe. Decision ladder:
1. **Derive a common key first** (most positional joins exist because data was extracted without a key). When the two sides hold the same entity under differently-formatted labels, normalize one with `add-formula` (e.g. `concat(col, " - <suffix>")`) and join on the derived key — exact, robust to ordering, and 1 recipe vs 3.
2. **No derivable key, but each input has a stable order column:** Window with `--compute rowNumber::idx` on each side (no partition; order by an existing positional col) → Join on the row-number columns.
3. **No stable order column** (raw CSV): pre-bake a `row_id` at upload — DSS Prepare has NO row-counter. `add-step --type Enumerator` accepts at add-time but fails at run with `UnavailableTypeException: Type Enumerator was available in a plugin that is not installed`. Bake the index in the Python extraction (`csv.writer` + `enumerate(rows)`, schema-set `row_id` to `bigint`). If the source is already a managed dataset, materialize one Window-with-rowNumber over the full input first.

Window `rowNumber` output column is **hardcoded to `rownumber`** (lowercase); the `--compute 'rowNumber::idx'` third segment is advisory and silently ignored — reference `rownumber` in the join key, or `--rename 'rownumber:idx'` to force it. When pre-baking a position key, mind the post-filter ordering trap: a Window `lead`/`lag` followed by a row filter must order on the position column before the filter, or the offset reads the wrong neighbor.

---

## JoinMultiple

N-way join on a single key. Chain 2-way Join recipes (one per additional input) for all-in-memory; use a SQL recipe with multiple `JOIN` clauses for 3+ inputs on a SQL connection.

---

## AppendFields (cartesian)

Cartesian product (Target × Source). DSS: Join `type: CROSS`, else SQL `SELECT * FROM a CROSS JOIN b`, else Python `a.assign(_k=1).merge(b.assign(_k=1), on="_k").drop("_k", axis=1)`.

**Single-row broadcast** (the most common AppendFields use): when the Source side is **one row** synthesized by `Sample(First 1) → Formula(extract field from row 0)` — stamping every Target row with a value from the input's first row (date in a title cell, a report parameter, a global stamp) — there is no cartesian. Skip the Sample/Formula branch AND the AppendFields; fold into the Target's Prepare:

```bash
dku recipe add-formula PREP --column Date --expr 'if(startsWith(F1, "Ranks as of "), substring(F1, 12), null)'
dku recipe add-step PREP --type UpDownFiller -p '{"columns":["Date"],"up":false}'
```

Row 0 sets `Date`, others get `null`, `UpDownFiller(up:false)` fills nulls with the previous non-null — broadcasting row-0 to all rows. **Only NULL triggers fill; `""` does not** — return `null`, not `""`. Collapses 3 tools → 2 Prepare steps, net zero recipes. See `ayx/overview.md` § Collapse triggers (messy-spreadsheet row).

---

## Union / Stack

Alteryx `Union` stacks inputs, matching columns by name (default), position, or manual; missing columns → null. DSS: Stack recipe.

```bash
dku recipe create-stack st -P PROJ -i a -i b -i c --output-ds stacked
```

- `Union Fields by Name` → `--mode UNION` (default; union schema, missing → null).
- `Union Fields by Position` → DSS Stack maps by **name, not position**. If the workflow depends on position, pre-rename columns upstream to the intended names, then stack `--mode UNION`.
- Type disagreement (e.g. `int` vs `string`) → Stack may upcast to `string`. Rename/cast upstream.

---

## Summarize

Group-by + explicit aggregations → DSS Group recipe with `--no-global-count` (Alteryx doesn't emit an unrequested count).

```bash
dku recipe create-group grp -P PROJ -i in --output-ds agg \
    --group-by Region --agg 'Sales:sum,Orders:count_distinct' --no-global-count
```

### Alteryx action → DSS aggregation

| Alteryx | DSS |
|---|---|
| `Sum` / `Count` / `CountDistinct` | `sum` / `count` / `count_distinct` |
| `CountNonNull` | `count` (on a non-null column) |
| `Min` / `Max` / `Avg` | `min` / `max` / `avg` |
| `First` / `Last` | `first` / `last` |
| `Median` | DSS `median` aggregate is **SQL-engine ONLY**, NOT reachable via `--agg` (set `--engine SQL` + `median` JSON flag via `set-settings`). In-memory engine fails `RuntimeException: Median aggregation is not implemented for DSS Engine`. On in-memory data, `create-sync` to SQL first — see § Median / percentile. |
| `Concat` / `ConcatDistinct` | `concat` — Snowflake LISTAGG size cap (see Caveats + `../../dku-cli/playbooks/tabular-flow.md`) |
| `StdDev` | `stddev` |
| `Variance` | **NOT a `--agg` function** (`col:variance` rejected). Get `stddev`² in a downstream Prepare `--computed-col`, or SQL `VAR_POP`/`VAR_SAMP`. |
| `Percentile` / `Quantile` | **NOT a Group aggregate at all** (`col:percentile` rejected). Use a SQL recipe `PERCENTILE_CONT(p) WITHIN GROUP (ORDER BY "col")` (`p` 0–1; every standard SQL engine). On filesystem inputs, `create-sync` to SQL first — see § Median / percentile. |
| `SumNo0` / `AvgNo0` / `MinNo0` / `MaxNo0` / `CountNo0` | **No direct DSS aggregation** — `*No0` variants ignore zeros (plus nulls), which DSS aggregations don't. Lift zero-exclusion to a `--computed-col` on the same Group, then aggregate it: `--computed-col 'col_no0=if(val("col")==0\|\|isBlank(val("col")), null, val("col")):double' --agg col_no0:avg`. The `if … null` converts zeros to nulls; `avg` already ignores nulls. **GREL `==` not `=`** — single `=` errors `Unexpected '='. Did you mean '=='?`; if it slips through, the job log shows a misleading `EOFException: Unexpected end of ZLIB input stream` (the GREL syntax error is the real cause). See `ayx/semantics.md` § Aggregation null-handling. |

**Caveats:**
- Group auto-names outputs `{col}_{func}` (`Sales_sum`). `--rename SRC:DST` fixes names inline (Group's `outputColumnNameOverrides` IS honored — unlike Pivot's, see `../../dku-cli/playbooks/tabular-flow.md`), or a downstream `ColumnRenamer`.
- `Concat` on Snowflake → LISTAGG, capped per-group. For large text, aggregate in Python.

### Median / percentile (no in-memory visual path)

Both `median` (SQL-engine only, not via `--agg`) and percentile/quantile (no Group aggregate at all) collapse to the same shape: sync input to a SQL connection (`duckdb_local` works for verification migrations), then ONE SQL recipe with `PERCENTILE_CONT`.

```bash
# Alteryx: Summarize(GroupBy Region, Median Sales, Percentile 90 of Sales)
dku recipe create-sync sync_to_db -P PROJ -i input --output-ds input_db -c <sql_connection>
dku recipe run sync_to_db -P PROJ --wait

dku recipe create-sql med_pct -P PROJ -i input_db --output-ds med_pct_result \
    --connection <sql_connection> \
    --sql 'SELECT "Region",
                  PERCENTILE_CONT(0.5)  WITHIN GROUP (ORDER BY "Sales") AS "Median Sales",
                  PERCENTILE_CONT(0.90) WITHIN GROUP (ORDER BY "Sales") AS "P90 Sales"
           FROM "${projectKey}_input_db" GROUP BY "Region"'
dku recipe apply-schema med_pct -P PROJ
dku recipe run med_pct -P PROJ --wait
```

`PERCENTILE_CONT(0.5)` IS the median, so one SQL recipe covers both actions. Use `PERCENTILE_DISC(p)` (actual data value, no interpolation) if Alteryx's percentile method requires it. For a SQL-backed input, skip the sync.

### Sample (Mode=First, N=1) → TopN, not Sort+Sample

Alteryx `Sample(Mode=First, N=1)` (no `GroupFields`) takes the first row — typically after a `Sort` to grab the min/max row. Migrate as a **single TopN** (sort + limit in one pass), not Sort + Sample:

```bash
# Alteryx: Group → Sort by avg_age asc → Sample(First, N=1)  (3 tools)
# DSS:    Group → TopN(--n 1 --sort-col 'avg_age:asc')        (2 recipes)
dku recipe create-topn youngest -P PROJ -i agg --output-ds youngest --n 1 --sort-col 'avg_age:asc'
```

`Mode=First, N=K` → `--n K`. With `GroupFields`, pass `--partition-key`. The Sort recipe is fully replaced.

---

## CrossTab

Pivot wide: group rows by `GroupFields`, columns from `HeaderField`, values from `DataField` with `Action` aggregation → DSS Pivot recipe.

```bash
dku recipe create-pivot pv -P PROJ -i in --output-ds wide \
    -r Region -c Category -v Sales --agg-type SUM --no-global-count
```

- Output columns are `<header_value>_<agg>`. For text aggregation ("Concatenate") use `concat` agg, mind SQL LISTAGG limits.

**Modality scan build failure (OWNER) — fix with `--value-limit`, don't avoid the pivot.** A fresh `create-pivot` at the default `TOP_N` builds and errors `RecipeSchemaComputer$DontWantToCompute: Modality lists stored in output schema are not up-to-date` (`dku` can't trigger the UI's distinct-value scan).
- Low cardinality (≤ a few dozen distinct headers): `--value-limit NO_LIMIT` — DSS resolves modalities at build time.
- Deterministic whitelist: `--value-limit EXPLICIT --explicit-values v1 --explicit-values v2`.
- Frequency floor: `--value-limit AT_LEAST_N_OCC --min-occ-limit N`.
- Setting `pivots[0].explicitValues` via `set-settings` does **NOT** work (updates payload, not the modality cache) — only the `--value-limit` flags do. For high-cardinality headers, fall back to per-modality columns inline upstream with `add-formula`.

**Count-occurrences-then-pivot collapses to ONE Pivot (default global count).** Alteryx `Summarize(GroupBy=(row,col)+Count) → CrossTab(DataField=Count, Method=Sum) → MultiFieldFormula(iif(isNull(x),0,x))` (incidence matrix) → a **single Pivot with no value column**: `create-pivot -r ROW -c COL --value-limit NO_LIMIT`. DSS adds a per-modality global-count column by default (this IS the per-cell record count) and **auto-fills empty cells with 0**, so the upstream Summarize AND the null→0 MultiFieldFormula both vanish. Output columns `<modality>_count` → one downstream `ColumnRenamer` (3 tools → 1 Pivot).

**CrossTab → DynamicRename.** Pivot, then a **trailing static Prepare** `ColumnRenamer` for the renames. A DynamicRename that maps output column names **from values in an input table** (data-driven rename) has no visual equivalent — needs **Python** (read the rename map, apply to the wide-form column headers).

**The job-not-the-tool reflex.** Many CrossTabs are mid-flow shape changes the downstream consumer doesn't need. Before reaching for Pivot, ask *what does the next recipe do with the wide form?* If it's "join then aggregate again", fold the aggregation into the upstream Group's `computedColumns` (`../../dku-cli/playbooks/tabular-flow.md` § Collapse N recipes into 1) or compute the per-category values per-component before any reshape.

---

## Transpose

Pivot long: key columns stay, data columns become (Name, Value) pairs → DSS Prepare with `MultiColumnFold` (stock, no plugin):

```bash
dku recipe add-fold prep1 --columns "q1,q2" --key-column Name --value-column Value -P PROJ
```

`add-fold` emits `MultiColumnFold` with `foldRemoveFoldedColumns: true`. `MultiColumnByPrefixFold` is the regex variant — `add-fold --pattern '.*-25'`.

**`MultiColumnFold` SILENTLY DROPS rows where the value is null** — a row with a null in one folded column yields N-1 long rows instead of N, no warning. Two handlers:
1. **For downstream aggregation** (most common — fold so you can `Group` the long form): pre-impute with `FillEmptyWithValue` (one step per folded column) BEFORE the fold. Imputed rows survive; Group result is unaffected by the imputation choice. (This is the default path.)
2. **For round-trip preserving null status** (rare — original wide values must appear as `Value=""` in the final long output): sentinel-string — cast each metric to string with `if(isBlank(strval("col")), "@@NULL@@", concat("", numval("col")))`, fold the sentinels, then `add-find-replace --matching FULL_STRING` swapping `@@NULL@@` → empty. Single Prepare, still visual.

**DO NOT use `FoldColumnsByName`** — that's a plugin processor (params `keyColumn`/`valueColumn`) that errors `UnavailableTypeException` where the plugin isn't installed. `add-fold` emits stock `MultiColumnFold`, no plugin needed. `pd.melt` is never needed for this, even on the rarest DSS instance.

**The job-not-the-tool reflex.** Most Transposes exist to feed a downstream `Summarize` over the long form. The cleaner DSS shape: compute the aggregate **per-input, before any reshape** — one `add-formula` per output key inside each upstream Prepare; the long form is never materialized (saves unpivot + lookup join + per-key Group). The round-trip `Transpose → MultiRowFormula → CrossTab → JoinMultiple → AlteryxSelect → Transpose` (long→window→wide→join→wide→long) reduces to: compute everything in long form, emit final long output via Stack-of-projections. The CrossTab/JoinMultiple round-trip exists because Alteryx MultiRowFormula operates on a single column; DSS Window carries both Value and lagged columns through the long form, so the round-trip is wasted shape change. See `ayx/overview.md` § Collapse triggers (the `Union → Transpose → Summarize` and `Transpose → MultiRowFormula → CrossTab → Transpose` rows).

---

## Component-stat workflows (Transpose + Summarize + CrossTab macro chains)

Common pattern: per-component datasets with wide stat columns (one per category), chained `Transpose` (wide→long) → `Summarize` (group+agg per category) → `CrossTab` (long→wide) → join across components → score; often wrapped in a `.yxmc` macro to repeat per category.

**The DSS rewrite skips both reshapes.** Do the per-category arithmetic *inside each upstream Prepare* with `add-formula` (one per category); the long form never materializes. A `BatchMacro` repeating the chain becomes N sibling Prepares (one per component). The `CROSS` join is one recipe (`create-join -i` is repeatable), not N-1 chained joins. Each Prepare stays on whatever engine its input uses — no engine break for the long form.

Worked example (4-component combo optimizer — score each component, cross-join, rank):

```bash
# Per component: one Prepare with N add-formula steps, one per category. No Transpose/Summarize/CrossTab.
for c in DRIVERS BODIES TIRES GLIDERS; do
  dku recipe create-prepare prep_${c} -P PROJ -i ${c}_RAW --output-ds ${c}_SCORED
  dku recipe add-formula prep_${c} -P PROJ --column speed_score \
      --expr 'numval("Anti-Gravity Speed") * 0.5 + numval("Ground Speed") * 0.5'
  dku recipe add-formula prep_${c} -P PROJ --column handling_score \
      --expr 'numval("Handling") * 0.7 + numval("Mini-Turbo") * 0.3'
  dku recipe apply-schema prep_${c} -P PROJ
done

# One CROSS join wires all four scored components into a single combo row (-i is repeatable, N>2 in one recipe).
dku recipe create-join join_combos -P PROJ \
    -i DRIVERS_SCORED -i BODIES_SCORED -i TIRES_SCORED -i GLIDERS_SCORED \
    --output-ds COMBOS --join-type CROSS

# Final score + sort.
dku recipe create-prepare score_combos -P PROJ -i COMBOS --output-ds COMBOS_SCORED
dku recipe add-formula score_combos -P PROJ --column total_score \
    --expr 'speed_score * 0.4 + handling_score * 0.6'
dku recipe create-sort sort_combos -P PROJ -i COMBOS_SCORED \
    --output-ds COMBOS_RANKED --sort-col total_score:desc
```

If a draft DSS plan contains `Transpose → Summarize → CrossTab` (or its macro equivalent), stop and audit: the per-category formulas usually already live in the upstream component dataset, and the reshape was just an Alteryx-flavored loop.
