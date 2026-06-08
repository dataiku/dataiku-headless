# Alteryx Join and Reshape Tools to Dataiku

Translation details for joins, unions, summarize, crosstab, transpose, and related collapse patterns.

## Join

**Alteryx:** three outputs — `Left` (rows only in left), `Join` (matched), `Right` (rows only in right). A wire from each output can fan out independently.

```xml
<Configuration joinByRecordPos="False">
  <JoinInfo connection="Left"><Field field="id"/></JoinInfo>
  <JoinInfo connection="Right"><Field field="id"/></JoinInfo>
</Configuration>
```

**Dataiku:** Join recipe. Type depends on which Alteryx outputs are used:
- Only `Join` consumed → **Inner**
- `Join` + `Left` consumed (separately) → Inner into one output + **Antijoin** (first-class type in recent DSS; check `dku recipe create-join --help`) into another; fallback is Inner + Left-Outer with a downstream filter.
- All three separately → cleanest is **Full Outer Join** into one recipe; then downstream filter on match status.
- DSS Join's "non-matching columns" option (where available) can also emit an extra output containing the unmatched rows, so the three Alteryx outputs can come from one Join recipe with two outputs + an antijoin.

```bash
dku recipe create-join jn -P PROJ \
    --inputs left,right \
    --output-ds joined \
    --type inner \
    --condition 'left.id == right.id'
```

**Caveats:**
- Column collision: if both sides have `name`, the right side comes through as `name_1`. Rename upstream.
- `joinByRecordPos="True"` (positional join) — Alteryx aligns rows by record index. DSS has no positional-join visual recipe. **First, look for a derivable common key**: positional joins in Alteryx often exist because the data was extracted from text/CSV without a key column, but a key can be reconstructed (e.g., concat / strip-suffix / parse-prefix). Tested on Challenge_031: left side had `Surf Site = "Tamarack St."`, right side had `Site = "Tamarack St. - San Diego County"` — adding `add-formula Site = concat(Surf Site, " - San Diego County")` to the left and joining on `Site = Site` reproduces the positional-join result exactly (and is more robust to ordering changes). **Only when no common key is derivable** fall back to: Window with `--compute rowNumber::idx` on each side (no partition; default ordering by an existing positional column) → Join on the row-number columns. The Window+Window+Join chain is 3 recipes vs 1 for the derived-key approach. **If neither input has a stable order column** (raw uploaded CSV with no positional field), prepend a `row_id` column at upload time — DSS Prepare has NO row-counter processor (verified Challenge_033: `add-step --type Enumerator` accepts at step-add time but fails at run-time with the misleading `UnavailableTypeException: Type Enumerator was available in a plugin that is not installed`), and Window's `rowNumber` aggregation requires an order-by column. Pre-baking the index in the Python extraction (`csv.writer` with `enumerate(rows)`, schema-set `row_id` to `bigint`) is the cleanest path; if the source is already a managed dataset, materialize one Window-with-rowNumber over the full input first, then proceed. Tested on Challenge_033 (Nielsen reshape): `joinByRecordPos="True"` between filtered metadata (30 rows) and filtered metric (30 rows) collapsed to: pre-bake `row_id` at upload → Prepare for Branch A (filter+formula+rename, surfaces `Code = 1..30` as a natural position key) → Window for Branch B (`lead` + post-filter to identify metric rows) → Window for Branch B index (`rowNumber` 1..30) → Join on `Code = rownumber`. The `rowNumber` output column is hardcoded by DSS to `rownumber` (lowercase), the `--compute 'rowNumber::idx'` third segment is advisory and silently ignored — reference `rownumber` in the join key, or `--rename 'rownumber:idx'` to force the override (works for Window output schema; remember the post-filter ordering trap above).
- Alteryx Join silently drops rows where the key is null on either side (matches SQL semantics). DSS Join does the same.
- `--cols 'INDEX:c1,c2,c3'` is **silently ignored** at the moment (writes `selectedColumns` as a plain string list; DSS Join requires `[{"name", "table", "type"}, ...]` dict objects and falls back to AUTO mode when the dict shape is missing). Until fixed, drop unwanted columns via a downstream Prepare `add-step ColumnsSelector keep=false`. See `../../dku-cli/playbooks/tabular-flow.md`.

