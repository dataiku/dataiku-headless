# Tabular Flow Playbook

Build and transform datasets in a DSS flow. References for JSON shapes the CLI
flags don't cover: `references/visual-recipe-payloads.md`,
`references/prepare-processors.md` (processor params), `references/formulas.md`
(GREL). For payloads that save clean and pass validation but still fail silently
at build or render time, check `../references/visual-recipe-traps.md` — the trap
catalog for exactly this class of bug.

## Capability ladder (take the first rung that fits)

Visual recipe → SQL recipe → Python recipe (last resort). A flow of visual
recipes is reviewable on the graph; one giant Python recipe is a black box.
"I prefer SQL / it's tidier / the team writes SQL" is **never** a reason.

## The sequence (every flow task)

**inspect → sample → wire → build → verify.** Never skip verify.

```bash
dku --format json project inspect PROJ                 # 1. project shape
dku dataset info IN -P PROJ && \
dku dataset schema IN -P PROJ && \
dku dataset head IN -P PROJ -n 5                  # 2. gauge + sample inputs
# 3. wire recipes (see decision table)
dku recipe create-join enrich -i IN -i LOOKUP --output-ds OUT --join-key id -P PROJ
# 4. build the terminal output, recursive + schema propagation
dku job run --target OUT -P PROJ --type RECURSIVE_BUILD --wait
# 5. verify REAL data
dku dataset head OUT -P PROJ -n 5 && dku dataset info OUT -P PROJ --recompute
```

When a recipe outputs to a managed **folder** (not a dataset), build with
`dku recipe run RECIPE -P PROJ --wait`.

Per SKILL.md rule 5 (verify with real rows): successful `--wait` builds (`job run`, `dataset build`, `recipe run`) print
`Built <ds>: N rows, M cols` per dataset — read it: a `0 rows` warning means
fix the recipe before building anything downstream, and an all-string-schema
hint means run `dku dataset infer-types DS --apply` before aggregating.

**Inspect with an analytical lens** — flag wrong-looking types (numbers stored
as strings, dates as text), identifier/surrogate-key columns (leakage risk for
ML), high null rates, low-cardinality columns correlated with a target, tiny
(<1k rows) or very wide datasets. Use `dku dataset analyze-column DS COL -P PROJ` for
distributions. Communicate findings as insights, not lists.

## Canonical commands (use directly — `--help` only for the rest)

Worked invocations for the high-frequency verbs. Substitute names; reach for
`dku recipe <cmd> --help` only when you need a flag not shown here.

```bash
# Join (repeat -i per input; --join-type LEFT|INNER|RIGHT|FULL|CROSS)
dku recipe create-join NAME -i LEFT -i RIGHT --output-ds OUT --join-key KEY --join-type LEFT -P PROJ
# Group / aggregate (repeat -k for multi-key; --agg col:func, e.g. amount:sum)
dku recipe create-group NAME -i IN --output-ds OUT -k KEY --agg amount:sum --no-global-count -P PROJ
# Pivot long→wide (default output cols are <colvalue>_<value>_<aggfunc>, e.g. Hardware_amount_sum)
dku recipe create-pivot NAME -i IN --output-ds OUT --row-key ROW --column-key COL --value-column amount --agg-type SUM -P PROJ
# Prepare recipe + steps (create-prepare auto-creates the output; generic
# `recipe create -t prepare` does NOT unless you pass -c CONNECTION)
dku recipe create-prepare NAME -i IN --output-ds OUT -P PROJ
# Build ALL steps in one artifact (preferred over N add-* calls). Each entry is an
# `op` (formula/rename/filter-rows/fill-empty/delete-columns/reorder/find-replace/
# fold/geopoint/geodistance) or a raw {"type","params"}. --replace to rebuild.
dku recipe apply-spec NAME @steps.json -P PROJ
# Single-step shortcuts (use when iterating one step, or --at to insert mid-pipeline)
dku recipe add-formula NAME --expr 'EXPR' --column NEWCOL -P PROJ
dku recipe add-rename NAME --from OLD --to NEW -P PROJ        # or --mappings 'OLD:NEW,OLD2:NEW2'
# Propagate schema (after editing steps), build recursively, verify
dku recipe apply-schema NAME -P PROJ
dku job run --target OUT -P PROJ --type RECURSIVE_BUILD --wait
```

