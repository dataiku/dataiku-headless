# Playbook: Analytics & Apps

Dashboards + charts + insights, App Designer, and Visual ML / AutoML.
Get exact flags from `dku <group> <cmd> --help`. Pull a reference only for full JSON shapes:
`references/dashboards.md`, `references/app-designer.md`.

## Canonical commands

```bash
# Dashboard + chart insight
dku insight create "Name" --type chart --dataset DS -P PROJ
dku insight set-definition INSIGHT_ID -d @chart.json -P PROJ
dku insight validate INSIGHT_ID -P PROJ
dku dashboard create "Name" -P PROJ
dku dashboard set-definition DASH_ID -d @dashboard.json -P PROJ
dku --format json dashboard get-definition DASH_ID -P PROJ

# App Designer
dku app-designer enable -P PROJ --label "..." --description "..."
dku app-designer add-tile -P PROJ -s 0 --type UPLOAD_DATASET_SET_FILE --dataset DS --behavior INLINE_UPLOAD_REDETECT_AND_INFER
dku app-designer add-tile -P PROJ -s 1 --type SCENARIO_RUN --scenario BUILD
dku app-designer list-tiles -P PROJ

# Visual ML
dku ml create-prediction DS label --type BINARY_CLASSIFICATION -P PROJ
dku ml settings ANALYSIS MLTASK -P PROJ
dku ml set-features ANALYSIS MLTASK --reject col1,col2 --input col3,col4 -P PROJ
dku ml train ANALYSIS MLTASK --wait -P PROJ
dku --format json ml models ANALYSIS MLTASK -P PROJ | jq 'max_by(.rank_score)'
dku ml deploy ANALYSIS MLTASK MODEL_ID -n model_name --train-dataset DS -P PROJ
```

## When to use what

- **Insight + dashboard** — present results to humans (charts, KPI tiles, tables).
- **App Designer** — turn a project into a self-service tool: upload → configure → run → download, no flow knowledge needed.
- **Visual ML / AutoML** — classification / regression / clustering. Prefer over hand-written Python models.

---

## Dashboards, charts, insights

Three steps: **(1)** create a chart insight bound to a dataset → **(2)** configure its `def` via `set-definition` → **(3)** create a dashboard and place tiles referencing the insight.

```bash
dku insight create "Monthly Revenue" --type chart --dataset sales_monthly -P KEY  # capture INSIGHT_ID
dku insight set-definition INSIGHT_ID -d @chart.json -P KEY
dku insight validate INSIGHT_ID -P KEY               # checks column refs — DO NOT SKIP
dku dashboard create "Revenue" -P KEY                 # capture DASH_ID
dku dashboard set-definition DASH_ID -d @dashboard.json -P KEY
```

### Chart insight payload (essentials)

`params.engineType` must be `"LINO"`. `params.datasetSmartName` is the bound dataset (required). `params.def` holds the chart:
- `type` — e.g. `lines`, `multi_columns_lines` (bars), `stacked_bars`/`stacked_columns`, `grouped_columns`, `pie`, `scatter`, `pivot_table`, `kpi`, `gauge`, `geom_map`. (`kpi` = single number, no dimensions.)
- `genericDimension0` = x-axis/category dims, `genericDimension1` = color/series breakdown, `genericMeasures` = y-axis values.
- Dimension object: `{column, type: ALPHANUM|NUMERICAL|DATE, isA:"dimension", sort, ...}`; DATE dims add `dateParams.mode` (`YEAR|QUARTER|MONTH|WEEK|DAY|HOUR`).
- Measure object: `{column, function: SUM|AVG|COUNT|MIN|MAX|COUNTD, type:"NUMERICAL", isA:"measure", displayAxis:"axis1"|"axis2", displayType:"column"|"line"|"area"}`.

Full field list and the empty-array scaffolding: `references/dashboards.md`.

### Dashboard payload (essentials)

Dashboard → `pages[]` → each page has a `grid` → `grid.tiles[]`.
- **Tiles live at `pages[i].grid.tiles`, NOT `pages[i].tiles`** (silent: dashboard loads but tiles vanish).
- Tile types: `INSIGHT` (set `insightId` + `insightType`), `TEXT`, `GROUP` (recursive container — nested tile `box` is RELATIVE to the group).
- `box` = `{top, left, width, height}` on a **36-column grid**.
- `insightType` ∈ `chart`, `dataset_table`, `metrics`, `scenario_run_button`, `filters`, `web_app`, etc.

