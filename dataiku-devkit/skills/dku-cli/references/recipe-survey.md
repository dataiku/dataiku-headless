# Recipe survey — picking the right recipe

The decision tree for "which DSS recipe should I use?" — when designing a flow, refactoring an existing one, or migrating from another tool. Companion to `recipe-decision.md` (which is the **code-examples-quick-reference** — every recipe + its CLI command + the Python anti-pattern it replaces); this file is the **decision-rationale** lens (when each recipe is right, the visual-recipe pipeline collapse pattern, filter-mode rules).

For migration-specific tool/step → recipe mapping (Alteryx tools, SAS PROCs), see `migration/<source>/translation.md`.

## Priority

**Visual → SQL → Python**, in that order. A flow with mostly visual recipes is a flow that downstream maintainers can read and reviewers can change without writing code. A flow of one giant Python recipe is a black box.

Drop to SQL when the logic genuinely needs:
- `LAG` / `LEAD` / `ROW_NUMBER` / window functions beyond what the Window recipe exposes
- `PERCENTILE_CONT` / approximate quantiles
- Range or theta joins (`BETWEEN`, `>=`, conditional join keys)
- Multi-CTE pipelines that genuinely benefit from in-engine optimization
- Direct port of an existing pass-through `SELECT`

…**or** when an engine constraint rules visual out:
- **Customer mandate** — "the flow must execute entirely in Snowflake / BigQuery / Postgres". Most visual recipes push down, but custom GREL with no SQL equivalent and certain Prepare processors do not. When the mandate is non-negotiable, switching those steps to SQL is the right call even if visual could express the logic.
- **Perf budget** — a visual recipe that round-trips through DSS for partial computation blows the SLA on a large input. Native SQL keeps the data in-engine end-to-end.
- **Explicit tuning** — CTAS ordering, query hints, partitioning, clustering keys that the visual recipe doesn't surface. Cross-check `sql-engines.md` § GREL → SQL push-down gotchas before assuming a visual recipe will push down cleanly.

These are concrete carve-outs, not a general escape hatch. "I prefer SQL" / "SQL is more readable" / "the existing team writes SQL" are still not reasons — visual recipes are reviewable on the flow graph, which SQL recipes are not.

Drop to Python only when neither visual nor SQL can express it:
- Regex-heavy multi-row state (e.g. parsing a log into events)
- Hash lookups with non-equality keys (fuzzy match, prefix match, IP range lookup)
- True row-by-row state machines (PDV, iterative-macro semantics)
- Arbitrary HTTP / web IO
- Heavy geospatial beyond the GeoJoin / GeoDistance / `geo*` GREL family

"One Python file is tidier" / "one SQL file is tidier" is **never** a reason. Visual recipes are tidier when read on the flow.

## Visual recipe survey

