# Common dku-cli gotchas

Dataiku- and CLI-level traps that bite anyone using `dku` — whether building a flow from scratch, migrating from another tool, or wiring up a one-off pipeline. Read the entry that matches your symptom; each row tells you the fix.

## Dataset / schema

| Gotcha | Fix |
|---|---|
| Upload auto-detects all columns as STRING | Always `set-schema` with correct types immediately after upload |
| `dku dataset upload` silently appends when the local filename differs from a previous upload | Same filename → upload errors without `--overwrite`. Different filename → both files coexist in the UploadedFiles dataset (rows from both surface in `dataset head`), no warning. Always pass `--overwrite` / `-f` when re-uploading after a format tweak |
| Single-column CSV with embedded commas auto-detects with `separator: ","` and the wrapping `"` of each row gets stripped on read | `dku dataset get-definition → set-definition` with `formatParams.separator = "\t"` (or any char absent from the data), `quoteChar = ""`, `parseHeaderRow = true`, and an explicit `schema.columns: [{"name": "<col>", "type": "string"}]`. Verify with `dataset head -o json` before adding split steps |
| `set-schema` with `type: date` on CSV → all null | Keep as `string`; cast inside a Prepare step (`DateParser`) — ISO strings compare and aggregate chronologically anyway |
| `dku dataset info` row count is stale after build | Pass `--recompute` — DSS does not auto-recompute metrics on build |
| `dateonly` JSON has trailing `00:00:00` | Strip to first 10 chars in parity checks |
| `dku dataset create --type SQL` fails on restricted licenses | Use the concrete subtype: `--type PostgreSQL`, `--type Snowflake`, etc. |
| Default `create --type <SQLType>` params miss `mode` and `table` | Pass `--definition '{"params":{"connection":"<c>","mode":"table","table":"${projectKey}_<name>"}}'` |

## Recipe creation / execution