---

## JoinMultiple

**Alteryx:** N-way join on a single key.

**Dataiku:** chain 2-way Join recipes (one per additional input) or use a SQL recipe with multiple `JOIN` clauses. For 3+ inputs on a SQL connection, the SQL recipe is cleaner; for all-in-memory, chain Joins.

---

## AppendFields (cartesian)

**Alteryx:** cartesian product of two inputs (Target × Source).

**Dataiku:** Join recipe with `type: CROSS` (if supported), else a SQL recipe: `SELECT * FROM a CROSS JOIN b`. In Python: `a.assign(_k=1).merge(b.assign(_k=1), on="_k").drop("_k", axis=1)`.

**Single-row broadcast (the most common Alteryx use of AppendFields).** When the Source side is **one row** synthesized upstream by `Sample(First 1) → Formula(extract field from row 0)` — i.e. the workflow is just stamping every Target row with a value derived from the input's first row (a date in the title cell, a report parameter, a global stamp) — there is no cartesian. Skip both the Sample/Formula branch AND the AppendFields. Instead, fold them into the Target's Prepare:

```bash
dku recipe add-formula PREP --column Date --expr 'if(startsWith(F1, "Ranks as of "), substring(F1, 12), null)'
dku recipe add-step PREP --type UpDownFiller -p '{"columns":["Date"],"up":false}'
```

The first row sets `Date`, every other row gets `null`, then `UpDownFiller(up:false)` fills `null` cells with the previous non-null value — broadcasting the row-0 value to all rows. **Only NULL triggers fill; empty string `""` does not** (see `../../dku-cli/references/prepare-processors.md` § UpDownFiller). Returning `null` from the formula (not `""`) is critical. This collapse turns `Sample + Formula + AppendFields` (3 tools) into `CreateColumnWithGREL + UpDownFiller` (2 steps) inside whatever Prepare you already have — net cost zero recipes. See `ayx/overview.md` § Collapse triggers — the "messy-spreadsheet" row.

---

## Union / Stack

**Alteryx `Union`:** stacks inputs, matching columns by name (default) or position. Missing columns → null.

```xml
<Configuration>
  <Mode>ByName|ByPosition|Manual</Mode>
</Configuration>
```

**Dataiku:** Stack recipe.

```bash
dku recipe create-stack st -P PROJ \
    -i a -i b -i c \
    --output-ds stacked
```

Modes:
- `Union Fields by Name` → Stack with `--mode UNION` (default; union schema, missing → null).
- `Union Fields by Position` → DSS Stack maps by column name, not position. If the Alteryx workflow depends on position, pre-rename columns upstream to the intended names, then stack with `--mode UNION`.

**Caveats:** if two inputs disagree on a column's type (e.g. `int` vs `string`), Stack may upcast to `string`. Rename/cast upstream to avoid surprises.

---

## Summarize

**Alteryx:** group-by + aggregations, explicit.

```xml
<Configuration>
  <SummarizeFields>
    <SummarizeField field="Region" action="GroupBy" rename="Region"/>
    <SummarizeField field="Sales" action="Sum" rename="Total Sales"/>
    <SummarizeField field="Orders" action="CountDistinct" rename="Unique Orders"/>
  </SummarizeFields>
</Configuration>
```