Don't rename a column the task didn't ask you to rename — the pivot's default
`<value>_<agg>` suffix is usually the expected output; an extra rename step often
moves you *away* from it.

## Dataset basics

**Upload local files** — use `UploadedFiles`; plain `create` defaults to
Filesystem which does NOT accept uploads:

```bash
dku dataset create raw --type UploadedFiles -P PROJ && \
dku dataset upload raw ./raw.csv -P PROJ --overwrite && \
dku dataset infer-types raw --apply -P PROJ && \
dku dataset head raw -P PROJ -n 5
```

- **Re-uploading: always pass `--overwrite`/`-f`.** Same filename without it
  errors; a *different* filename silently coexists (rows from both files
  surface in `head`), no warning. `--overwrite` trips the tier-2 delete guard
  (exit 77, needs `--yes`) even on a freshly created empty dataset — expected,
  pass `--yes`.
- **Upload auto-detects every column as STRING** — the next sum/avg then fails
  (or worse, silently mis-sorts). Fix in one step right after upload:
  `dku dataset infer-types DS --apply` re-infers bigint/double/boolean from the
  data (conservative: leading-zero identifiers and mixed columns stay string).
  Date-like columns are intentionally KEPT string — casting CSV columns to
  `type: date` via set-schema yields all-null; parse inside a Prepare
  `DateParser` (ISO strings sort/aggregate chronologically anyway). Same trap
  and same fix for Prepare/visual outputs that land all-string.
- **`set-schema` only updates metadata, not the on-disk column ORDER.** If your
  declared order differs from the file's actual order, DSS reads by POSITION →
  silent garbage. Match schema order to file order (use `dku --format json dataset head` to see
  the real order, or a `ColumnReorder` step at the end of the Prepare).
- **Manual Filesystem dataset needs `-c CONNECTION`** (rare; recipe create
  usually does this): `dku dataset create NAME --type Filesystem -c filesystem_managed -P PROJ`.

### Querying & counting by logical name (no physical table)

Use these instead of writing raw SQL against a hand-resolved physical table:

- **`dku dataset count NAME [--where SQL]`** — on SQL-backed datasets resolves the
  physical table and runs `SELECT COUNT(*)` (so `--where` works and the count is
  exact); other types fall back to the COUNT_RECORDS metric.
- **Filtered counts are SQL-backed-only.** `count --where` / `query` need a SQL table;
  on file datasets the CLI errors prescriptively — `create-filter` then `count`, or
  `head` locally and count there.
- **`dku dataset query NAME --sql '... {{table}} ...'`** — runs SQL against a
  SQL-backed dataset's table by logical name; the `{{table}}` token expands to the
  resolved `${projectKey}_<NAME>` table on the right connection. SQL-table-backed
  datasets only.
- **`dku dataset download NAME [OUT]`** — omit the output arg (or pass `-`) to stream
  CSV to stdout; pipe straight into `python`/`jq`.
- **`dku dataset analyze-column NAME COL`** — distribution + top values for one
  column (null rate is numeric-only; for strings read the `""` top value).

**Managed Snowflake physical-table rule.** The physical table is
`${projectKey}_<DATASET>` **UPPER-cased** (`orders_sf` in `GTN_DEMO` →
`GTN_DEMO_ORDERS_SF`), but DSS stores **column names lowercase** — raw SQL must
**quote** them or Snowflake folds unquoted identifiers to upper. SQL recipes likewise
UPPER-case unquoted output aliases (`AS reason` → `REASON`); quote the alias
(`AS "reason"`) to preserve case. Never hand-resolve `${projectKey}` — `dataset
count`/`query` resolve table + connection for you.

## Visual recipe decision — what to use, never Python