| Gotcha | Fix |
|---|---|
| `apply-schema` required before first run | Otherwise computed columns silently missing |
| `apply-schema` ALSO required after adding rename/formula/select steps to an EXISTING Prepare recipe | First `apply-schema` propagates the upstream input schema only. Adding `ColumnRenamer` / `CreateColumnWithGREL` / `ColumnsSelector` steps later silently leaves the output dataset's schema stale until you `apply-schema` again, then re-run. Since 2026-04, `dku recipe run` emits a hint when it detects schema-changing steps without `--auto-update-schema` |
| `add-step --type CreateColumnWithGREL --params '{"column":"x","expr":"y"}'` runs but the formula is a no-op | The processor reads `expression` (NOT `expr`). DSS silently ignores unknown processor params, so the step adds an empty column to the output schema and the recipe runs `successfully`. Symptom: downstream column appears empty; CLI emits an exit-2 error since 2026-04 (`wrong_param_key`). Fix: use `"expression"` in raw `--params` JSON, or prefer `dku recipe add-formula --expr ... --column ...` which maps to the correct key. Same silent-ignore pattern as MinMaxProcessor / FillColumn / ArrayUnfold (CLAUDE.md gotchas) |
| Window aggregation `sum:col` / `avg:col` fails: `Cannot sum non-numeric column X of type STRING` even though the upstream Prepare's `CreateColumnWithGREL` produces numeric expressions | GREL formula columns default to STRING in the output schema regardless of expression type — `toNumber(...)` returns a number at evaluation time but the schema still types the column as `string`. **Fix:** after the Prepare runs, type the column explicitly: `dku dataset set-schema OUTPUT_DS -P PROJ -d "$(dku dataset schema OUTPUT_DS -P PROJ -o json | jq 'map(if .name=="col" then .type="bigint" else . end)' -c)"`. The `TypeSetter` Prepare processor accepts a `newType` enum but the value is opaque (Java FQCN; not safely guessable from outside DSS source) — `set-schema` is the working route until the enum is documented |
| Window output column names default to `<col>_<agg>` regardless of the third-segment alias in `--compute TYPE:column:OUTPUT` | The third segment is advisory; DSS auto-names. With empty input data a `--post-filter 'rn == nb_active_months'` against the advisory names parses fine and runs successfully (no rows = no formula evaluation), masking the bug — only fails when real rows arrive with `Unknown column 'rn'`. **Fix:** use `--rename customer_id_count:nb_active_months --rename rownumber:rn` to force the names referenced in `--post-filter`. The same trap applies to `count:` (output `<col>_count`) and `rowNumber::` (top-level output `rownumber` — lowercase) |
| Sampling recipe with `uiData.expression` filter silently drops the predicate | DSS rewrites `selection.filter.uiData` to `{mode: "CUSTOM", conditions: []}` on save — your filter becomes a no-op, same row count out as in, no error. Only the bare `selection.filter.expression` (string) shape is honored. The CLI's `create-filter` builds a Prepare recipe with `FilterOnCustomFormula` — that schema isn't mutated. **Verified shapes (input 10 rows, filter `age > 30`, expected 5):** `selection.filter.expression` bare → 5 ✅; `uiData.expression` only → 10 ❌; `formula` key → 10 ❌; Prepare + `FilterOnCustomFormula` → 5 ✅ |
| Group / Window / Distinct / TopN `preFilter` or `postFilter` formula silently ignored | The filter slot keys off `uiData.mode`: `"&&"` / `"||"` → DSS evaluates `uiData.conditions[]` (visual mode); `"CUSTOM"` → DSS evaluates the **top-level** `expression` (formula mode). Putting the GREL string only inside `uiData.expression` makes DSS fall through to the empty conditions array (matches all rows). The `dku recipe create-{group,window,distinct,topn,stack}` flags `--pre-filter` / `--post-filter` / `--input-filter` now emit the canonical CUSTOM shape (top-level `expression` + `uiData.mode == "CUSTOM"` + empty `conditions[]`); only matters when you hand-edit recipe JSON via `set-settings`. **Verified on a Group recipe** (input 10 rows, postFilter `expression: "amount_sum >= 300"`): with `mode: "&&"` + empty `conditions[]` → 4 rows (filter ignored); with `mode: "CUSTOM"` + top-level `expression` → 2 rows ✅ honored. Canonical CUSTOM shape in `dataiku/references/visual-conditions.md` |
| Group recipe adds an extra `count` column | Pass `--no-global-count` for SQL / Summarize parity |
| Group outputs auto-named `{col}_{func}` | Add `add-rename` to restore source aliases (`amount_sum` → `total_revenue`) |
| Join recipe: column-name collision silently suffixes with `_1` | Rename in the upstream Prepare step so both sides have unique names |
| Stack recipe: column-name mismatch leaves values null or drops columns depending on mode | Use `dku recipe create-stack --mode UNION` (default) to keep the superset of input columns. Use `--mode INTERSECT` only when you deliberately want columns present in every input, or `--mode FROM_DATASET:NAME` to copy one input's schema. Pre-rename upstream with `ColumnRenamer` when differently named columns are semantically the same |
| Stack: I added a Prepare per input just to tag `source = "<filename>"` | That's the canonical anti-pattern. `dku recipe create-stack --origin-column source` builds the tag column directly. With `--origin-label INDEX:VALUE` you can override the per-input label. One Stack call replaces N tag-only Prepares |
| `apply-schema` fails with `UnavailableTypeException: Type X was available in a plugin that is not installed` | The processor ID is unknown to DSS. Cross-check `type` against `dataiku/references/prepare-processors.md` and `dku-cli/references/commands.md` before adding the step |
| `add-fold` errors with `FoldColumnsByName ... plugin is not installed` (older CLI) | Reinstall the global CLI: `uv tool install --from . dku-cli --force --reinstall`. Recent versions emit the stock `MultiColumnFold` (no plugin needed). Never fall back to `pd.melt` for unpivot — and consider whether the unpivot is needed at all (often you can compute the per-group aggregate inline, before any reshape) |
| `MultiColumnFold` (`add-fold`) silently DROPS rows where the value column is null | The fold step emits one row per `(key, value)` pair, but rows where the cell would be null are dropped — no warning. Pre-impute with `add-fill-empty` (one step per folded column) BEFORE the fold to preserve those rows. If the original null status must be preserved (rare), use a sentinel: cast each metric to a string col with `if(isBlank(strval("col")), "@@NULL@@", concat("", numval("col")))`, fold, then `add-find-replace --matching FULL_STRING --find @@NULL@@ --replace ""` |
| Window's `Lag(col, k)` returns null at the partition boundary (no edge-fill) | DSS Window's `lag` returns null when the offset runs off the start/end of the partition. Add a `FirstValue(col)` aggregation in the same Window AND a Prepare formula `if(isBlank(strval("col_lagk")), numval("col_first"), numval("col_lagk"))` per offset to coalesce against the edge value. Required for parity with Alteryx `MultiRowFormula` `<OtherRows>Nearest</OtherRows>` (see `migration/ayx/translation.md` § MultiRowFormula) |
| Window CLI's `--compute lag:col:` only accepts ONE default offset (1) | For lag offsets `1..N`, get the recipe settings, edit `payload.values[]` for the target column to set `lag=true` and `lagValues="1,2,…,N"` (comma-separated string), then `set-settings`. The `--compute` flag is a quick path for the common single-lag case |
| Window `--rename SRC:DST` applies AFTER `--post-filter` — post-filter referencing the renamed column silently produces ZERO rows | DSS evaluates `--post-filter` on the windowed (pre-rename) schema, then applies `outputColumnNameOverrides` to the output dataset. So a recipe with `--compute 'lead:Field_1:next_field' --rename 'Field_1_lead:next_field' --post-filter 'startsWith(strval("next_field"), "(")'` filters on a column DSS doesn't see yet → the filter evaluates to null on every row → output is empty (no error, no warning, just 0 rows). **Fix:** in `--post-filter`, reference the PRE-rename name (`Field_1_lead`, not `next_field`). The output dataset still gets the renamed name in its schema — the rename works, only the filter expression sees pre-rename names. Same trap if you rename a Window's `rownumber` / `_lag` / `_avg` output and then filter on it. (Window `--rename SRC:DST` itself works — supersedes earlier "cannot be renamed inline" guidance; the trap is only the filter ordering.) |
| `dataset delete` cascades to recipes silently | Deleting a dataset that's an INPUT to another recipe removes that recipe from the project (no warning prompt for the cascade). After `dataset delete`, re-list recipes and recreate any that disappeared. Affected most often when prototyping Stack chains |
| `create-pivot` build fails with `RecipeSchemaComputer$DontWantToCompute: Modality lists stored in output schema are not up-to-date` | The pivot's modality scan is UI-only **only when `--value-limit TOP_N` (the default) is used**. `dku` cannot trigger the scan — even `set-settings` with `pivots[0].explicitValues = [["A"], ["B"], …]` updates the recipe payload but does NOT populate the output dataset's modality cache. **First workaround: pass `--value-limit NO_LIMIT`** (or `EXPLICIT --explicit-values v1 --explicit-values v2 …`) — DSS resolves modalities at build time without needing the cached scan, the build succeeds. Use NO_LIMIT for cardinalities under a few dozen (one column per modality, headless-safe); use EXPLICIT when you want a deterministic whitelist regardless of input row presence. **Second workaround:** restructure to avoid the pivot — compute the N columns inline upstream with `add-formula` (one per modality). See `migration/ayx/translation.md` § CrossTab |
| `create-pivot --rename SRC:DST` is silently ignored — output dataset still uses the auto-generated names (`<modality>_<value>_count`, `<col>_sum`, `<col>_min`, etc.) | DSS Pivot does not honor the top-level `payload.outputColumnNameOverrides` field that other visual recipes (Group, Window, TopN, …) read. The CLI writes the overrides into the payload but they're a no-op for Pivot — both for pivoted-modality outputs AND for `--other-column` carry-through outputs. **Workaround:** chain a downstream Prepare with `add-rename --mappings '{"1B_Position_count": "1B", …}'`. Bulk renames in one Prepare step are cheap; the only cost is one extra recipe in the flow. Tested on Challenge_030 (fantasy-baseball summary): 12 renames across pivoted and other-column outputs, all silently dropped at the Pivot level, all applied at the downstream Prepare level. Filed as a CLI gap (`create-pivot` should reject `--rename` with a prescriptive error pointing at `add-rename`, OR find the per-pivot field DSS actually reads). |
| `create-join --cols 'INDEX:c1,c2,c3'` is silently ignored — output dataset contains the FULL union of input columns instead of the projection | DSS Join's `virtualInputs[i].selectedColumns` requires a list of dict objects `[{"name": "c1", "table": <i>, "type": "<inferred>"}, ...]`, NOT a plain string list. The CLI's `create-join` writes `vi["selectedColumns"] = ["c1", "c2", ...]` (string list) and DSS silently falls back to AUTO mode. Same shape gotcha as the self-join AUTO_NON_CONFLICTING trap (CLAUDE.md). **Workaround:** chain a downstream Prepare with `add-step ColumnsSelector --params '{"keep":false, "columns":["unwanted_col"], "appliesTo":"COLUMNS"}'` to drop unwanted columns. Tested on Challenge_031: `--cols '0:Surf Site,Swell Direction,…' --cols '1:Surf Season,Location,Lat,Long'` was silently ignored (Site column from left side leaked into output); a 1-step ColumnsSelector Prepare downstream fixed it. **CLI gap:** `create-join --cols` should write `selectedColumns` as `[{"name": col, "table": idx, "type": <type from input schema>}, ...]` — requires looking up the column types from each input dataset's schema at recipe-creation time. |
| `create-join` with 3+ inputs sets `table1=0` on every join past the first — second join keys off the original left table, not the running join result | The CLI's multi-input join wires `joins[i].table1` to 0 (first input) for every join pair instead of `i` (last-joined virtual table). Build fails with `Invalid join condition: Dataset X has no column Y` when the second join key only exists in input 1. **Workaround:** `get-settings`, fix `joins[i].table1` and `joins[i].on[*].column1.table` to `i` for each subsequent join, then `set-settings -s @file.json` (sending only `{"payload": {...}}`, not the full settings dict — the latter errors with `dictionary update sequence element #0 has length 1; 2 is required`). |
| `create-group` with no `-k` (global aggregate, single output row) crashes at run time with `AssertionError` in `ExpressionUtils.getSchemaColumn` | Recent CLI clears the dataikuapi grouping builder's `keys: [{}]` placeholder to `keys: []` automatically — rebuild the global CLI (`uv tool install --from . dku-cli --force --reinstall`) if you still hit it. The global-aggregate pattern is "one Group with `keys: []`, `computedColumns` for any per-row indicator, then aggregates summing/counting over all rows" — useful for the final reduce step in count-and-percentage pipelines |
| `dataset detect --save` on a `FilesInFolder` dataset pointing at a `.yxdb` prints "Detected and saved: yxdb format, N columns" but persists nothing — `formatType` stays empty, `schema.columns` stays `[]`, subsequent `dataset head` errors with `Missing format type` | The detection runs and prints the right schema, but the save path does not write `formatType` for the yxdb format. **Workaround:** `dataset get-definition`, set `formatType: "yxdb"`, `formatParams: {}`, and an explicit `schema.columns: [...]` array (use the printed detection output as the source of truth), then `dataset set-definition -d @file.json`. `dataset info --recompute` and `dataset head` both work after that |

