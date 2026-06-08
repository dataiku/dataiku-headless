# Alteryx IO, Apps, Spatial, and Predictive Tools to Dataiku

Translation details for IO tools, apps, macros, spatial workflows, correlation, and predictive tool macros.

## Download

**Alteryx:** issues HTTP(S) requests per row; emits a response column.

**Dataiku:** Python recipe. No visual recipe for HTTP. Use `requests`.

```python
import pandas as pd, requests
df = dataiku.Dataset("in").get_dataframe()
df["response"] = df["url"].apply(lambda u: requests.get(u, timeout=30).text)
dataiku.Dataset("out").write_with_schema(df)
```

**Caveats:** for high-volume, throttle with `time.sleep` or parallelize with `concurrent.futures.ThreadPoolExecutor`. Long-running recipes should live in a scenario with retry.

---

## FindReplace

**Alteryx:** look up values in a second input of (find, replace) pairs and substitute — with options for whole-word match, append mode, and case sensitivity.

**Dataiku:**
- **Read replacements from a dataset** (the direct equivalent): Prepare recipe, Find and Replace processor, **Advanced: Read replacements from a dataset**. Point at an editable (or any) dataset with a "find" column and a "replace" column. No Join / Python needed. This is the preferred path.
- **Whole-word replacement inside a text** (not the Alteryx FindReplace normal mode) → Python recipe with regex boundary.
- **Exact match with join semantics** → Join (left) on `value = find` + Prepare `CreateColumnWithGREL: if(isnull(replace), value, replace)` + drop helper. Only use when the remap table is large or pushed-down SQL is critical.

---

## Spatial tools

Dataiku has more visual geospatial capability than is obvious — try the visual path before reaching for Python.

| Alteryx tool | Dataiku answer |
|---|---|
| `CreatePoints` (lat/lon → point) | Prepare `Create GeoPoint from lat/lon` processor. Inverse: `Extract lat/lon from GeoPoint`. |
| `Distance` (point-to-point) | Prepare `Compute distance between two points` (Haversine). Driving/walking/cycling distance → **GeoRouter plugin** (isochrones, routing) |
| `FindNearest` (kNN between two sets) | **GeoJoin recipe** with `within distance`, then Prepare compute-distance to pick closest. Supports contains, within-distance, beyond-distance, intersects, touches, disjoint, equality. **`--max-matches` caps but does NOT sort by proximity** — to replicate Alteryx's "1 nearest" semantics, GeoJoin all candidates within a generous radius, add `geoDistance` in a Prepare, then a Window (partition by left key, order by distance ASC, `rowNumber`) with postFilter `rn==1`. SQL haversine alternative below. |
| `FindNearest` — SQL alternative when inputs aren't on a geo-capable visual path | When inputs are file-backed and adding 2× `add-geopoint` Prepares + GeoJoin + Window-pick-min feels heavier than warranted, sync the inputs to a SQL connection (DuckDB, PostgreSQL, Snowflake — all have native `radians`/`sin`/`cos`/`asin`) and write a single `sql_query` recipe with haversine in a CTE: `2 * 3958.8 * asin(sqrt(pow(sin(radians(lat2-lat1)/2), 2) + cos(radians(lat1))*cos(radians(lat2))*pow(sin(radians(lon2-lon1)/2), 2)))`. CROSS JOIN the two sides + `ROW_NUMBER() OVER (PARTITION BY left_key ORDER BY dist ASC) = 1` picks the nearest. Expect 3 syncs + 1 SQL recipe (4 total) — competitive with the 5-recipe visual GeoJoin path. Same ~0.06% spheroid offset as `geoDistance`. |
| `Buffer` (expand/contract by value) | Prepare `Create area around geopoint` processor, or `geoBuffer` GREL formula. GeoRouter for routing-aware (isochrone) buffers |
| `Generalize` / `Smooth` (fewer vertices) | `geoSimplify` GREL formula |
| `SpatialInfo` (area, length, centroid, bbox) | `geoEnvelope` formula for bbox; Prepare geo-extract processor for area, centroid, length |
| `Spatial Match` (contains/intersects/touches) | `geoWithin` / `geoContains` GREL formulas for the simple case; GeoJoin recipe for full relation set (one recipe per relation) |
| `Heat Map` / `Binned Geo` | DSS Charts native (density and binned geo map types) |
| `PolyBuild` (point sequence → polygon/line) | **For the geometry itself** — Python (`shapely.geometry.Polygon` / `LineString`) — no visual path for ordering points into a single LineString WKT (Group `concat` does not preserve order). **For the typical downstream metric (`SpatialInfo.LengthMi` total trip distance)** — visual path: Prepare to build `point_wkt = "POINT(" + lon + " " + lat + ")"` → Window `lag(point_wkt)` partitioned by group, ordered by sequence column → Prepare `geoDistance(point_wkt, point_wkt_lag, "MILES")` (filter out first row per group where lag is empty) → Group `sum(leg_miles)`. See § PolyBuild + SpatialInfo below |
| `Spatial process` (polygon editing: union/intersection/…) | Python (`shapely` boolean ops) |
| `Trade area` | **GeoRouter plugin** (isochrones with transportation mode) |
| `MapInput` (user draws shape) | User-provided WKT/GeoJSON dataset; no UI drawing replacement |
| `Make Grid` | Python (shapely) — no direct visual equivalent |