| Task | Recipe | NEVER |
|---|---|---|
| Join / merge / enrich | `create-join` (multi-input) | `pd.merge` |
| Aggregate / group-by | `create-group` | `df.groupby` |
| Stack / union / concat | `create-stack` | `pd.concat` |
| List distinct values of one/few columns | `create-distinct --on COLS` (output = just those columns) | `create-group` no-agg, `unique()` |
| Dedup whole rows, ALL columns are key | `create-distinct` | `drop_duplicates` |
| Keep one FULL row per key (subset is key) | `create-window` ROW_NUMBER==1 | `create-distinct` (drops other cols) |
| Sort | `create-sort` | `sort_values` |
| Filter rows | `create-filter` | `df[cond]` |
| Window / rank / lag / running total | `create-window` | `groupby().transform` |
| Top/bottom N (per group) | `create-topn` (`-k group`) | `nlargest`/`groupby().first` |
| Long→wide | `create-pivot` | `pivot_table` |
| Wide→long (unpivot) | Prepare + `add-fold` | `pd.melt` |
| Random sample | `create-sampling` | `df.sample` |
| Row expansion / cartesian | `create-join --join-type CROSS` | nested loops |
| Passthrough / cross-connection move | `create -t sync` (`--connection`) | Python passthrough |
| Spatial join / distance | `create-geojoin` / `add-geodistance` | haversine in Python |
| Fuzzy / approx string match | `create-fuzzy-join` (`--method`: LEVENSHTEIN default; COSINE/JACCARD for token text, HAMMING for codes, EUCLIDEAN for numerics) | custom Levenshtein |
| Per-row transform (rename, cast, parse, derive) | Prepare (`add-*` steps) | — |
| Apply saved model | `create-prediction-scoring` / `create-clustering-scoring` (needs `--model`; see scoring note below) | — |
| None of the above | `create -t sql_query` → then `-t python` | — |

**Join design: multi-input beats cascading.** One `create-join -i A -i B -i C`
with index-prefixed keys (`--join-key k`, `--join-key 1:k`, `--join-key 2:left=right`)
beats A+B→temp→temp+C: one recipe, zero intermediates, no column-name explosion.
Default join type is INNER; if the task says "enrich", use `--join-type LEFT`.
Cascade only when each step needs a different join type, or an intermediate is a
real deliverable. Inequality/range ON conditions are flags-only: `--join-key`
accepts operators (`-k 'a.seq>=b.seq'` style without the prefixes —
`'seq>=start_seq'` → GTE; also `<=`, `>`, `<`, `!=`; left side = first input's
column). No CROSS + `--post-filter` detour or payload surgery needed.

**In-database pipeline (full pushdown in one call).** Every visual `create-*`
(join/group/window/sort/distinct/pivot/stack) accepts `-c`/`--connection` so its
output lands as a managed dataset on a SQL connection — chain them and the whole
pipeline runs in-engine, no pre-created intermediates (`-c` is the column key on
`create-pivot`, so use `--connection` there):

```bash
dku recipe create-group agg -i raw --output-ds grp -k region --agg amount:sum --connection Snowflake-conn -P PROJ
```

**Scoring shortcut.** DSS auto-names scoring recipes `score_<input>` (ignoring the
name you pass); the CLI renames it back so `recipe run <your-name>` works, and the
output schema is auto-applied so the first build succeeds. Symptom if it isn't:
scored output stays at 0 columns and the build dies with `Schema incompatibility
... 0 columns in target`, sometimes surfaced only as a raw `IndexOutOfBoundsException`.
Fix: re-run `apply-schema` on the scoring recipe before rebuilding.

**Rolling / trailing-N windows.** Cause: the DSS engine ignores frame bounds —
see `references/visual-recipe-payloads.md` for the mechanism, and
`references/visual-recipe-traps.md` for the full trap writeup. Frame bounds only
take effect on a SQL engine. Pick a fix by window size:

**Small fixed N (≈≤3): Window `--lag-offsets` + null-aware GREL.** Two recipes, no payload surgery.

1. One Window recipe with lag offsets:
   `create-window mw -i d --output-ds out -k category --order-key seq --lag-offsets 'price:1,2'`
