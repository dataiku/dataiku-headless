# Migration workflow

The five-phase migration playbook, in detail. Source-agnostic. Source-specific Phase 1 parsing lives in each `<source>/overview.md`.

---

## Phase 0 — Preflight

```bash
dku whoami                          # must succeed — if not: dku auth login
dku connection list                 # find a writable+managed connection
dku project create PROJ --name "Project"
```

Store the connection name and project key — every subsequent command uses them.

---

## Phase 1 — Extract & inventory

Produce a complete inventory of every source step / tool, its inputs, outputs, and what it does. **No Dataiku planning yet** — just understand the source. For complex sources (>20 tools) surface the inventory for a sanity check before drafting the plan; for small sources roll straight into Phase 2. The single consequential confirmation gate is between Phase 2 (plan) and Phase 3 (build).

Generic inventory template:

```
| # | Source ID | Source Type | What It Does | Inputs | Outputs | Migratable? |
|---|-----------|-------------|--------------|--------|---------|-------------|
| 1 | …         | …           | …            | …      | …       | Yes → …     |
```

For source-specific column meanings (`Source ID` vs `Tool ID` vs `SAS step name`), parsing logic, and inventory examples, read `<source>/overview.md`.

### Deduplicating multi-implementation projects

Real projects often have the same transformation implemented several ways (DATA step *and* PROC SQL; or `Formula` + `Filter` *and* `RunPython`). Identify the canonical production version, migrate that one, and note the alternatives as "skipped (alternative of step N)" in the inventory. Present the choice to the user before proceeding.

---

## Phase 2 — Migration plan

Map each migratable step to a Dataiku recipe. Pick types using `../../dku-cli/playbooks/tabular-flow.md` and `<source>/translation.md` (priority: **Visual → SQL → Python**).

**Apply the collapse triggers as you draft, not after.** The full per-source list lives in `<source>/overview.md` § Collapse triggers. As you map each step, ask:

1. **Consecutive single-row transforms (Formula, Select, TextToColumns, DateTime, Filter)?** → fold into one Prepare recipe with N steps.
2. **Filter immediately upstream/downstream of a Group/Join/Window/Sort?** → fold into the visual recipe's `preFilter` / `postFilter` slot (top-level rule 12).
3. **Computed column immediately upstream of a Group/Join/Window?** → fold into the visual recipe's `computedColumns` slot.
4. **Per-input Prepare adding a literal "source" column before a Stack?** → replace with `dku recipe create-stack --origin-column source` (the entire per-input layer disappears).
5. **Pivot or Unpivot whose only consumer immediately re-aggregates?** → compute the per-group aggregate **inline** in the upstream Prepare (`add-formula` per modality) and remove the reshape entirely. This is also the only reliable workaround for the `create-pivot` modality-scan blocker.
6. **A "do this per Category" loop / batch macro?** → DSS expresses per-key iteration as a CROSS join on the key column. The macro body becomes one Join + (often) one Prepare.
7. **Any recipe whose only consumer is a `BrowseV2` / `Render` / Excel report?** → drop it. UI-only.

Plan shape:

```
| # | Source Step(s) | Recipe | Type | Input | Output | Key Operations |
|---|----------------|--------|------|-------|--------|----------------|
| 1 | …              | Prepare | Visual | … | … | … |
| 2 | …              | Join    | Visual | … | … | … |
| 3 | …              | Group   | Visual | … | … | … |
```

### Sanity check before presenting

Print a one-line ratio at the top of the plan: *"Source: N tools → Plan: M recipes (N/M ≈ X×)."* Expected **3–5×** for typical workflows. If you're at <2×, either re-walk the triggers (you've probably missed fold-ins or per-input Prepare-before-Stack patterns) or state explicitly why this workflow doesn't compress (small input, fully parallel branches, output-only chain). Then get user confirmation before Phase 3.

---

## Phase 3 — Build & verify (incremental, in functional units)