| Recipe | What it does | When to pick it |
|---|---|---|
| **Prepare (Shaker)** | Per-row transformations: rename, retype, formula, regex, find/replace, split, parse, filter, fill, format. 100+ processors. | Any time the operation is row-local: cast types, compute new columns, normalize strings, parse dates. The default first choice for "transform a column" |
| **Filter** (sub-type of Prepare via `create-filter`) | Keep rows matching a formula | Single-output filtering. Always built as a Prepare recipe with a `FilterOnCustomFormula` step — never the standalone "Sampling" recipe |
| **Split** | Route rows to multiple outputs based on conditions | Keep BOTH the matching and non-matching rows. Cleaner than two inverse Prepare-filter recipes |
| **Join** | Equi-join two datasets, optional unmatched-row outputs | Any equality-keyed join. Inner, left, right, outer, cross, antijoin. Three outputs: `joined`, `unmatched_left`, `unmatched_right` |
| **Group** | Group-by + aggregations | SQL `GROUP BY`, SAS PROC SQL/MEANS/SUMMARY, Alteryx Summarize. Pass `--no-global-count` unless you specifically want a row count column added |
| **Window** | Partition + order + window aggregations | `LAG` / `LEAD` / `ROW_NUMBER` / `RANK` / cumulative sums / by-group order-dependent logic |
| **Stack (Union)** | Append datasets vertically | SQL `UNION ALL`, SAS `set X Y;`, Alteryx Union. Five `--mode` values: `UNION` (default, superset), `INTERSECT` (intersection), `FROM_DATASET:NAME` (copy schema from named input), `FROM_INDEX:N` (copy schema from input at position N — useful when input names are templated), `REMAP` (custom output schema with positional `--columns-match` per input — eliminates N upstream `ColumnRenamer` recipes). Per-input pre-filter via `--input-filter INDEX:GREL`; output post-filter via `--post-filter` |
| **Distinct** | Drop duplicate rows | Only when *all columns* are part of the dedup key. If only a subset of columns are keys, use Window + `ROW_NUMBER == 1` instead — Distinct is wrong |
| **Sort** | Order rows | Any sort. Mostly used to feed an order-dependent Window or `val()` formula |
| **Top N** | Keep first/last N rows per group | Sample / Top N rows. Requires an upstream sort or partition-aware Top N config |
| **Pivot** | Wide pivot or unpivot (melt) | SQL `PIVOT`, Alteryx CrossTab, SAS `proc transpose`. Both directions: pivot (long → wide) and unpivot (wide → long) |
| **Sync** | Copy a dataset from one connection to another | Cross-connection landing (CSV → Snowflake, Filesystem → S3). Lightest-weight way to satisfy rule 2 |
| **GeoJoin** | Spatial join (contains, within-distance, intersects) | Any geometric relationship. **Set `--max-matches 1 --right-limit-strategy KEEP_LARGEST` for "tag each left row with one match" semantics — without it INTERSECTS fans out left rows when N polygons match.** |
| **Update** (UPSERT) | Maintain a target by merging input rows on a unique key | SQL `MERGE`, Alteryx Append Fields, SAS `proc append`. Output dataset MUST already exist (Update operates in-place; the recipe stores its config in `recipe.params`, not the JSON payload). CLI: `dku recipe create-update -i delta --output-ds master --unique-key id` |
| **Extract Failed Rows** | Quarantine rows that violated dataset checks | Alteryx Data Cleansing fail-bucket, SAS `PROC SQL VALIDATE`. Input must have checks defined (`dq add-check`). Without `--rule-id`, extracts failures for ALL enabled rules |
| **List Folder Contents** | Emit one row per file in a managed folder | Alteryx Directory tool, SAS `dopen()` / `pipe ls`. Built-in (not a plugin); the only DSS recipe that reads folder *metadata* into a dataset rather than file *content* |
| **Merge Folder** | Combine N source folders into one | Alteryx Output-to-Folder with multiple branches, shell `cp -r`. Built-in; the only DSS folder→folder recipe |
| **Sampling** (with `selection.filter` set) | Don't use for filtering — schema is shape-sensitive and DSS silently drops some shapes during save | Use `create-filter` (Prepare with `FilterOnCustomFormula`) instead. The Sampling recipe only honors a bare `selection.filter.expression` string; the natural-looking `uiData.expression` shape is rewritten to `{mode: "CUSTOM", conditions: []}` and the filter becomes a no-op. See `common-gotchas.md` for the verified test matrix |

## ML recipes (training, scoring, evaluation)