2. One Prepare formula averaging value + lags with `isNonBlank` guards.
   Partition-head rows (fewer than N values) come out right by construction.

**Large or variable N: range self-join + Group.**

1. Self-join the input to itself, giving the anchor side a computed window-end
   and the detail side an aliased value column:
   `create-join self_roll -i seq_ds -i seq_ds --computed-col '0:win_end=month_seq + 11:bigint' --computed-col '1:w_price=price:double' …`
   **Rule: alias the detail column.** A self-join silently drops same-named
   detail columns (anchor side wins) — without the alias, step 3 aggregates
   each anchor's own value instead of the window's.
2. Express the range with inequality join keys — `--join-key` accepts operators:
   `-k 'seq<=seq' -k 'win_end>=seq'` → LTE/GTE conditions (left side = first
   input's column).
3. Group by the anchor key, aggregating the alias: `--agg w_price:sum`.
4. Sanity-check the fan-out: joined rows ≈ Σ min(N, rows remaining per partition).

## Collapse N recipes into 1 — the pipeline stages

Every visual recipe (Group/Window/Join/Distinct/TopN/Sort) runs an internal
pipeline: `preFilter → computedColumns → ACTION → postFilter`. The `create-*`
shortcuts and their `--pre-filter`/`--post-filter`/`--compute` flags configure
these stages. So "filter, compute a column, group, then drop small groups" is
**one** Group recipe — not four recipes and three intermediate datasets. For
stages the flags don't reach (custom aggregations, per-input computed columns),
read→edit→write the payload (see `references/visual-recipe-payloads.md`).

Don't collapse when the intermediate is a deliverable, when a filter defines a
separately-referenced logical dataset, or when stages need different engines.

**Validate before build** — Group/Window/Join/TopN/Distinct carry a `$status`
block on each filter after `set-settings`/`set-definition`. Gate on it:

```bash
dku --format json recipe get-settings R -P PROJ | jq '.payload | {pre: .preFilter."$status".ok, post: .postFilter."$status".ok}'
```

`ok:false` → read `.message` and fix. `fullyTranslated:false` → part of the
formula fell back to the in-memory engine (breaks SQL-only flows; check which
fragment via `$status.sql`, the compiled push-down SQL). Prepare/Stack/Sort/
Pivot have NO `$status` — validate those by building and reading `head`.

`dku recipe lint-formula`/`lint-sql`/`lint-python RECIPE` exit 1 on fatal errors,
so chain them ahead of the build (`lint-formula R && job run …`) to catch bad GREL/
SQL/Python before spending a job slot.

## Prepare recipe

The default first choice for any **row-local** transform (rename, retype,
formula, regex, split, parse, fill, format — 100+ processors). Sequence:

```bash
dku recipe create clean --type prepare -i raw --output-ds cleaned -c filesystem_managed -P PROJ && \
dku recipe apply-spec clean @steps.json -P PROJ && \
dku recipe apply-schema clean -P PROJ && \
dku recipe run clean -P PROJ
# steps.json: [{"op":"formula","column":"total","expr":"price * qty"},
#              {"op":"delete-columns","columns":["scratch"]}]
```

**Prefer `apply-spec` over a chain of `add-*` calls** — one declarative array
(op DSL + raw `{"type","params"}` escape) is one reviewable artifact, builds the
steps in deterministic order, and is validated as a batch before any save (a bad
entry aborts with its index, recipe untouched). Reach for the single `add-*`
shortcuts only when iterating on one step or inserting mid-pipeline with `--at`.

Processor IDs and params: `references/prepare-processors.md`. GREL syntax:
`references/formulas.md`. Add geo columns with `add-geopoint` before any geo op.

**Prepare gotchas:**

- **`apply-schema` is required before the FIRST run** (else computed columns are
  silently missing) **AND again after adding rename/formula/select steps to an
  existing recipe** (the later steps leave the output schema stale until you
  re-`apply-schema` and re-run).
- **Formula columns default to STRING regardless of expression type.** A
  downstream Window `sum:col` then fails `Cannot sum non-numeric column`. Fix:
  after the Prepare runs, retype with `dku dataset set-schema OUT -d "$(dku --format json dataset schema OUT | jq 'map(if .name=="col" then .type="bigint" else . end)' -c)"`.
- **`MultiColumnFold` (`add-fold`) silently DROPS rows where the value is null.**
  Pre-impute with `add-fill-empty` on each folded column BEFORE the fold.
- **Schema does NOT auto-propagate downstream when an input's types change.**
  `apply-schema` reports "no updates needed". Explicitly `set-schema` each
  downstream managed dataset, then re-run the chain.
- **`computedColumns` entries cannot reference each other** — `g(a)` evaluates
    against the input row, not `a`'s value. Inline every reference.
- **Date columns carry a time component.** A Date column surfaces as `2024-01-04 00:00:00`
  unless created via `asDateOnly()`. If the task expects date-only (`2024-01-04`), wrap
  comparison columns: `substring(strval(col), 0, 10)`. A set-schema with `type: date`
  on a CSV column yields all-null — keep string and use DateParser step.

## SQL recipe

Use only after concluding a visual recipe can't express the logic, or to port a
production-quality passthrough `SELECT`. Genuine SQL triggers: window functions
beyond the Window recipe, `PERCENTILE_CONT`, range/theta joins, multi-CTE
pipelines, or a customer mandate to execute entirely in-engine.

- **`sql_query`** (single SELECT): output dataset **must pre-exist**; run
  `apply-schema` before first build (else `INSERT has more expressions than
  target columns`). A build run BEFORE `apply-schema` can also "succeed" with
  **ZERO rows** (`head` returns `[]`) — silent, no error; apply-schema then
  re-run. Reference the output as `"${projectKey}_<dataset>"` — the
  `${DKU_DATASET_..._TABLE_NAME}` form is NOT valid here. Payload is raw text. On
  Snowflake, quote lowercase columns and output aliases (see Managed Snowflake
  physical-table rule under Dataset basics).
- **`sql_script`** (`create-sql-script --sql @f.sql`): multi-statement; on
  Snowflake use SPLIT mode for `CREATE; INSERT; SELECT` chains. Recipe-level
  flags tune the parser — see `--help`.
- **Cross-connection landing:** `create -t sync --connection TARGET` auto-creates
  the managed output on the target connection — never a Python passthrough.

**Force push-down with `--engine SQL`** on Snowflake/Postgres/Redshift; the
top-level `payload.engineType` defaults to DSS otherwise. GREL→SQL push-down
gotchas (use `concat("", col)` not `toString(col)` / `"" + col` for int→string
casts) live in `references/formulas.md`.

## Python recipe — last resort

Only when neither visual nor SQL fits: multi-row state machines, fuzzy/range/IP
hash lookups, arbitrary HTTP IO, whole-text regex-with-state, heavy geospatial.

```bash
dku recipe create score -t python -i feats --output-ds scores -c filesystem_managed -P PROJ && \
dku recipe set-code score -P PROJ --code @score.py
```

- Code recipes need a managed connection — pass `-c`/`--connection` (find via
  `dku connection list`). Folder inputs: `add-input R FOLDER --type MANAGED_FOLDER`.
- **Never `.astype("int64")` on dirty ID columns** (`IntCastingNaNError`):
  `pd.to_numeric(col, errors="coerce")` → `dropna` → cast.
- **Snowflake bigint keys lose precision in pandas (float64, >2^53).** Prefer a
  visual recipe (full precision, native SQL); if Python is unavoidable, cast via
  string. Same engine note: `--agg col:concat` on large text hits Snowflake's
  `LISTAGG` limit (error 300002) — split numerics into a visual Group, merge
  text in a small Python recipe.

## Data quality rules

Validate datasets with built-in rules (`dku dq` is top-level, not `dku dataset dq`):

```bash
dku dq create DS -P PROJ --type not-empty --column customer_id   # or --config @rule.json
dku dq compute DS -P PROJ && dku dq results DS -P PROJ
dku dq project-status -P PROJ                                             # rollup across datasets
```

Rule families: record/file-size-in-range, numeric range (min/max/avg/sum/stddev/
median/count), emptiness, uniqueness, values-in-set/range, top/mode membership,
meaning validity, schema containment, metric comparison. `ERROR` (hard bound)
can fail builds when `autoRun=true`; `WARNING` (soft) reports only. Prefer
built-in types over Python-code rules. Quarantine failing rows with the Extract
Failed Rows recipe (input must have checks defined). Never delete a rule without
user confirmation (`delete --rule-id` needs `-y`).

## Flow organization

Organize as you build, not in cleanup. Pick one zoning convention:

- **By stage** (linear flows): `ingest / prepare / join / aggregate / output`.
- **By functional area** (large/multi-domain migrations): `credit_risk /
  collateral / reporting / shared_lookups`.

Zone verbs live at the flow root: `dku flow create-zone NAME`, `dku flow zones`
(list), `dku flow move` — there is no `flow zones create`. The DEFAULT zone's members are DERIVED
(`itemsDerived=true`, and `flow zones` reports its `items[]` empty) — items live
there implicitly until you move them, so judge "clean flow" by membership, not raw
counts. The default zone can't be deleted and only materializes once another zone
exists, so an all-new-zones layout strands an empty `Default` box on the flow —
make it one of your stages instead: `dku flow move <stage-1 nodes> --zone default`,
then `dku flow set-zone default --name ingest --short-desc '...'`. `flow move -t AUTO`
resolves the item type for you and mixes types in one call. Rename recipes verb-first and descriptive (`join_homeequity_to_us_data`, not
`compute_joined_3`); the recipe names the action, the dataset names the thing. Give every dataset *and*
recipe a hand-written one-liner in the project's working language (`dku dataset set-metadata --short-desc`,
`dku recipe set-description`).