## SQL recipes (`sql_query`)

| Gotcha | Fix |
|---|---|
| `sql_query` output dataset must pre-exist | `sql_query` is a `SingleOutputRecipeCreator`, not a `CodeRecipeCreator`. Create the output first |
| `sql_query` recipe payload is raw text, not JSON | `get-definition` and `set-code` on SQL recipes handle text payloads |
| SQL recipe output table has 0 columns initially | Run `apply-schema` before the first build — otherwise `INSERT has more expressions than target columns` |
| `${DKU_DATASET_<name>_TABLE_NAME}` not valid in `sql_query` | Use `"${projectKey}_<dataset>"` — DSS substitutes at run time |

## GREL formulas

| Gotcha | Fix |
|---|---|
| `create-filter` formula rejects `` `col with space` `` backticks with `ParsingException at offset 0` | GREL filter/formula parser does not accept backtick-quoted identifiers. Use `numval("col with space")` / `strval("col with space")` to reference the column by quoted name |
| `numval(expr, default)` with a non-literal first arg silently returns empty (and the output column gets typed as `string`) | `numval` / `strval` / `val` take a quoted column NAME, not an expression. For string→number conversion inside a formula, use `toNumber(split(Range,"-")[0])` — `toNumber()` is also correctly inferred as `bigint` by `apply-schema` |
| `strval(numeric_col)` returns "" — silent — for any numeric (`bigint` / `double`) column | `strval()` is a string-coercion-on-string-column accessor and returns empty for non-string types. To convert a numeric column to a string in a formula, use `concat("", numval("col"))` — `concat` forces string concatenation and `numval` returns the numeric value cleanly. The bareword form `concat("", col)` is sometimes unreliable (column name parsing ambiguities); prefer the quoted `numval("col")` form universally |
| Set-schema overrides the dataset's column ORDER metadata, but the on-disk file still has the original order — silent type-mismatch reads | `dku dataset set-schema -d @file.json` only updates metadata, NOT the file content. If your declared column order in the schema differs from the actual file's column order, DSS interprets columns by POSITION → silent garbage (string columns parsed as bigint = null, etc.). Verify with `head -o json` after `set-schema`: keys appear in the schema's declared order, but values come from the FILE's positional order. **Always match the schema's column order to the actual file order** — for a Prepare's output, use `head -o json` first to see the file's column order, then declare schema accordingly. Or use a `ColumnReorder` step at the end of the Prepare to force the desired order on disk |
| Schema does NOT auto-propagate downstream when an input dataset's types change (e.g., bigint → double) | After changing an input's schema, the downstream managed datasets keep their previously-locked types. `apply-schema` reports "no schema updates needed". Data flows through but values get coerced to null where the new type doesn't fit. **Fix:** explicitly `set-schema` on EACH downstream managed dataset to update the type, then re-run the chain. There's no automatic propagation. For long pipelines, scripting a per-dataset set-schema pass is faster than tracking which one is stale |
| `computedColumns` entries in Group/Window/Join recipes CANNOT reference each other — silent failure | When you list `[{name:"a",expr:"f(x)"}, {name:"b",expr:"g(a)"}]`, expression `g(a)` evaluates against the INPUT row, not against `a`'s value, and `a` is treated as missing/empty. No error; aggregations downstream silently produce uniform 0/all-rows output (the conditional always falls into one branch). **Fix:** inline every reference. If `is_open` and `is_closed` both need `substring(strval(d), 0, 10)`, paste the substring expression in both — don't try to build a chain of helper computedColumns |
| `<` / `>=` between a date-typed column and a GREL `asDateOnly()` value crashes with `Invalid format: "2013-04-03T00:00:00.000Z" is malformed at "T00:00:00.000Z"` | Date columns surface to GREL formulas with the full ISO8601 form including `T...Z`, while `asDateOnly()` returns date-only. The comparison operator tries to parse the date column's string form with the date-only parser and fails. **Fix:** cast both sides to `yyyy-MM-dd` strings via `substring(strval(date_col), 0, 10)` and compare lexically — ISO8601 string ordering matches date ordering. For "same month" checks, prefer `substring(strval(date_col), 0, 7) == substring(strval(month_str), 0, 7)` over date-arithmetic with `inc()` |