Rule of thumb: if the flow has only 1–2 genuine-Python spatial tools (PolyBuild, Spatial Process, MakeGrid), collapse the spatial segment into a single Python recipe using `shapely` / `geopandas`. Everything else has a visual path via Prepare processors, GREL formulas, or GeoJoin.

### PolyBuild + SpatialInfo (sequence → length)

The `PolyBuild(SequencePolyline) → SpatialInfo(LengthMi)` pair is the most common Alteryx spatial pattern (compute total trip / route length per group). DSS resolves this WITHOUT building the LineString geometry, since `geoDistance(pt_wkt, pt_wkt, "MILES")` plus a per-leg sum gives the same total. 5 visual recipes, all push down to the SQL/local engine the input lives on:

1. **Prepare on cities** — extract `lon`/`lat` from the source coordinates (regex-extract if the source is JSON-like text — DSS will strip embedded `"` from CSV uploads, so use `match(Centroid, /.*\[\s*(-?\d+\.\d+),\s*(-?\d+\.\d+)\s*\].*/)[0|1]` against the de-quoted text), then build `point_wkt = "POINT(" + lon + " " + lat + ")"`. **Use WKT, not GeoJSON** — `geoDistance` accepts WKT `POINT(lon lat)` strings reliably; GeoJSON Point strings (`{"type":"Point","coordinates":[lon,lat]}`) returned empty in our test, with no warning. The column does not need to be re-typed to `geopoint` — string is fine for `geoDistance`'s input.
2. **Window** partitioned by `REP` (or your group key), ordered by the sequence column, `--compute lag:point_wkt:point_wkt_lag`. **Watch out:** the third segment of `--compute` (custom output name) is silently ignored by Window — output column is always `{column}_lag`.
3. **Prepare on the windowed dataset** — `add-filter-rows --action KEEP_ROW --formula 'length(strval("point_wkt_lag")) > 0'` (drops the first row per group, which has no predecessor) + **`add-geodistance --from point_wkt --to point_wkt_lag --output-column leg_miles --unit MILES`** (Prepare's `GeoDistanceProcessor`, NOT GREL `geoDistance()` — see the precision warning below).
4. **Group by REP** with `--agg leg_miles:sum --no-global-count`. Output is `leg_miles_sum` (total trip distance per rep).
5. **Sort** descending on `leg_miles_sum` (`--sort-col leg_miles_sum:desc`).

**GREL `geoDistance()` rounds to 2 decimals; `add-geodistance` Prepare processor is full-precision — and they use DIFFERENT spheroid math.** Tested on Challenge_032 (5-point trip, hotel + 4 surf sites in San Diego County):
| Method | Per-leg result | Sum (4 legs) | vs Alteryx 81.6396 |
|---|---|---|---|
| GREL `geoDistance(p1, p2, "MILES")` | 36.45, 3.55, 12.67, 29.02 (rounded to 2 decimals) | 81.69 | +0.06% (HIGHER) |
| Prepare `add-geodistance --unit MILES` | 36.375807100548414, 3.5480203538343713, 12.643350855533372, 28.94970912502732 (full precision) | 81.5169 | -0.15% (LOWER) |

**Always use `add-geodistance`** for trip-distance / route-length workflows where per-leg differences accumulate — full precision matters and the Prepare processor's spheroid model is closer to Alteryx than the GREL function (drift is smaller in absolute terms despite the opposite sign). Use GREL `geoDistance()` only for ad-hoc / per-row distance comparisons where 2-decimal precision is fine. **Both DSS implementations differ from Alteryx — Alteryx and DSS use different Earth ellipsoid parameters and there is no choice of Earth-radius constant that makes them match exactly.** SQL haversine (`R = 3958.8 mi`) drifts in the same direction as one of the DSS methods. Document the offset in the validation summary and treat as a "matches" result — do not chase the difference.

---

## PearsonCorrelation

**Alteryx:** emits a correlation matrix across numeric columns.

```xml
<Configuration>
  <Fields>
    <Field name="Hitter Rank" />
    <Field name="2015 Team Rank" />
    <Field name="Year" selected="False" />
    …
  </Fields>
  <Covariance value="False" />
</Configuration>
```

**Dataiku — preferred (visual-first, headless-safe):** Sync the input to a SQL connection, then SQL recipe with `CORR()`:

```bash
dku recipe create-sync sync_to_db -P PROJ -i input --output-ds input_db -c <sql_connection>
dku recipe run sync_to_db -P PROJ --wait

dku recipe create-sql pearson -P PROJ -i input_db --output-ds pearson_result \
    --connection <sql_connection> \
    --sql 'SELECT CORR(COALESCE("col_a", 0), COALESCE("col_b", 0)) AS "Result" FROM ${projectKey}_input_db'
dku recipe apply-schema pearson -P PROJ
dku recipe run pearson -P PROJ --wait
```

`CORR()` is in every standard SQL engine (Postgres, Snowflake, DuckDB, Redshift, BigQuery, Oracle). The Sync + SQL pair is two recipes, fully visual to the flow graph, no Python.

**Critical: `COALESCE(col, 0)` for null-handling parity.** Alteryx's PearsonCorrelation tool **treats null values as 0** when computing correlation — it does NOT use pairwise complete cases (the statistical convention used by SQL `CORR()`, pandas `df.corr()`, and numpy). Tested on Challenge_030 (fantasy-baseball draft, 253 rows where 104 had null `Hitter Rank`): pairwise-complete `CORR("Hitter Rank", "2015 Team Rank")` returned `-0.0337`; expected was `-0.0181`; wrapping in `COALESCE("Hitter Rank", 0)` reproduced the expected value exactly. **Always wrap nullable columns in `COALESCE(col, 0)` for Alteryx parity** — the value can differ by a factor of 2 or more on datasets with sparse null patterns. See `ayx/semantics.md` § Aggregation null-handling.

For multi-column correlation matrix, emit one row per column-pair via UNION ALL or a Python recipe (DSS `Statistics` cards in the UI are not headless / scenario-runnable). For interactive exploration, a Statistics card in the dataset UI is fine.

---

## Macros

Alteryx macros consolidate a group of tools into a reusable unit. Three flavors:

### Standard Macro

A sub-workflow with Input/Output tools, used to avoid repeating the same tool sequence at multiple call sites.

**Dataiku answer:**
- **App-as-recipe** is the closest equivalent — a project where specific datasets and variables are exposed as a "recipe" the user can drop into other flows. High adoption bar for low-code users; budget time for the first one.
- **Dataiku plugin recipes** (custom Python recipes packaged in a plugin) — higher investment, stronger UX than App-as-recipe for frequent reuse.
- **Inline duplication** — for macros called only 2–3 times, just inline the logic at every call site. The Flow becomes self-documenting.

### Batch Macro

A sub-workflow applied to each row (or each group) of a control dataset — the rest of the workflow stacks all outputs.

**Dataiku answer:**
- **If the batches are data-driven splits of one dataset** (same schema) → **partition the dataset**. Partitions with identical recipes applied in parallel. Requires designing the partition dimension up front.
- **If the batches are "apply process with different parameters per batch"** → **scenario-loop plugin** (`dss-plugin-scenario-loop`). Loop over a control dataset or a parameter list; each iteration runs a scenario step with substituted variables.
- **If the batches are "process many files with varying schema"** → native multi-file import (managed folder + regex + `Use as dataset`), or **Excel Sheet importer** plugin (one dataset per sheet), then Stack.

### Iterative Macro

Loop until a condition is met (N iterations or state-based). Classic uses: allocation problems (inventory, trade area assignment), transitive closure (hierarchy traversal, graph reachability), fixed-point computations.

**Dataiku answer — pick by shape:**
- **Hierarchy / transitive closure / graph reachability** (the most common iterative-macro pattern in real Alteryx flows — "walk up a parent chain", "find all descendants", "fan a tree out into ancestor pairs") → **one SQL recipe with a recursive CTE** on any SQL connection (PostgreSQL, Snowflake, DuckDB, etc.). `WITH RECURSIVE chain AS (base SELECT … UNION ALL recursive SELECT … FROM chain JOIN base ON …) SELECT …`. If the input dataset is on a filesystem connection, prepend ONE `dku recipe create-sync -i input --output-ds input_db -c <sql_conn>` so the SQL recipe has a SQL-backed input. Total: sync + sql = 2 recipes, regardless of hierarchy depth. **Visual alternative** for bounded depth (≤ 5 levels): N chained `create-join` recipes (each hop is one self-join), then `create-stack` of N projections to the long form. Recipe count grows linearly with depth.
- **Allocation problems** (inventory rebalancing, trade-area assignment) — these genuinely need an explicit termination test on aggregate state. **Scenario-loop plugin** (`dss-plugin-scenario-loop`) with a custom condition — cleanest visual-ish path.
- **Anything else state-based** that doesn't decompose into a fixed-point JOIN — **Python recipe with explicit loop**, last resort.

The "no code-free equivalent" disclaimer applies only to the allocation/state-based shape — transitive-closure macros DO have a clean visual-ish equivalent (SQL recursive CTE).

**Caveat:** macros often come bundled with Dynamic Input / Dynamic Rename tools. Migrate the whole cluster at once — the individual tools outside the macro context don't make sense.

---

## Dynamic Input

**Alteryx:** read from a database/file at runtime; row-driven or parameter-driven file/sheet/query selection.

**Dataiku:**

- **Parametric SQL / parametric export run N times** → **Dynamic Recipe Repeat** (native). Open the recipe's Advanced tab → "Dynamic recipe repeat" section → Enable → pick a parameters dataset. The recipe runs once per parameters row, expanding `${col}` variables from the current row into the query/body. For each column in the parameters dataset, a variable is created automatically; map columns to specific variable names to avoid shadowing.
  ```
  Parameters dataset:
    Col1    Col2
    Jan     2024
    Feb     2024
    ...
  SQL recipe body: SELECT * FROM sales WHERE month = '${Col1}' AND year = ${Col2}
  ```

- **"Pick the latest file in a folder by modification time"** → **Dynamic Dataset Repeat** (native). Chain:
  1. **List Contents recipe** on the managed folder → dataset with `path` + `last_modified` columns.
  2. **TopN recipe** sort `last_modified` desc, limit 1 → single-row dataset with the latest `path`.
  3. Create a dataset on the managed folder, enable **"Dynamic dataset repeat"** in Advanced, pick the TopN output as parameters, set **"Files to include"** to `${path}`. The dataset resolves at build time to the most recent file.

- **Read many files from one folder** (all at once) → managed folder + dataset with include-regex filter (`tab1_.*\.csv`). `dku dataset create --type FilesInFolder`.

- **Read all sheets of an Excel file** → native multi-sheet Excel reader (recent DSS), or Excel Sheet importer plugin (generates one dataset per sheet). Stack afterward.

- **Parametric SQL when Dynamic Recipe Repeat doesn't fit** (e.g. batching to overcome query-length limits) → Python recipe issuing queries via `dataiku.core.sql`, or pre-process the parameters dataset to batch rows (e.g. 10 at a time) and feed the batched form to Dynamic Recipe Repeat.

---

## YXDB files (native Alteryx binary format)

DSS reads `.yxdb` natively — no plugin, no Python conversion. Drop the file into a managed folder and create a dataset pointing at it; DSS parses the schema.

**Caveat:** `.yxdb` Date / DateTime fields have no timezone metadata. By default DSS reads them as **strings**. To read them as dates, set a timezone in the dataset's format configuration. Prefer parsing in a Prepare recipe downstream if the timezone is ambiguous.

**When to use:** if the user has only `.yxdb` outputs of an Alteryx workflow and no upstream access, migrate by consuming the `.yxdb` as a dataset and rebuilding the downstream logic. Often simpler than replicating the full upstream pipeline.

---

## Email output

Alteryx `Email` tool → **Send email** plugin recipe. The plugin iterates rows of an input contacts dataset, sending one email per row. Features:

- Mail channels configured at the instance level (no per-recipe SMTP config).
- Dynamic Recipient / Subject / Body pulled from input columns, with static fallbacks.
- Dataset attachments as CSV or Excel, or embedded inline as HTML table.
- **Conditional formatting** is preserved on Excel attachments and inline-HTML bodies.
- Full JINJA templating for the body.

For a simple "send a build-complete email to one recipient", skip the plugin and use a scenario `Send message` step. For per-row dynamic emails with attachments, use the plugin.

**Conditional formatting trick for inline HTML bodies:**
1. Configure conditional formatting on the dataset in Explore tab (column color rules, row rules).
2. In the scenario's Send Message step: Source = Inline, Send as HTML checked, attach the dataset as Excel with "Apply conditional formatting" and "embed as HTML variable" → reference as `${datasetHtml}` in the body.

---

## Excel Templater

Alteryx's "write to Excel template" pattern → **Excel Templater** plugin recipe.

- Input: the datasets to populate + a managed folder with the `.xlsx` template.
- The template has tagged cells (default tag: `DATASET.tablename`) — the plugin finds each tag and writes the matching dataset starting at the tag's position.
- Only dataset contents are written, not headers — the template controls headers.
- Output: the populated `.xlsx` in the output managed folder.

---

## Dynamic Filename

Alteryx often pairs Output with a dynamic filename pattern (e.g. `report_20240415.csv`). DSS answer: a scenario with two steps:

1. **Custom Python** step sets a project variable, for example `dynamic_filename_csv = f"report_{datetime.utcnow():%Y%m%d}.csv"`.
2. **Run the Export-to-Folder recipe** with output filename set to `${dynamic_filename_csv}`.

If the scenario also emails the file, attach `${dynamic_filename_csv}` from the managed folder in a Send Message step.

---

## Analytic Apps

Alteryx `Analytic App` (desktop interactive UI) → **Project variables** + **Dataiku Applications**.

- **Project variables** are referenced in visual/code recipes as `${var_name}`. Set on the project (not per-recipe) and updated via the UI or scenarios.
- **Applications** expose a visual form on top of a project — user fills in values, these populate project variables, then runs a scenario. The user never sees the Flow.
- **App-as-recipe** (see Macros above) packages a whole project as a callable recipe in other flows.

For Alteryx apps with heavy custom UI, expect HTML/JS customization in the Application layer. Non-trivial lift.

---

## Excel input / output

### Input

Alteryx excels here (pun intended). DSS options:
- **Multi-sheet file** → native DSS Excel import (recent versions), or **Excel Sheet importer** plugin.
- **Files behind cloud storage** → **SharePoint Online**, **OneDrive**, **Google Drive**, **Google Sheets**, **Dropbox**, **Box** plugins. Get the source off local drives first; nothing else works reliably for shared, repeating workflows.
- **Sheet name as dataset column** → native DSS, or Google Sheets plugin.
- **Named ranges** → no direct support. Export to CSV on the Excel side, or Python recipe with `openpyxl`.

### Output

Also Alteryx-strong. DSS options:
- **Excel export with conditional formatting** → DSS Explore conditional formatting is preserved when exporting to Excel.
- **Many datasets into one multi-sheet file** → **Multisheet Excel export** plugin.
- **Template-based Excel output (write to ranges)** → private plugin; contact internal TAM.
- **Dynamic per-partition Excel files / emails** → private plugin; else scenario with Python step.

Challenge the requirement first: is the Excel file the actual deliverable, or is it a dashboard/email/workspace that got implemented as Excel because Alteryx made it easy?

---

## Predictive Tools (R-based macros)

Alteryx ships `Predictive Tools\\*.yxmc` macros that wrap R packages (`forecast`, `nnet`, `glmnet`, etc.). They appear in `.yxmd` as `<Node>` elements with `<EngineSettings Macro="Predictive Tools\\<Name>.yxmc" />` and an empty `<GuiSettings Plugin>` (the Plugin is the macro file path, not a built-in plugin name) — so XML parsing returns an empty plugin name. Always check `EngineSettings/@Macro` when you see an empty `Plugin` attribute.

### ARIMA + TS_Forecast (time-series forecasting)

**Alteryx:** `ARIMA.yxmc` (model fit) → `TS_Forecast.yxmc` (forecast + confidence intervals). Two macros, output schema: `Period, Sub_Period, forecast, forecast_high_95, forecast_high_80, forecast_low_80, forecast_low_95`.

The Configuration `<Value>` parameters on the ARIMA node map to:

| Alteryx param | Meaning | Python equivalent |
|---|---|---|
| `target_field` | Series column | `y = df[col]` |
| `freq_weekly` / `freq_monthly` / etc. | Series frequency (one is `True`) | `freq = "W"` / `"M"` / etc. (only used for date-index labelling, not for the model itself) |
| `max_p`, `max_q` | AR / MA order ceilings (non-seasonal) | `auto_arima(max_p, max_q)` |
| `s_max_P`, `s_max_Q` | seasonal AR / MA ceilings | `auto_arima(max_P, max_Q)` (only used if `seas_dif=True`) |
| `max_order` | upper bound on `p+q+P+Q` total | `auto_arima(max_order)` |
| `ic_aic` / `ic_aicc` / `ic_bic` | information criterion (one is `True`) | `auto_arima(information_criterion="aic"/"aicc"/"bic")` |
| `drift` | include linear time trend (drift) | `with_intercept=True` for d=0; for d>=1 wrap with statsmodels `trend="t"` or `"ct"` |
| `first_dif` / `seas_dif` | force differencing | `d=...` / `D=...` (else auto-detected) |
| `box_cox` | Box-Cox transform | `BoxCoxEndogTransformer` (statsmodels) — rare in practice |

**Dataiku:** No first-class visual auto-ARIMA recipe — Python is the right answer. Two viable libraries:

1. **`pmdarima`** (Hyndman-Khandakar algorithm, mirrors R's `forecast::auto.arima` closely). Cleanest port:
   ```python
   import pmdarima as pm
   model = pm.auto_arima(y, max_p=2, max_q=2, max_P=1, max_Q=1, max_order=5,
                         information_criterion="aicc", with_intercept=True,
                         seasonal=False, error_action="ignore", suppress_warnings=True)
   point, ci80 = model.predict(n_periods=horizon, return_conf_int=True, alpha=0.20)
   _,     ci95 = model.predict(n_periods=horizon, return_conf_int=True, alpha=0.05)
   ```

2. **`statsmodels.tsa.arima.ARIMA`** with manual grid search (when `pmdarima` is unavailable or pinned to an incompatible NumPy):
   ```python
   from statsmodels.tsa.arima.model import ARIMA
   import itertools
   best = None
   for p, q in itertools.product(range(0, 3), range(0, 3)):
       if p + q > 5: continue
       for trend in ["c", "ct"]:  # "c"=intercept only, "ct"=intercept+linear time (drift)
           res = ARIMA(y, order=(p, 0, q), trend=trend,
                       enforce_stationarity=False, enforce_invertibility=False).fit()
           if best is None or res.aicc < best[0]:
               best = (res.aicc, (p, 0, q), trend, res)
   res = best[3]
   fcst = res.get_forecast(steps=horizon)
   point, ci95, ci80 = fcst.predicted_mean, fcst.conf_int(alpha=0.05), fcst.conf_int(alpha=0.20)
   ```

**Output convention** (Period / Sub_Period): `Period = abs_idx // m + 1` (1-indexed period within frequency), `Sub_Period = abs_idx % m + 1` (sub-period within current Period), where `abs_idx = n + i` (i in 0..horizon-1, n is input length, m is the periodicity for the chosen frequency — 52 for weekly, 12 for monthly). Period/Sub_Period are macro-internal labels; for downstream join-back to a date axis, derive a real timestamp from the input series instead.

**Numerical fidelity warning.** Alteryx's R-based ARIMA and Python's pmdarima/statsmodels diverge by 5–15% on point estimates and 10–20% on confidence-interval widths even with identical hyperparameters. Optimizer choice (Nelder-Mead vs L-BFGS), default tolerances, and feature-search heuristics differ. **Treat this as a shape-based migration**: row count, schema, sub-period range, and forecast-trajectory direction must match; exact-string match across implementations is unreachable without invoking R from a Python recipe via `rpy2`. Acceptable validation: 6 rows, all 7 columns, point forecasts in the same magnitude band as the source, CIs widening over the horizon (low_95 < low_80 < forecast < high_80 < high_95).

**Code-env.** statsmodels and pmdarima are not in any default DSS env — install via `dku code-env set-packages <env> --packages 'pandas>=2,<3\nnumpy>=1.22,<3\nstatsmodels>=0.14\npmdarima'`. Pin numpy explicitly (pmdarima compiled against numpy<2 in some wheels — pin to `numpy<3` to allow the resolver flexibility). The Python recipe must `set-settings '{"envSelection":{"envMode":"EXPLICIT_ENV","envName":"<env>","envVersion":"BUILTIN_PINNED"}}'` to bind to the env.

### Other Predictive Tools macros

| Alteryx macro | DSS path |
|---|---|
| `Linear_Regression.yxmc` | Visual ML Lab Prediction recipe (Linear regression algorithm) — visual-first |
| `Logistic_Regression.yxmc` | Visual ML Lab Prediction recipe (Logistic regression) — visual-first |
| `Decision_Tree.yxmc` | Visual ML Lab Prediction recipe (Decision Tree) — visual-first |
| `Random_Forest.yxmc` | Visual ML Lab Prediction recipe (Random Forest) — visual-first |
| `Boosted_Model.yxmc` | Visual ML Lab Prediction recipe (XGBoost / LightGBM) — visual-first |
| `K_Centroids_Cluster_Analysis.yxmc` | Visual ML Lab Clustering recipe (K-Means) — visual-first |
| `Neural_Network.yxmc` | Visual ML Lab Prediction recipe (Deep Learning / MLP) — visual-first |
| `ARIMA.yxmc` + `TS_Forecast.yxmc` | Python recipe with statsmodels/pmdarima (above) |
| `ETS.yxmc` (exponential smoothing) | Python recipe with `statsmodels.tsa.holtwinters.ExponentialSmoothing` |
| `Spline_Model.yxmc` | Python recipe with `scipy.interpolate.UnivariateSpline` or `patsy.dmatrix("bs(...)")` |

The classification/regression cases are where visual-first applies — the DSS Lab fits the model graphically and produces a saved-model object, no Python required. Time-series and spline are Python-only.