Full tile/field reference: `references/dashboards.md`.

### Gotchas — with fix

- **Wrong column names render a blank chart with NO server error.** Verify columns first: `dku dataset schema DS -P KEY`, then `dku insight validate INSIGHT_ID -P KEY`.
- **Missing `engineType:"LINO"` or `params.datasetSmartName`** → empty/failed chart. Always include both (`--dataset` on create sets the latter).
- **DSS normalizes payloads on save — fields silently dropped.** After every `set-definition`, re-read and diff:
  ```bash
  dku dashboard set-definition DASH_ID -d @dashboard.json -P KEY && \
    dku --format json dashboard get-definition DASH_ID -P KEY > after.json && \
    diff <(jq -S . dashboard.json) <(jq -S . after.json) || true
  ```
- **`TEXT` tile `htmlContent` is often stripped.** Use the markdown form (`tileParams.text` + `displayedText`, both set to the same value) which persists; or use a chart insight with a large title instead of a scripted header.
- **Do NOT hand-write a `dataset_table` payload.** Its `shakerScript.columnOrder` can expect objects not strings (`Expected BEGIN_OBJECT but was STRING`). Clone-then-narrow: create with `--dataset`, `get-definition` the live default, edit only `columnsSelection` / `sorting` / `previewMode`, write back.
- **Filter page "missing" dataset** — check `pages[i].filtersParams.datasetSmartName`, not only the filter insight definition.

---

## App Designer

Turns a project into a self-service app: a homepage of **tiles** grouped in **sections**.

```bash
dku app-designer enable -P KEY --label "My App" --description "..."   # --mode setup (default) vs template
dku app-designer set-section -P KEY -s 0 --title "Step 1) Upload" --text "Upload your CSV."
dku app-designer add-tile -P KEY -s 0 --type UPLOAD_DATASET_SET_FILE --dataset raw_input \
  --behavior INLINE_UPLOAD_REDETECT_AND_INFER --prompt "Upload Data"
dku app-designer add-tile -P KEY -s 1 --type SCENARIO_RUN --scenario BUILD --button-text "Build" --prompt "Run"
dku app-designer add-tile -P KEY -s 1 --type DASHBOARD_LINK --dashboard DASH_ID --prompt "View Results"
dku app-designer add-tile -P KEY -s 1 --type DOWNLOAD_DATASET --dataset output --prompt "Download"
dku app-designer add-tile -P KEY -s 1 --definition @tile.json   # complex tiles via JSON
dku app-designer list-tiles -P KEY                               # verify
```

Manifest shape (`set-definition -d @manifest.json` for full replace): `useAppHomepage:true`, `label`, `homepageSections[]` each with `sectionTitle`/`sectionText`/`visibilityCondition`/`tiles[]`. Tiles always need `type` + `prompt`. Common tile types: `UPLOAD_DATASET_SET_FILE`, `PROJECT_VARIABLES_EDIT` (form via `params[]`, prefer `behavior:INLINE_AUTO_SAVE`), `SCENARIO_RUN`, `PERFORM_SCHEMA_PROPAGATION`, `DOWNLOAD_DATASET`, `DASHBOARD_LINK`, `TEXT_DISPLAY`/`VARIABLE_DISPLAY`. Full tile + parameter catalog: `references/app-designer.md`.

Design: number sections as linear steps (upload → configure → run → results), bind every dataset/folder tile to a specific resource, give every tile a `prompt` and `help`, hide infra tabs via `instanceFeatures`.

### Gotchas — with fix

- **`--mode` matters.** `setup` (default) keeps the project `REGULAR` with `useAppHomepage` (Project Setup page). `template` flips it to `APP_TEMPLATE` (instantiable Dataiku App). Picking the wrong mode turns a reference project into an App or vice versa; reverting `template`→`setup` has no CLI verb (manual `projectAppType='REGULAR'` save).
- **GET/PUT asymmetry on REGULAR projects.** Reading the manifest via API raises "neither app template nor app instance", but **`PUT` accepts writes** — a probe `PUT {}` silently wipes `homepageSections` (200 OK). The CLI `get` falls back to the export ZIP and `set-definition` gates section-wipes behind CASCADE. Verify section count: `dku --format json app-designer get -P KEY | jq '.homepageSections | length'`.
- **`datasetName` required on every dataset tile** — without it DSS opens a blank "New dataset" page instead of erroring.
- **Folder tiles fail in instances** unless the folder is in `projectExportManifest.includedManagedFolders`.
- Create/test instances with `dku app create-instance PROJECT_KEY --key INST1 --name "..."`; test `INLINE_PYTHON_RUN` tiles in an **instance**, not the template (frontend scope bug).