## Folders & file formats

| Gotcha | Fix |
|---|---|
| `dku folder create-dataset` always defaults `formatType: "csv"` regardless of the file extension in the folder | An `.xlsx`-only folder gets parsed as CSV — DSS reads gibberish and `dataset head` returns empty/garbled rows with no error. Pass `--format excel` (or `parquet`/`json`/`avro`/`yxdb`) explicitly. For Excel, also set `--sheet NAME` (or `--sheet-index N`) and `--skip-rows-before` if the data isn't on row 0. Verify after with `dataset get-definition` → `formatType` and `dataset head -o json`. **Never** rely on auto-detection through `dataset detect --save` — for non-csv formats it prints the right schema but doesn't always persist `formatType` |
| `dku plugin get-file <plugin> <path>` errors on dev plugins with `'utf-8' codec can't decode byte 0x8b` | The CLI streams the file as text; gzipped or binary plugin assets (e.g. compiled JS, model `.tar.gz`) crash. Workaround: clone the dev plugin's filesystem path directly under `<DSS_DATA_DIR>/plugins/dev/<plugin>/` instead of pulling via API |

## Saved models / ML

| Gotcha | Fix |
|---|---|
| `dku model list` returns LLM and agent objects (`type: "LLM_GENERIC_RAW"`, `"RETAIL_AUGMENTED_LLM"`, etc.) alongside trained ML models | The endpoint conflates saved-models with LLM-mesh registrations. Filter by `jq '.[] \| select(.type \| IN("PREDICTION","CLUSTERING","TIMESERIES_FORECAST","SOLUTION","CAUSAL"))'` to get only trained models; use `dku agent list` for agents and `dku llm list` for LLMs |
| `dku model get <ID>` returns blank `type: ""` | Saved-model settings have no top-level `type`; the CLI falls back to `model list` to populate it. If the fallback misses (e.g. project has 100+ models, model not in first page), pass `--output json` and pull `type` from `dku model list -P PROJ -o json \| jq '.[] \| select(.id=="<ID>")'` directly |
| Reference-data / data-prep projects have 0 scenarios + 0 saved models — that's intended, not unfinished | Many DSS projects exist purely to materialize curated datasets that downstream Solution projects bind to as remote inputs. Skip "no scenarios" warnings on these. Confirm by checking whether the project key is referenced as a remote input in the Solution-template projects (`dku project inspect SOL_X -o json \| jq '.datasets[]\|select(.params.projectKey)'`) |