```bash
# 3.1 — Upload source data (first time only)
dku dataset create DS --type UploadedFiles -P PROJ && \
dku dataset upload DS /path/to/file.csv -P PROJ && \
dku dataset set-schema DS -P PROJ -d '[
  {"name":"id","type":"bigint"},
  {"name":"amount","type":"double"},
  {"name":"dt","type":"string"}
]'
# Leave date columns as string (rule 6).

# 3.2 — Create recipe (visual shortcuts auto-create outputs)
dku recipe create-filter filter_active -i DS --output-ds active \
    -f 'status == "A" && amount > 0' -P PROJ

# 3.3 — Validate BEFORE running (catches formula errors early)
# (a) For visual recipes with formula filters / computed cols, check $status.ok
dku recipe get-settings filter_active -P PROJ -o json \
  | jq '.payload | {pre: .preFilter."$status".ok, post: .postFilter."$status".ok}'
# Both should be true. If false, read .message and fix before continuing.
# (b) Then apply-schema
dku recipe apply-schema filter_active -P PROJ

# 3.4 — Run
dku recipe run filter_active -P PROJ --wait

# 3.5 — Verify output
dku dataset info active -P PROJ --recompute
dku dataset schema active -P PROJ
dku dataset head active -P PROJ -n 5
```

Compare row count against the source's expected count (SAS: NOTE in the log `NOTE: Table WORK.X created, with N rows`. Alteryx: cached `BrowseV2` data or a ground-truth CSV. Excel: row count of the source range.). If counts differ, investigate before continuing.

### Cadence: one-liner per recipe, summary per zone

Per recipe, a one-liner is enough: `recipe_name: input → output, N rows OK`. At the end of each functional unit / zone (or every 5–8 recipes for large flows), present a short summary table — recipes built, row counts vs. source, anything skipped. Reserve a richer per-recipe report for the cases where the row count *doesn't* match and you need to walk the user through what you tried. Verbose per-recipe narration on every step is unnecessary in a 30+-recipe flow.

### Independent branches can run concurrently

If two recipes share no upstream dependency (parallel branches in the source DAG), there is no reason to build them sequentially. Configure both, validate `$status.ok` on both, then run them in parallel — verify each terminus as it lands. The "one at a time" anti-pattern this is replacing is *cascading 10+ unverified recipes*, not "ever submitting two builds in the same minute".

### Cross-connection landing

If the source upload lands on a different connection from the rest of the flow (e.g. CSV → Filesystem, but the rest is on Snowflake), insert a single `sync` recipe to land it on the target connection before any further processing. Otherwise rule 2 (one engine per flow) is silently violated.

---

## Phase 4 — Integration test

```bash
dku recipe list -P PROJ
dku dataset list -P PROJ
dku dataset head FINAL_OUTPUT -P PROJ -n 5 -o json
```

Present a migration summary: source step → recipe → output dataset → row count → status. Note anything skipped (non-migratable patterns; alternative implementations).

If a wiki was bootstrapped via `dku project ai-describe --save` in Phase 3, refine it now with the final mapping table and any deviations from parity.

---

## Common Gotchas

Full catalog in `../../dku-cli/playbooks/tabular-flow.md`. Source-specific gotchas (parsing quirks, language traps) in each `<source>/overview.md`.

| Gotcha | Fix |
|---|---|
| Upload auto-detects all columns as STRING | `set-schema` with correct types right after upload |
| `set-schema` with `type: date` on CSV → all null | Keep as `string`; parse with `DateParser` in a Prepare step |
| Sampling recipe with `uiData.expression` filter silently drops the predicate (no error, output row count = input row count) | DSS rewrites `uiData` to `{mode: "CUSTOM", conditions: []}` on save. Use `dku recipe create-filter` (Prepare + `FilterOnCustomFormula`) — that schema isn't mutated |
| Group recipe adds an extra `count` column | Pass `--no-global-count` |
| `dku dataset info` row count is stale after build | Pass `--recompute` |
| `apply-schema` required before first run | Otherwise computed columns silently missing |
| ML setup as a Python recipe in the Flow (PROC LOGISTIC / PROC REG / PROC GLM landed as `dataiku.api_client()` script) | Anti-pattern. Recipes produce data, not status. Use the `dku ml` namespace: `create-prediction → set-algorithm → train → deploy → recipe create-prediction-scoring`. See `sas/ml-scenarios.md`. |
| Window recipe doesn't produce global aggregates per row (`MEAN(col)` over the whole table → still per-row identity) | Use Group(no key) + CROSS Join + Prepare instead. See `sas/procs.md`. |
| `.sas7bdat` numeric IDs export as `1077430.0` (float) — `set-schema id:bigint` silently nulls every value, joins produce 0 rows | Cast to nullable `Int64` in pandas before `to_csv`. See `sas/overview.md` § `.sas7bdat` source tables. |