A zone's short description shows on the main flow UI — a paragraph per zone
(`dku flow set-zone ZONE --short-desc '...'`) documents the flow where readers
actually look. Wiki-style object links (`[label](dataset:NAME)`, `recipe:`,
`scenario:`, `dashboard:ID`, `flow_zone:ID`) render as typed, clickable chips
in it. The long `--description` only fills the zone's details panel. Rendering
is gated by the project display setting `showFlowZoneDescriptions`;
`set-zone`/`create-zone` enable it when writing a short description.

Before reporting a project done, hand-write at least one wiki article
(`dku wiki create`) in the project's working language, covering purpose, sources,
flow stages, and a rebuild runbook.

## Flow review — see what the reviewer sees

The flow is the deliverable; audit it the way an SME will read it before calling a
stage — and certainly the project — done:

```bash
dku project audit -P PROJ                                      # the finish gate — read-only verdict
dku flow visualize -P PROJ      # the DAG as an ASCII tree — read your own flow
dku flow zones -P PROJ          # every object zoned? default repurposed, not an empty husk?
dku flow sources -P PROJ        # sources only where expected; strays = orphan scaffolding
dku flow check -P PROJ          # schema + data consistency across the graph
dku dataset schema DS --fields name,type,description -P PROJ   # column docs present?
```