## Secrets and credential exposure

| Gotcha | Fix |
|---|---|
| `dku dataset get-definition` on a plugin-connector dataset (`type: "CustomPython_<plugin>"`) returns `params.customConfig.<service_account>.inlinedConfig` containing the raw PAT/token in plain text | DSS does not redact credentials at the API level. NEVER pipe `dataset get-definition` output to chat, paste it into a wiki, or commit it to git. If you need the dataset definition, jq-strip the secret first: `jq 'del(.params.customConfig)' < def.json`. The same applies to `connection list -o json` for connections that store credentials inline |
| `dku webapp get-definition` exposes the webapp-scoped `apiKey` | Treat the output as secret. The `apiKey` field appears at the top level of webapp definitions and grants the same scope the webapp uses to call DSS APIs. Strip with `jq 'del(.apiKey, .config.apiKey)'` before sharing |
| `dku connection list -o json` may include `params.password`, `aws_secret_access_key`, OAuth refresh tokens | Same redaction recommendation. If you need to share a connection schema for support, regenerate via UI export (which DSS redacts) instead of API output |

## Cross-engine push-down

When the input AND output of a Prepare recipe are on the same SQL connection, DSS push-downs the formulas to SQL. This is fast but the GREL → SQL translation has gaps. Read `sql-engines.md` § GREL → SQL push-down gotchas before writing GREL on a SQL-pushed flow. Highlights:

- `"" + col` → SQL numeric addition, fails. Use `concat("", col)` for `int → string` casts.
- `toString(col)` is Shaker-side only and may not survive push-down.

---

## Error recovery

| Error | Fix |
|---|---|
| `dku whoami` fails | `dku auth login` |
| `Unknown function 'X'` in GREL | Case matters — `toTitlecase` not `toTitleCase`; `toLowercase` not `toLowerCase`. Check `dataiku` skill's GREL reference |
| `output dataset does not exist` | `dku dataset create DS --type Filesystem -c CONNECTION -P PROJ` |
| Recipe run fails | Run `apply-schema` first; then check connection / schema / formula syntax |
| Row count mismatch (when comparing to a known source) | If migrating: source-specific debugging in `migration/<source>/overview.md` § Row count mismatch. Otherwise: rerun `dku dataset info DS -P PROJ --recompute` first; check filters/null handling/string-vs-numeric in keys |
| Value mismatch on rounding boundaries (when comparing to a known source) | If migrating: source-specific rounding parity — `migration/sas/translation.md` § Rounding parity, or `migration/ayx/semantics.md` § Decimals. Otherwise: GREL `round()` is half-up; SQL engine rules vary; pandas defaults to banker's rounding |

---

## CLI / recipe gotchas

### Dataset create + upload
`dku dataset create` defaults to Filesystem, which does NOT support `dku dataset upload`. Use `--type UploadedFiles` for anything being uploaded via CLI. `dku dataset delete` and `dku recipe delete` prompt by default but support `--yes` / `-y` for non-interactive deletion. `dku project delete` requires `--confirm`, `--yes`, or `-y`.