---

## Visual ML / AutoML

Lifecycle: **create ML task → audit features → train → pick best model → deploy to flow → score a dataset.**
`create-*` returns the `ANALYSIS_ID` + `MLTASK_ID` that every later verb needs; `train` produces `MODEL_ID`s (one per algorithm). Carry all three through `deploy`.

```bash
dku ml create-prediction training_ds label --type BINARY_CLASSIFICATION -P KEY   # → ANALYSIS, MLTASK
dku ml settings ANALYSIS MLTASK -P KEY                                 # AUDIT for leakage — do not skip
dku ml set-features ANALYSIS MLTASK --reject leaky_col,order_id --input quantity,price -P KEY
dku ml train ANALYSIS MLTASK --wait -P KEY                             # trains every enabled algorithm
dku --format json ml models ANALYSIS MLTASK -P KEY | jq 'max_by(.rank_score)' # → best MODEL_ID
dku ml deploy ANALYSIS MLTASK MODEL_ID -n sm_label --train-dataset training_ds -P KEY  # → SAVED_MODEL
dku ml details ANALYSIS MLTASK MODEL_ID -P KEY                         # AUC / accuracy / RMSE of that model
```

Other task types — same flow, different `create-*`:

```bash
dku ml create-clustering customers --guess-policy KMEANS -P KEY        # ANOMALY_DETECTION → Isolation Forest
dku ml create-timeseries sales revenue order_date -i store_id -P KEY   # time col must be Date type; -i per series
```

Retrain into the existing flow model (keeps downstream recipes wired):

```bash
dku ml train ANALYSIS MLTASK --wait -P KEY                             # new session → new MODEL_ID
dku ml redeploy ANALYSIS MLTASK MODEL_ID --saved-model-id SAVED_MODEL --activate -P KEY
```

Score new data with a prediction/clustering recipe (the saved model is auto-wired as a `model` input):

```bash
dku recipe create score --type prediction_scoring -i new_data --output-ds scored \
  --model SAVED_MODEL -P KEY
dku job run --target scored --auto-update-schema --wait -P KEY
dku dataset head scored -P KEY                          # verify prediction columns exist
```

Scoring-recipe naming reconcile rationale (DSS auto-names `score_<input>`): see `tabular-flow.md` → "Apply saved model".

### Gotchas — with fix

- **Auto-guess does NOT detect label leakage.** After `create-prediction` always audit `dku ml settings` and reject post-event columns, IDs, and any column derived from the target — before training, not after.
- **Use `set-features` (one transactional write), NOT a `set-feature` loop.** Each `set-feature` is a full get→modify→save; firing several back-to-back races and silently drops some rejects, so you train on columns you meant to drop. `set-features` reads once, applies all roles, saves once, and aborts on a typo'd feature name.
- **Pick the best model by `rank_score`, not the raw metric.** `dku --format json ml models | jq 'max_by(.rank_score)'` — `rank_score` normalizes higher-is-better (AUC) and lower-is-better (RMSE, logLoss) metrics so `max_by` is always correct.
- **`deploy` REQUIRES `--train-dataset`** (DSS re-fits on the full set). Pass `--no-redo-optimization` when the best model is already DONE and full hyperparameter optimization fails on a small dataset.
- **`redeploy` updates an existing flow model** — target it with `--saved-model-id` OR `--recipe-name`. `--activate` is the default (downstream recipes pick up the new version); pass `--no-activate` to stage it while the previous version stays live.
- **`prediction_scoring` / `clustering_scoring` recipes REQUIRE `--model`** (saved-model ID or name) — omitting it errors before the server call.
- Scoring uses the model's **active version**. After retraining, `dku model set-active-version` to point downstream recipes/endpoints at the new one.
- Compare candidates with `dku model-comparison` before promoting.