`dku project audit` is the default finish sweep — run it first. Read-only, it rolls the
graph, metadata, wiki/runbook, terminal-output health, and obvious blank/type smells into
one verdict and prints the concrete `dku ...` command to fix what failed. The gate fails
(exit 1) only on `fail`-severity checks; warnings are advisory — always shown, never
blocking. Read the full scored verdict with `dku --format json project audit -P PROJ`.
The manual commands below drill into failures; `--contract @file.json` adds value-parity
checks, and `--bucket` re-runs one area without paying for the full sweep.

Checklist — fix anything that fails with the verbs in "Flow organization":

- **Structure** — `visualize` reads as the story you meant: clear stages, no dangling
  branches, no join you can't explain in one sentence.
- **Zones** — the default zone repurposed into a named stage, not left an empty husk
  or an accidental dump; zone short-descs present so the flow UI reads like chapters.
- **Names** — recipes verb-first; datasets name things, not steps (`orders_by_region`,
  not `joined_2_prepared`).
- **Descriptions** — every dataset has at least a one-liner and key output columns are
  documented; `dataset get-definition` shows what a reader will see.
- **Consistency** — `flow check` clean; pending schema drift resolved (`flow propagate`).

## Job / build recovery

Timeout is NOT failure. `dku --format json job list -P PROJ` to find the job,
`dku job wait JOB_ID`, `dku job log JOB_ID` on failure, then verify outputs.
`job run --wait` and `job wait` exit non-zero on FAILED/ABORTED, so an `&&` chain
stops at a failed build — safe to chain.
Never start an overlapping build on the same path while a prior job may be live.
For linearly dependent recipes, complete create→configure→run→verify for each
before starting the next — don't batch-create then build all at once. Ask before
`RECURSIVE_BUILD` on a flow with Spark/BigQuery/Snowflake connections, and
before LLM-heavy runs (sample 100 rows first to validate output format).