### Code recipe create + connection
`dku recipe create` for code recipes fails if the project has no default managed connection. Always pass `--connection` / `-c` when creating Python/SQL recipes in projects without a default managed connection. Use `dku connection list` to find available connections (`filesystem_managed` is the most common). If `connection list` is unavailable, inspect an existing dataset with `dku dataset get-definition DS -P PROJ -o json | jq -r '.params.connection'`. Cross-project recipe inputs use `PROJECT_KEY.DATASET_NAME`. Visual recipe shortcuts auto-create outputs and don't need `--connection`.

### Dataset verification + schema reality
`dku dataset head -o json` returning `[]` means the dataset has 0 rows, not an error. Always verify built outputs with `dku dataset head OUTPUT -P PROJ -n 5` and inspect actual columns with `dku dataset schema OUTPUT -P PROJ` before assuming a recipe worked. Wiki plans and schema docs can lag the real dataset.

### Python recipe numeric IDs
ID columns from external datasets may contain nulls or non-numeric values. Never cast directly with `.astype("int64")`; use `pd.to_numeric(..., errors="coerce")`, `dropna`, then cast, or the recipe will fail with `IntCastingNaNError`.

### Snowflake `concat` aggregation + bigint precision
`--agg "col:concat"` in `create-group` compiles to Snowflake's `LISTAGG()`, which has a per-group result size limit. Large text/JSON columns (200+ chars per row, multiple rows per group) fail with error 300002. Fix: visual group for numeric aggs only, Python recipe downstream for JSON/text merging. Also: pandas loads Snowflake bigints as float64, losing precision for values > 2^53. Visual recipes preserve full precision. Python recipes should cast via string, not `pd.to_numeric().astype("int64")`.

### Global flag position
`--errors json`, `--profile`, `--dangerous`, `--url`, `--api-key` are root-app options. They must precede the subcommand: `dku --errors json user delete X` works; `dku user delete X --errors json` fails with "No such option". The `AGENT INSTRUCTION` block's `rerun_with_confirmation` preserves the correct position automatically — agents should copy it verbatim.

### Visual recipe `engineType` (top-level)
Every visual recipe payload (Group/Join/Stack/Pivot/Window/Distinct/Sort/Split/TopN/ExtractFailedRows) carries `payload.engineType ∈ {DSS,SQL,SPARK_SQL,IMPALA,HIVE}` as a TOP-LEVEL field — distinct from `engineParams.<engine>.executionEngine` deeper in the payload. Setting only one leaves DSS in an inconsistent state and `engineType` wins. Defaults to DSS when the recipe is created via the SDK; agents on Snowflake/Postgres/Redshift must pass `--engine SQL` to push down. The CLI's `--engine` flag wires this top-level field on every visual `create-*` verb. Fuzzyjoin is forced DSS-only (in-memory operation; setting `engineType: "SQL"` silently falls back).

### Pivot `valueLimit` spelling + `explicitValues` shape
`valueLimit: "EXPLICIT"` (singular, NOT `"EXPLICIT_VALUES"`) — the wrong spelling silently falls back to TOP_N=20, truncating the modality whitelist with no warning. `explicitValues` is an **array of single-element arrays**: `[["2024"], ["2025"]]` — the flat form `["2024", "2025"]` is also silently ignored. CLI: `dku recipe create-pivot --value-limit EXPLICIT --explicit-values 2024 --explicit-values 2025`.