| Recipe | What it does | CLI verb |
|---|---|---|
| **Training (Prediction / Clustering)** | Reads a dataset, fits a model, writes a saved model. Created **only** by `mltask.deploy_to_flow()` — there is **no** `recipe create-prediction-training` / `create-clustering` (training) verb because training-recipe payloads inherit lab MLTask configuration that has no standalone-recipe equivalent | Workflow: `dku ml create-prediction` → `dku ml train` → `dku ml deploy` (creates the training recipe + saved model in the flow). Same path for clustering |
| **Prediction Scoring** | Apply a saved prediction model to score a dataset | `dku recipe create-prediction-scoring -i input --output-ds scored --model SAVED_MODEL_ID` |
| **Clustering Scoring** | Assign cluster labels using a saved clustering model | `dku recipe create-clustering-scoring -i input --output-ds clustered --model SAVED_MODEL_ID` |
| **Evaluation** | Compute metrics for a saved model against a labelled dataset | `dku recipe create-evaluation -i labelled --output-ds metrics --model SAVED_MODEL_ID` |

For LLM-based scoring/evaluation see GenAI recipes below — `create-llm-eval`, `create-agent-eval`.

## SQL recipes

Two modes, very different ergonomics:

- **`sql_query`** — single SELECT, raw text payload. Output dataset *must already exist* (it's a `SingleOutputRecipeCreator`, not a `CodeRecipeCreator`). Run `apply-schema` before the first build, otherwise `INSERT has more expressions than target columns`. Reference output table as `${projectKey}_<dataset>` — the `${DKU_DATASET_<name>_TABLE_NAME}` form is not valid in `sql_query`.
- **`sql_script`** — multi-statement script. CLI: `dku recipe create-sql-script NAME --connection CONN --sql @file.sql -P PROJ`. Multiple inputs/outputs supported; useful for stored-procedure-like flows or DDL. Recipe-level params (NOT in payload) tune the parser:
  - `--use-psql` / `usePsql` — treat the body as a psql-style script. Required for backslash directives (`\copy`), `IF NOT EXISTS` blocks, or DELIMITER-style stored-proc bodies. Off by default.
  - `--statements-mode {SPLIT,UNIFIED,RAW}` / `statementsParsingMode` — `SPLIT` (default) runs each `;`-separated statement as its own JDBC call (REQUIRED for `CREATE TABLE; INSERT INTO; SELECT...` chains on Snowflake — the JDBC driver rejects multi-statement payloads without splitting); `UNIFIED` sends the whole body as one batched statement; `RAW` disables splitting entirely.
  - `--allow-multiple-connections` / `allowMultipleConnections` — let the script span connections (advanced).
  - `--no-infer-output-schema` / `inferOutputDatasetsSchema:false` — skip schema inference from the script.
  - `--skip-prerun-validate` / `skipPrerunValidate` — skip pre-run validation (useful for scripts depending on objects created mid-execution).

Use SQL when you've already concluded a visual recipe can't express the logic, OR when porting an existing `passthrough SELECT` that's already production-quality.

## EDA / feature-engineering recipes

| Recipe | What it does | CLI verb |
|---|---|---|
| **`eda_univariate`** | Univariate analysis (frequency tables, quantiles, summary stats, confidence intervals) | `dku recipe create-eda-univariate NAME -i in --output-ds out --analyse VISIT:CATEGORICAL --analyse AVAL:NUMERICAL [--with-frequency-table] [--with-quantile-table] [--with-confidence-intervals] [--confidence-level 0.95]`. Migration target: SAS `PROC FREQ` + `PROC UNIVARIATE`, R `summary()` chains. |
| **`generate_features`** | Auto feature engineering — DSS scans the dataset and synthesises derived features (date parts, text length, categorical encodings, ...) | `dku recipe create-generate-features NAME -i raw --output-ds raw_with_features -P PROJ`. Tune via `set-settings` after creation. |

## LLM / GenAI recipes

| Recipe | What it does | CLI verb |
|---|---|---|
| **`prompt`** | Batch LLM generation, one row per input. STRUCTURED mode (default) uses single-brace `{var}` placeholders in `payload.prompt.structuredPromptPrefix`; TEXT mode uses double-brace `{{var}}` in `payload.prompt`; CHAT mode for multi-turn. **Trap**: writing TEXT-mode body to STRUCTURED storage path silently produces an empty no-op recipe. | `dku recipe create-prompt NAME -i in --output-ds out --completion-llm LLM --structured-prefix 'Summarize: {body}' --input-var body=article_body [--response-format json]` |
| **`nlp_llm_user_provided_classification`** | Zero/few-shot text classification via NLI. Constrains output to user-provided class labels — much more reliable than asking an LLM to free-form pick a label. **Trap**: needs ≥2 `--class` values; with 1, the recipe builds but produces empty predictions. | `dku recipe create-llm-classify NAME -i in --output-ds out --completion-llm LLM --input-col TEXT_COL --class urgent --class routine [--hypothesis-template '...'] [--explain-output] [--example 'TEXT||LABEL']` |
| **`nlp_llm_rag_embedding`** (Embed Dataset) | Embed a text column into a Knowledge Bank | `dku recipe create-embed NAME -i in --output-kb KB --embedding-llm LLM --embed-column body --metadata-col title --metadata-col url`. **`--metadata-col` is the priority gap**: without it, retrieved chunks lose source attribution and RAG citations break. |
| **`embed_documents`** (Embed Documents) | Extract + chunk + embed documents from a managed folder | `dku recipe create-embed-docs NAME -i pdf_files --output-kb KB --embedding-llm LLM [--chunk-size N --chunk-overlap N] [--vlm VLM] [--ocr-engine TESSERACT --ocr-languages eng,fra]` |
| **`nlp_llm_evaluation`** (LLM eval) | Score LLM outputs against ground truth | `dku recipe create-llm-eval NAME -i in --eval-store ID [--metrics ...] [--bleu-tokenizer 13a] [--bertscore-model X] [--temperature 0]` |
| **`nlp_agent_evaluation`** (Agent eval) | Score agent tool-call accuracy | `dku recipe create-agent-eval NAME -i in --eval-store ID --metrics toolCallExactMatch,...` |

## Python recipes

Use only as the last resort. Things that justify Python:
- Multi-row state machines that don't fit Window
- Hash lookup with prefix/range/fuzzy keys (no SQL `BETWEEN`-friendly form)
- Arbitrary HTTP / webhook / API IO
- Whole-text regex-with-state (e.g. parse a log into events)
- Custom geospatial beyond GeoJoin / `geo*` GREL formulas (shapely-heavy)

Don't use Python for:
- "Easier than learning the Pivot recipe" — learn the Pivot recipe
- Trivial cleanup that fits in a Prepare recipe
- Joins that are equi-joins (use Join recipe, even if there are 4 keys)
- Simple aggregations (use Group recipe, even if there are 10 metrics)

## Decision tree

```
Is the operation row-local (per-row, no neighbors)?
├─ Yes → Prepare recipe
└─ No → Does it group / aggregate?
        ├─ Yes → Group recipe (set --no-global-count)
        └─ No → Does it combine two datasets?
                ├─ Equi-join → Join recipe
                ├─ Spatial   → GeoJoin recipe
                ├─ Stack     → Stack recipe
                └─ No → Does it need order / window / lag?
                        ├─ Yes → Window recipe
                        └─ No → Does it pivot / unpivot?
                                ├─ Yes → Pivot recipe
                                └─ No → Does it dedupe?
                                        ├─ All cols are key → Distinct recipe
                                        └─ Subset is key   → Window + ROW_NUMBER==1
```

If every node in the tree says "no", that's the signal to drop to SQL — and only if SQL says no, then Python.

## When you genuinely need to fall back

Pattern: build the upstream and downstream as visual recipes, isolate the un-visual step into the smallest possible SQL or Python recipe in the middle. Don't write one giant SQL recipe that subsumes upstream and downstream too — that destroys readability and forfeits the visual layer's reviewability.

---

## Use the visual recipe pipeline — collapse N recipes into 1

Every visual recipe (Group, Window, Join, Distinct, TopN, Pivot) runs an internal pipeline:

```
INPUT → preFilter → computedColumns → THE ACTION → postFilter → OUTPUT
                                       (group / window /
                                        join / topN / …)
```

The CLI shortcuts (`create-group`, `create-window`, etc.) configure only the action stage. The other three stages — pre-filter, computed columns, post-filter — are accessible by reading the payload, editing it, and writing it back. **They are massively under-used by agents**, who tend to build a chain of 4 recipes when one would do.

### Worked example — 4 recipes → 1

**Naïve translation:** "filter on `active=true`, compute a `bucket` column, group by region+bucket summing amount, drop groups with sum < 200":

```
filter_active        (Prepare, FilterOnCustomFormula on active==true)   → orders_active
prep_bucket          (Prepare, CreateColumnWithGREL for bucket)         → orders_bucketed
grp_region_bucket    (Group, sum amount)                                → orders_summary_raw
filter_min_sum       (Prepare, FilterOnCustomFormula amount_sum>=200)   → orders_summary
```

That's 4 recipes and 3 intermediate datasets.

**Pipeline-aware translation:** *one* Group recipe with all four stages populated:

```bash
dku recipe create-group g_orders -i orders --output-ds orders_summary \
    -k region --agg "amount:sum" --no-global-count -P PROJ
# Then patch the payload to add preFilter, computedColumns, postFilter:
dku recipe get-settings g_orders -P PROJ -o json > /tmp/g.json
# Edit /tmp/g.json's payload object — add:
#   preFilter:        { enabled, distinct: false, uiData: {mode:"&&", conditions:[...]} }
#   computedColumns:  [ { name:"bucket", type:"string", mode:"GREL", expr:"if(amount>=200,...)" } ]
#   keys:             [ {column:"region"}, {column:"bucket"} ]   ← computed col used as a key
#   postFilter:       { enabled, distinct:false, uiData:{mode:"&&", conditions:[{input:"amount_sum","operator":">= [number]","num":200}]} }
dku recipe set-settings g_orders -s @/tmp/g.json -P PROJ
dku recipe apply-schema g_orders -P PROJ
dku recipe run g_orders -P PROJ
```

**Result:** 1 recipe, 1 output dataset, single engine pass. Per-recipe schemas in `dataiku/references/visual-recipe-payloads.md`.

### Stages by recipe

| Recipe | preFilter | computedColumns | Action stage | Custom aggregations | postFilter |
|---|---|---|---|---|---|
| Group | top-level | top-level | `keys` + `values` (boolean flags) | `values[]` entries with `customExpr` + `customName` (SQL engine only) | top-level |
| Window | top-level | top-level | `windows` + `values` | — | top-level |
| Distinct | top-level | — | `keys` | — | top-level |
| TopN | top-level | top-level | `keys` + `orders` + `topN` | — | top-level |
| Join | per-input: `virtualInputs[i].preFilter` | per-input: `virtualInputs[i].computedColumns` | `joins[]` + `selectedColumns` | — | top-level |

### Custom aggregations (Group recipe)

The Group recipe's `values[]` array accepts arbitrary SQL aggregate expressions alongside the standard ones. Distinguished by `customExpr` + `customName` instead of `column` + boolean flags:

```json
{
  "customExpr": "max(\"price\") - min(\"price\")",
  "customName": "price_range",
  "type": "DOUBLE"
}
```

Use for anything not exposed by the boolean flags: `PERCENTILE_CONT`, `STRING_AGG`, conditional aggregations (`SUM(CASE WHEN status='A' THEN amount ELSE 0 END)`), variance forms, etc. **Custom aggregations can reference `computedColumns`** — `min(AAAA)` aggregates over the `AAAA` column derived earlier in the same recipe. SQL engine required (won't run on the in-memory DSS engine).

Full schema in `dataiku/references/visual-recipe-payloads.md` § Custom aggregations.

### Validate before you run — read `$status`

**Which recipe types populate `$status`?** Only the visual recipes that have a payload-level filter pipeline — Group, Window, Join, TopN, Distinct (for their `preFilter` / `postFilter`). Prepare/`shaker`, Stack, Sort, Sampling, Pivot do **not** carry a `$status` block in `get-settings` output, so a `jq '."$status".ok'` query returns `null` / `(no status)` and is not a meaningful gate. Validate those instead by:

| Recipe type | Validation move |
|---|---|
| Group / Window / Join / TopN / Distinct | Read `$status` on the filters as below |
| Prepare (`shaker`) | `dku recipe check-schema RECIPE -P PROJ` (per-step validation) and inspect `dku dataset head OUTPUT -n 5` after build |
| Stack | Build then `dku dataset head OUTPUT` — the only meaningful runtime check |
| Sort / Sampling / Pivot | Same — there is no payload-level validator |

After `set-settings`, every filter slot on the supported recipe types carries a `$status` block populated by DSS during validation. **Use it as a programmatic post-write check** before triggering a build — it surfaces config errors instantly instead of waiting for a job to fail:

```bash
# After set-settings, confirm both filters are valid
dku recipe get-settings g_orders -P PROJ -o json | jq '
  .payload | {
    preFilter:  {ok: .preFilter."$status".ok,  fullyTranslated: .preFilter."$status".fullyTranslated,  message: .preFilter."$status".message},
    postFilter: {ok: .postFilter."$status".ok, fullyTranslated: .postFilter."$status".fullyTranslated, message: .postFilter."$status".message}
  }'
```

What to gate on:

| Field | Read it as |
|---|---|
| `ok: true` | Configuration is valid — safe to `apply-schema` + run |
| `ok: false` | Stop. Read `message` and fix before running |
| `fullyTranslated: true` | All expressions translated to the target engine. SQL push-down is intact |
| `fullyTranslated: false` | Part of the formula falls back to the in-memory engine. **On a SQL-only flow, this silently breaks rule 2** — investigate which fragment didn't translate |
| `validated: false` | Validation hasn't run yet (just-saved, stale block) — re-fetch settings or trigger a save again |
| `message` | Human-readable issue. **Caveat: can be stale** — observed on a working recipe whose `message` still complained about a long-fixed parse error from earlier UI edits. Trust `ok` over `message` |

### Debugging tip — read `$status.sql`

The same `$status` block also contains a `sql` field with the **compiled SQL DSS will push to the engine**. Authoritative source for what's actually running:

```bash
dku recipe get-settings g_orders -P PROJ -o json \
  | jq '.payload | {preFilter_sql: .preFilter."$status".sql, postFilter_sql: .postFilter."$status".sql}'
```

If a filter "isn't firing", read its `$status.sql` first — usually it reveals that the predicate compiled to something different from what you wrote (or didn't compile at all, in which case the slot is in the wrong `uiData.mode`). For postFilter specifically, `$status.schema` shows the column list available after the action stage — confirms which custom-aggregation `customName`s and which `count` column you can reference.

### Filter mode — pick the right `uiData.mode`

Three modes — the trap is mismatching the mode flag with the field you populated.

| `uiData.mode` | What DSS evaluates | Syntax | Use when |
|---|---|---|---|
| `"&&"` or `"\|\|"` | `uiData.conditions[]` (visual) | per-condition objects | Single- or multi-column comparisons composable as AND/OR |
| `"CUSTOM"` | `expression` (formula) | GREL — `val("col") != 0` | Formulas, GREL functions, references to computed columns; works on every engine |
| `"SQL"` | `expression` (raw SQL) | SQL — `"col" != 0 AND "status" = 'A'` | SQL-only predicates (subqueries, vendor-specific functions). SQL engine required |

**Empirical check (Group recipe, 10-row input):** `expression: "active"` + `uiData.mode: "&&"` + empty `conditions: []` returned all groups (filter ignored). Same `expression` with `uiData.mode: "CUSTOM"` returned only the rows where active was true (filter honored).

Canonical formula-mode shape (matches the DSS UI's saved output):

```json
{
  "enabled": true,
  "distinct": false,
  "uiData": {
    "mode": "CUSTOM",
    "$latestOperator": "&&",
    "$filterOptions": "CUSTOM",
    "conditions": []
  },
  "expression": "amount_sum >= 300 && status == 'A'"
}
```

`$latestOperator` and `$filterOptions` are UI metadata (preserved across mode toggles) — keep them on read-modify-write but they're not required for evaluation.

### Window aggregation framing — `last(col)` is NOT cumulative

DSS Window aggregations (`sum`, `max`, `last`, `first`, `count`) computed via `--compute 'TYPE:COL:'` default to a frame of **current row only** — NOT "unbounded preceding to current row" — even with `enableLimits: false` on the window definition. This trips agents using `last(col)` for forward-fill: it returns the current row's own value, not the most recent non-null value seen.

| Goal | Wrong (current-row-only) | Right |
|---|---|---|
| Cumulative sum (running total) | `--compute 'sum:val:'` | Same — `sum` IS cumulative when an `--order-key` is set with no partition |
| Forward-fill (last non-empty) — monotonic data only | `--compute 'last:val:'` (returns current row's value) | `--compute 'max:val:'` — empty strings sort lexicographically before non-empty, so cumulative max picks up the latest filled value. Works for `'07' → '08'`, FAILS for `'08' → '09' → '08'`. |
| Forward-fill — general / non-monotonic | (no single-Window solution) | Two Windows: (a) cumulative `sum(is_set)` → `group_id`, (b) partition by `group_id` + `max:val:` (within a group only one row has `val` set, so max returns it). |
| Next row's value (lookahead) | — | `--compute 'lead:val:'` (default offset 1) or `--lead-offsets 'val:1,2,3'` for multi-offset in one Window. Always `--rename val_lead:next_val` since the third segment of `--compute 'TYPE:COL:OUTPUT'` is silently ignored. |
| Full-partition aggregate (same value every row) — Alteryx Summarize+Join, or `df.groupby(...).transform("mean")` | `--compute 'avg:val:'` (cumulative within partition, even with no order-key — partition-wide value only on the LAST row) | `--compute 'avg:val:' --frame-unbounded` — sets `enableLimits=True` + `limitPreceding/Following=False` + payload-level `legacyUnboundedWindowStreamBehavior=True`. All three are required: without the legacy flag, DSS streams cumulatively even with the limits cleared. Replaces a Group + Join chain with a single Window. |

The cumulative-max trick is the single-Window workaround for forward-fill of monotonic ordinals (year strings, sortable IDs, dates). For anything else, accept the two-Window pattern.

The `legacyUnboundedWindowStreamBehavior` flag is poorly named — "legacy" refers to the original DSS-pre-streaming-engine semantics where unbounded windows produced full-partition results. Newer DSS versions stream cumulatively unless the flag is set. The CLI's `--frame-unbounded` flag is the clean way to ask for this; if you've built the Window without it, edit via `dku recipe set-settings -s '{"payload": {…, "legacyUnboundedWindowStreamBehavior": true}}'`.

### When NOT to collapse

Three cases where keeping separate recipes is correct:
- **The intermediate dataset is itself a deliverable** (downstream consumers, reused as input by another recipe, exposed in a dashboard). Collapse loses that artifact.
- **The pre-filter changes the semantics of how the source step migrates.** If a SAS `where` clause defines a separate logical dataset (e.g. `WORK.HE_ACTIVE` is referenced by name in 5 other steps), keep the filter as its own Prepare recipe so the downstream references resolve.
- **The action runs on a different engine** than the upstream prepare you'd want to fold in (SQL Group with a Python-only formula in computedColumns won't push down). In that case the formula belongs in a Prepare upstream that runs on the right engine.