**Dataiku:** Group recipe, `--no-global-count` (Alteryx doesn't emit an unrequested count).

```bash
dku recipe create-group grp -P PROJ -i in --output-ds agg \
    --group-by Region \
    --agg 'Sales:sum,Orders:count_distinct' \
    --no-global-count
```

### Alteryx action → DSS aggregation

| Alteryx | DSS |
|---|---|
| `Sum` | `sum` |
| `Count` | `count` |
| `CountDistinct` | `count_distinct` |
| `CountNonNull` | `count` (on a non-null column) |
| `Min` / `Max` | `min` / `max` |
| `Avg` | `avg` |
| `Median` | `median` |
| `First` / `Last` | `first` / `last` |
| `Concat` / `ConcatDistinct` | `concat` — careful on SQL connections (LISTAGG size cap, see § Caveats below and `../../dku-cli/playbooks/tabular-flow.md`) |
| `StdDev` / `Variance` | `stddev` / `variance` |
| `Percentile` | `percentile` (configure `percentile_value`) |
| `SumNo0` / `AvgNo0` / `MinNo0` / `MaxNo0` / `CountNo0` | **No direct DSS aggregation** — the `*No0` variants in Alteryx ignore zero values (in addition to nulls), which DSS aggregations don't. Lift the zero-exclusion to a `--computed-col` on the same Group recipe, then aggregate the computed column. Pattern: `--computed-col 'col_no0=if(val("col")==0\|\|isBlank(val("col")), null, val("col")):double' --agg col_no0:avg`. The `if … then null else col` construct converts zeros to nulls, then `avg` (which already ignores nulls) gives Alteryx-equivalent semantics. Tested on Challenge_030 (fantasy-baseball Avg_Age and Avg_Pitcher Rank by team): 1 Group recipe, exact match against expected. **GREL `==` not `=` for equality** — single `=` is assignment and the CLI errors `Unexpected '='. Did you mean '=='?` (good) but the underlying job log shows a misleading `EOFException: Unexpected end of ZLIB input stream` (bad — investigate later). See `ayx/semantics.md` § Aggregation null-handling for why this divergence exists. |

**Caveats:**
- Group recipe auto-names outputs `{col}_{func}` (`Sales_sum`). Use `--rename SRC:DST` to fix names inline (the Group recipe's `outputColumnNameOverrides` IS honored — unlike the Pivot recipe's, see `../../dku-cli/playbooks/tabular-flow.md`). Or add a `ColumnRenamer` in a downstream Prepare to restore Alteryx aliases.
- `Concat` on Snowflake → LISTAGG, capped per-group. For large text, aggregate in a Python recipe.

### Sample (Mode=First, N=1) → TopN, not Sort+Sample

Alteryx's `Sample` tool with `Mode=First` and `N=1` (no `GroupFields`) takes the first row of the input — typically used after a `Sort` to grab the row with the min/max value. **Migrate as a single TopN recipe**, not Sort + Sample:

```bash
# Alteryx: Group → Sort by avg_age asc → Sample(First, N=1)  (3 tools)
# DSS:    Group → TopN(--n 1 --sort-col 'avg_age:asc')        (2 recipes — TopN sorts internally)

dku recipe create-topn youngest -P PROJ -i agg --output-ds youngest --n 1 --sort-col 'avg_age:asc'
```

Alteryx's `Sample` with `Mode=First, N=K` collapses to `--n K` on TopN. With `GroupFields` set, pass `--partition-key`. The Sort recipe is fully replaced — TopN is sort + limit in one pass.

---

## CrossTab

**Alteryx:** pivot wide. Group rows by `GroupFields`, columns from `HeaderField`, values from `DataField` with `Action` aggregation.

```xml
<Configuration>
  <GroupFields><Field field="Region"/></GroupFields>
  <HeaderField>Category</HeaderField>
  <DataField>Sales</DataField>
  <Methods><Method method="Sum"/></Methods>
</Configuration>
```

**Dataiku:** Pivot recipe.

```bash
dku recipe create-pivot pv -P PROJ -i in --output-ds wide \
    -r Region -c Category -v Sales --agg-type SUM --no-global-count
```

**Caveats:**
- Output columns are `<header_value>_<agg>`. If Alteryx used "Concatenate" for text aggregation, use `concat` agg but mind SQL LISTAGG limits.
- **Modality scan is UI-only.** A fresh `create-pivot` recipe builds and errors `RecipeSchemaComputer$DontWantToCompute: Modality lists stored in output schema are not up-to-date`. Setting `pivots[0].explicitValues = [["v1"], ["v2"], …]` via `set-settings` updates the recipe payload but DOES NOT populate the output dataset's modality cache, so the build still fails. There is no `dku` command that triggers the scan. **Workaround: restructure to avoid the pivot.** If you need a wide table with one column per modality for downstream joins, compute the per-modality aggregate inside each upstream branch (Prepare with `add-formula` per modality) and skip the pivot altogether. See `ayx/overview.md` § Collapse triggers — the `Summarize → CrossTab` row.

> **The job-not-the-tool reflex for CrossTab.** Many CrossTabs are mid-flow shape changes that downstream consumers don't actually need. Before reaching for Pivot, ask: *what does the next recipe do with the wide form?* If the answer is "join then aggregate again", you can usually fold the aggregation into the upstream Group recipe's `computedColumns` (see `../../dku-cli/playbooks/tabular-flow.md`) or just compute the per-category values per-component before any reshape.

---

## Transpose

**Alteryx:** pivot long. Key columns stay; data columns become (Name, Value) pairs.

```xml
<Configuration>
  <KeyFields><Field field="id"/></KeyFields>
  <DataFields><Field field="q1"/><Field field="q2"/></DataFields>
</Configuration>
```

**Dataiku:** Prepare recipe with `MultiColumnFold` (stock DSS — no plugin). Use the `add-fold` shortcut:

```bash
dku recipe add-fold prep1 --columns "q1,q2" --key-column Name --value-column Value -P PROJ
```

(`add-fold` emits `MultiColumnFold` with `foldRemoveFoldedColumns: true`. `MultiColumnByPrefixFold` is the regex-pattern variant — `add-fold --pattern '.*-25'`.)

> **`MultiColumnFold` SILENTLY DROPS rows where the value is null.** A row that has a null in one of the folded columns produces N-1 long rows instead of N. There is no warning. Two ways to handle this:
>
> 1. **For aggregation downstream** (most common — fold so you can `Group` over the long form): pre-impute with `FillEmptyWithValue` (one step per folded column) BEFORE the fold. Imputed rows survive and the Group result is unaffected by the imputation choice.
> 2. **For round-tripping back to long form preserving null status** (rare — e.g., the original wide values need to appear as `Value=""` in the final long output): use a sentinel-string approach. Cast each metric to a string column with `if(isBlank(strval("col")), "@@NULL@@", concat("", numval("col")))`, fold the sentinel-strings, then `add-find-replace` with `--matching FULL_STRING` to swap `@@NULL@@` back to empty. Six metric columns → ~10 step Prepare. Single Prepare; still visual.
>
> The default DSS auto-output behavior is option 1; only reach for option 2 when the null status itself is part of the contract.

> **DO NOT use `FoldColumnsByName`** — that's a plugin processor (different param names: `keyColumn`/`valueColumn`) that errors with `UnavailableTypeException` where the plugin isn't installed. `dku recipe add-fold` emits the stock `MultiColumnFold`, which needs no plugin. `pd.melt` is genuinely never needed for this — even on the rarest DSS instance.

> **The job-not-the-tool reflex for Transpose.** Most Alteryx Transposes exist to feed a downstream `Summarize` (group + agg) over the long form. In DSS the cleaner shape is to compute the aggregate **per-input, before any reshape**: one `add-formula` step per output key inside each upstream Prepare, and the long form is never materialized. Saves the unpivot, the lookup join, and the per-key Group all in one shot. See `ayx/overview.md` § Collapse triggers — the `Union → Transpose → Summarize` row.

> **Pivot/Transpose round-trip in Alteryx is just a long-form computation in disguise.** The pattern `Transpose → MultiRowFormula → CrossTab → JoinMultiple → AlteryxSelect → Transpose` (long → window → wide → join → wide → long) reduces in DSS to: compute everything in long form, then emit the final long output via Stack-of-projections. The CrossTab/JoinMultiple round-trip exists in Alteryx because MultiRowFormula operates on a single column and the original metric values must be re-attached to the moving averages — DSS Window can carry both Value and lagged columns through the long form, so the round-trip is wasted shape change. See `ayx/overview.md` § Collapse triggers — the `Transpose → MultiRowFormula → CrossTab → Transpose` row.

---

## Component-stat workflows (Transpose + Summarize + CrossTab macro chains)

A common Alteryx pattern: per-component datasets carrying wide stat columns (one column per category), chained through `Transpose` (wide→long) → `Summarize` (group + agg per category) → `CrossTab` (long→wide back to one column per category) → join across components → score. Often wrapped in a standard or batch `.yxmc` macro to repeat per category.

**The DSS rewrite skips both reshapes entirely.** When the goal is "for each component, produce one column per category, then combine across components", do the per-category arithmetic *inside each upstream Prepare* with `add-formula` (one formula per category) — the long form is never materialized.

Worked example (Mario Kart-style 4-component combo optimizer, validated migration `MARIOKART_FRESH`):

```bash
# Per component (drivers / bodies / tires / gliders): one Prepare with N add-formula
# steps, one per category to score on. No Transpose, no Summarize, no CrossTab.
for c in DRIVERS BODIES TIRES GLIDERS; do
  dku recipe create-prepare prep_${c} -P PROJ -i ${c}_RAW --output-ds ${c}_SCORED
  dku recipe add-formula prep_${c} -P PROJ --column speed_score \
      --expr 'numval("Anti-Gravity Speed") * 0.5 + numval("Ground Speed") * 0.5'
  dku recipe add-formula prep_${c} -P PROJ --column handling_score \
      --expr 'numval("Handling") * 0.7 + numval("Mini-Turbo") * 0.3'
  dku recipe apply-schema prep_${c} -P PROJ
done

# One CROSS join wires all four scored components into a single combo row
# (`-i` is repeatable; create-join handles N>2 in a single recipe).
dku recipe create-join join_combos -P PROJ \
    -i DRIVERS_SCORED -i BODIES_SCORED -i TIRES_SCORED -i GLIDERS_SCORED \
    --output-ds COMBOS --join-type CROSS

# Final score + sort: another Prepare with the weighted-sum formula, then Sort.
dku recipe create-prepare score_combos -P PROJ -i COMBOS --output-ds COMBOS_SCORED
dku recipe add-formula score_combos -P PROJ --column total_score \
    --expr 'speed_score * 0.4 + handling_score * 0.6'
dku recipe create-sort sort_combos -P PROJ -i COMBOS_SCORED \
    --output-ds COMBOS_RANKED --sort-col total_score:desc
```

**Why this collapses cleanly:**
- The Transpose/Summarize/CrossTab triplet only existed because Alteryx-style macros encourage looping over a category list. DSS expresses "per-category arithmetic" as N formulas in one Prepare — explicit, readable, and stays on whatever engine the input uses (no engine break for the long form).
- A `BatchMacro` repeating the chain per component becomes 4 sibling Prepares (one per component), all configurable via the same loop.
- The `CROSS` join is one recipe, not N-1 chained joins, because `create-join -i` is repeatable.

If you find yourself writing `Transpose → Summarize → CrossTab` (or its macro equivalent) in a draft DSS plan, stop and audit: usually the per-category formulas already live in the upstream component dataset, and the entire reshape was just a Alteryx-flavored loop.

---