**Build gotchas:**

- **`apply-schema` on a JOIN output can zero out its rows** — the recursive build
  then treats the empty state as up-to-date and downstream stays empty. If a join
  output drops to 0 rows after `apply-schema`, rebuild the join directly
  (`dku recipe run JOIN -P PROJ --wait`) before rebuilding downstream.
- **Containerized recipe (`containerMode: INHERIT`) hangs in RUNNING forever** on a
  full K8s quota — the pod never schedules and later builds fail "incompatible with
  build state". Recovery: `dku job abort JOB -P PROJ`, then set
  `containerMode: NONE` via `dku recipe set-definition` (small data only), or free
  quota and retry.
- **Recipe env/container changes must go through `set-definition`, NOT
  `set-settings`** — engine/env/container knobs live in the DEFINITION, and a
  `set-settings` write of them silently does not persist. Verify with
  `get-definition` after any such write.

## Shell discipline (agents piping `dku`)

- **Never `2>&1` into a `--format json` consumer** — stderr tips merge into
  stdout and break the JSON parse. Data is on stdout, pipe-safe by design;
  leave stderr alone (or send it to a file).
- **Repeatable flags: write them literally or use shell arrays** — zsh does
  not word-split `$VAR`, so `AGG="--agg a:sum --agg b:sum"; dku … $AGG` passes
  ONE token and fails with a confusing `No such option`. Use
  `agg=(--agg a:sum --agg b:sum); dku … "${agg[@]}"`.
- **Don't judge success from `tail -N`** — read the first line or the exit
  code; create/run errors put the verdict first (and restate FAILED last).
- **When step order matters, use `apply-spec` (one ordered artifact)** — not a
  compound of `add-*` calls, where a failed earlier command silently shifts the
  next one's index (wrong order, no error). `apply-spec` validates the whole
  array before saving and writes the steps in array order.

## Debug quick map

| Symptom | First command |
|---|---|
| Build failed | `dku job log JOB_ID -P PROJ` |
| Output columns missing | `dku recipe check-schema RECIPE -P PROJ` |
| Row count stale | `dku dataset info DS -P PROJ --recompute` |
| Wrong column names | `dku dataset schema DS -P PROJ` |
| Flow topology unclear | `dku --format json flow graph -P PROJ` |
| `output dataset does not exist` | pre-create it (`dataset create ... -c CONN`) |
| Recipe run fails | `apply-schema` first, then check connection/schema/formula |

## Done when

- `dku job run --target OUT -P PROJ --type RECURSIVE_BUILD --wait` succeeds and
  prints a non-zero `Built <ds>: N rows, M cols` for every dataset in the chain.
- `dku dataset head OUT -P PROJ -n 5` and `dku dataset info OUT -P PROJ --recompute`
  show real rows and a current row count, not stale metadata.
- Group/Window/Join/TopN/Distinct filters gate clean:
  `dku --format json recipe get-settings R -P PROJ | jq '.payload | {pre: .preFilter."$status".ok, post: .postFilter."$status".ok}'`
  returns `true`/`true`.
- `dku project audit -P PROJ` passes with no `fail`-severity checks.