### Window `postFilter` replaces a downstream filter recipe
The classic Lag/Lead "drop boundary rows" pattern is one Window+postFilter recipe, NOT Window followed by a Filter recipe. The `--post-filter 'PartitionFirstRow != 0'` slot runs after window functions; partition-boundary nulls drop in the same pass.

### Window `lagDiff` / `leadDiff` + `--lag-date-unit`
`--compute lagDiff:price:price_lagDiff` computes current minus lag value (delta) in one pass — agents otherwise build Window+Prepare(formula). For date columns, `--lag-date-unit MONTH` writes `dateDiffUnit` on each lag/lead `values[]` entry; default is DAY which silently produces wrong offsets when ordering by month-grain timestamps.

### Pivot carry-through columns + slugification
- `--other-column COL[:AGG[:ORDER_COL]]` writes `payload.otherColumns[]` — extra columns kept through the pivot with an aggregation. `LAST:timestamp` is the canonical "keep latest non-pivot column per group" pattern (typical for sensor / IoT pivots).
- `--modality-slugification {NONE,SOFT_SLUGIFY,HARD_SLUGIFY}` controls output column-name normalisation. NONE preserves spaces/punct in modality strings; SOFT replaces spaces with `_`; HARD strips all non-alphanumeric. Affects every downstream column reference — pick before adding downstream Prepare steps.
- `--no-sort-modalities` disables the alphabetic output-column sort. `--identifier-mode AUTO` makes every input column a row identifier (vs default EXPLICIT which only uses `--row-key` columns).

### Join advanced conditions (date-window, fuzzy, rightLimit)
Regular Join supports far more than EQ — agents fall back to Cross+Filter or Python because the CLI used to hide these. Now exposed via `dku recipe create-join`:
- `--date-window FROM:TO:UNIT` (e.g. `-7:7:DAY`) maps to `windowFrom` / `windowTo` / `dateDiffUnit` on each EQ condition. Replaces SAS `WHERE a.date BETWEEN b.date - 7 AND b.date + 7`.
- `--max-distance N` maps to `maxDistance` on EQ conditions (Levenshtein on a regular Join — no need to switch to fuzzyjoin).
- `--case-insensitive`, `--normalize-text` map to `caseInsensitive` / `normalizeText`.
- `--max-matches N` caps right rows joined per left row.
- `--right-limit-*` flags work on regular EQ joins (not just spatial). `--right-limit-keep KEEP_LARGEST --right-limit-decision-column record_date --right-limit-max-matches 1` is the "for each transaction, keep only the most-recent matching customer record" pattern that previously took 3 recipes (Window + TopN + Join).

### Embed recipe source attribution (`--metadata-col`)
`dku recipe create-embed --metadata-col TITLE --metadata-col URL` carries those columns through to the Knowledge Bank chunks. Without `--metadata-col`, retrieved chunks have no source attribution and RAG citations break — agents won't notice until a user asks "where did this come from?". Maps to `payload.metadataColumns[]`.

### `nlp_llm_rag_embedding` uses `knowledgeColumn`, NOT `embedColumn`
Hand-written `set-definition` payloads with `embedColumn: "text"` silently embed nothing. The right field is `knowledgeColumn`. The `--metadata-col` carry-through column similarly maps to `metadataColumn` (separate from the chunk-text column).

### `evaluation` recipe `appendMode: true` is the default
Every build APPENDS one row to `outputs.metrics`. Recreating the evaluation recipe and rebuilding accumulates duplicate metric rows against the OLD recipe's metric definitions — set `appendMode: false` if you want overwrite-on-each-build semantics, or wipe the metrics dataset between recipe revisions.

### LLM classify needs ≥2 classes
`dku recipe create-llm-classify --class urgent --class routine` is the minimum. With one `--class`, the recipe builds without error but produces empty predictions every run — DSS does not enforce the floor. The CLI does.