## Reference Map

### Within this skill

| Reference | When to read |
|---|---|
| `references/workflow.md` | Phase-by-phase mechanics — the source-agnostic Phase 0–4 playbook |
| `sas/overview.md` | SAS-specific entrypoint — file parsing, source-specific rules, non-migratable patterns |
| `sas/translation.md` | SAS translation entrypoint and focused reference map |
| `sas/data-step.md` | DATA step, RETAIN, ARRAY, DO, SELECT/WHEN, and external file I/O |
| `sas/procs.md` | PROC mapping, SQL, transpose, univariate, formats, and stats |
| `sas/functions-formats.md` | Function mapping, GREL/SQL equivalents, rounding, and dates |
| `sas/ml-scenarios.md` | Visual ML, scheduling, checks, reporting, and scenarios |
| `sas/flow-patterns.md` | Enterprise driver scripts, passthrough extracts, fan-in/split, and parity checks |
| `sas/semantics.md` | PDV, MERGE semantics, missing values, macro patterns — read when a value disagrees |
| `ayx/overview.md` | Alteryx-specific entrypoint — file parsing, source-specific rules, non-migratable patterns |
| `ayx/translation.md` | Alteryx translation entrypoint and focused reference map |
| `ayx/tools-core.md` | TextInput, DbFile, Formula, Select, Filter, Sort, Sample, and Unique |
| `ayx/tools-join-reshape.md` | Join, JoinMultiple, AppendFields, Union, Summarize, CrossTab, and Transpose |
| `ayx/tools-state-parsing.md` | MultiRowFormula, RunningTotal, RecordID, TextToColumns, RegEx, and DateTime |
| `ayx/tools-io-apps-ml.md` | Download, FindReplace, spatial, macros, dynamic input, yxdb, email, Excel, apps, and predictive tools |
| `ayx/workflow-patterns.md` | Range joins, reroutes, component-stat chains, correlation, and recurring collapse patterns |
| `ayx/semantics.md` | Alteryx data types, null/join semantics, MultiRowFormula boundary rules |
| `ayx/frictions.md` | DSS-vs-Alteryx onboarding pushbacks (intermediate datasets, previews, layout) |
| `xlsx/overview.md` | Excel-specific entrypoint |

### External skill references (read often)

- **`../../dku-cli/playbooks/tabular-flow.md`** — the tabular-flow playbook: picking a recipe type (Visual → SQL → Python rationale, decision tree, `$status.ok` validation), the visual-recipe pipeline-collapse pattern (4 recipes → 1), filter-mode rule, custom aggregations; Dataiku/CLI traps (upload→STRING, `--recompute`, `apply-schema` required, Sampling-filter trap, GREL push-down quirks); flow zones, recipe naming, wiki, dataset descriptions; and SQL-engine work (cross-connection landing, GREL → SQL push-down, stale-physical-table recovery) — *mandatory* whenever the target connection is SQL.
- **`dku <noun> <verb> --help`** (machine-readable under `DKU_AGENT_HELP=1`) — the authoritative source for every command's exact flags. The skill's quick examples are abbreviated; drill into `--help` rather than guessing.
- **`../../dku-cli/references/prepare-processors.md`** — the index of all Prepare-recipe processors with their JSON shape. You will translate dozens of source steps into Prepare-step JSON; this is the canonical reference. The Golden Rule from the file: prefer a purpose-built processor over `CreateColumnWithGREL`.
- **`../../dku-cli/references/formulas.md`** — GREL function reference. Translating source formulas (`Formula` tools in Alteryx, DATA-step assignments in SAS, Excel formulas) is mostly "find the GREL equivalent of this function". Case-sensitive, has surprises (`toTitlecase` not `toTitleCase`).
- **`../../dku-cli/playbooks/project-ops.md`** — orchestrating multi-step builds. Useful when the migrated flow needs scheduled rebuilds, cross-project quality gates, or composing leaf scenarios. Read after Phase 4 when wiring the flow into automation.
