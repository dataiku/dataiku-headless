# Alteryx Stats, Optimization & Predictive Tools → Dataiku

The analytical/modeling tail: correlation, mathematical optimization (LP / MILP / knapsack / allocation), and the R-based Predictive Tool macros (regression, classification, clustering, ARIMA / ETS time-series). Most are the legitimate Python / Visual-ML-Lab escape hatches — read the altitude rules first.

**Contents:** PearsonCorrelation · Optimization & prescriptive macros · Predictive Tools (regression / classification / clustering / ARIMA / ETS) · Building the model headless (`dku ml`).

## PearsonCorrelation

Correlation matrix across numeric columns. **Preferred (visual-first, headless-safe):** Sync to SQL, then SQL recipe with `CORR()` (in every standard engine):

```bash
dku recipe create-sync sync_to_db -P PROJ -i input --output-ds input_db -c <sql_connection>
dku recipe create-sql pearson -P PROJ -i input_db --output-ds pearson_result --connection <sql_connection> \
    --sql 'SELECT CORR(COALESCE("col_a", 0), COALESCE("col_b", 0)) AS "Result" FROM ${projectKey}_input_db'
```

**Critical: `COALESCE(col, 0)` for null-handling parity.** Alteryx PearsonCorrelation **treats null as 0**, NOT pairwise-complete (the SQL `CORR()`/pandas/numpy convention). On sparse-null data the coefficient can differ by 2×+; `COALESCE(.,0)` reproduces Alteryx exactly. See `semantics.md` § Aggregation null-handling. Multi-column matrix → one row per pair via `UNION ALL` or Python (DSS Statistics cards are UI-only, not scenario-runnable).

---

## Optimization & prescriptive macros (knapsack, Optimization tool, location optimizer)

**FIRST: is it MONOTONIC priority-fill against a fixed capacity? That is a WINDOW, not Python.** Classify the greedy:

| Greedy shape | Path |
|---|---|
| **Monotonic fill-until-empty** — allocate capacity `C` to demand rows in priority order, each gets what's left, partial-fill the boundary, zero after. No accept/reject branching; allocation depends only on cumulative demand *above*. | **One Window + one Prepare, NO Python.** Window `--partition-key <grp> --order-key Priority:desc --compute 'sum:Demand' --frame-preceding 1000 --frame-following 0` (cumulative-INCLUSIVE; `:output` rename ignored → DSS auto-names `Demand_sum`); Prepare `cum_before=Demand_sum-Demand`; `fulfilled=max(0,min(Demand,Capacity-cum_before))`; `unmet=Demand-fulfilled`. The standard waterfall shape (inventory fill, budget waterfall, seniority). |
| **Conditional-carry / skip-if-over** (knapsack: skip an item that would breach the cap, keep filling with later smaller ones) — running total branches on prior accept/reject | **CANNOT be a Window** → Python (or SQL recursive CTE — `tools-state-parsing.md` § MultiRowFormula). See knapsack below |

The real **Optimization** tool (LP/MILP), the location optimizer, and home-grown knapsack/allocation `.yxmc` macros have **no DSS visual recipe** → a single Python recipe (EXCEPT the monotonic case). Pick the library:
- **Small / heuristic** (greedy fill, top-N-under-budget, textbook knapsack) → plain Python, no solver. These are usually a *heuristic*, not a true optimum — reproduce the macro's algorithm, not the mathematical optimum, when matching a GT table.
- **True LP / MILP / assignment** → `PuLP` or `OR-Tools` (add to a code env).

**Decode the macro before reimplementing.** A `.yxzp` is a zip: unzip → `.yxmd` + bundled macros under `_externals/N/*.yxmc`. The "solver" is often a recognizable greedy.

**Knapsack — heuristic, reproduce the macro's algorithm.** A `Knapsack_Macro.yxmc` (`Sort($ desc) → MultiRowFormula(conditional-carry: add weight only if running ≤ CAP else keep prior = SKIP) → Unique → RecordID → AppendFields(× NumItems) → Filter(Count ≤ NumItems)`) is greedy (often == optimum on small inputs). One Python recipe:
```python
order = sorted(boxes, key=lambda b: (-b["value"], b["kg"]))  # $ desc, kg ASC tiebreak
kept, running = [], 0
for b in order:                       # conditional-carry == skip-overflow
    if running + b["kg"] <= CAP:
        kept.append(b); running += b["kg"]
for n in range(1, MAX_N + 1):         # AppendFields(NumItems) + Filter(Count <= NumItems)
    selected = kept[:n]
```
The `$ desc` sort needs a **`kg` ASC tiebreak** to match the macro's box-numbering (ties → keep the lighter). The conditional-carry running total can't be a Window (`tools-state-parsing.md` § MultiRowFormula).

**Decode the *real* Optimization tool's matrix input mode.** When the `.yxmd` has an `Optimization` node, read `<Configuration>`: `maximize`, `problemType=LP/ILP/MILP`, `solver=glpk`, `inputMode=matrix`. **Matrix mode** has no formula string — reverse-engineer from upstream `AlteryxSelect` renames + `Formula` literals + a constraint `TextInput`:
- **Objective** = the column renamed `coefficient` (one row/decision var); variable label = column renamed `variable`.
- **Variable bounds & type** = `Formula` fields `lb`/`ub`/`type` (`'B'`=binary, `'I'`=integer, `'C'`=continuous).
- **Each constraint's LHS coefficients** = one more renamed column per constraint. The tool reads **all numeric columns except the objective** as constraint vectors, in column order.
- **Constraint directions + RHS** = a separate `TextInput` (`dir`,`rhs`), one row per constraint; an equality `==8` is a `<=`/`>=` pair. Match positionally to the coefficient columns.

**PuLP — true MILP selection model.** Pick K items maximizing an objective under a budget cap (~15 tools → one recipe). A `Sample(Mode=Skip,N=1)` after the tool drops the objective-value summary row — in Python just don't emit it.
```python
import pulp
prob = pulp.LpProblem("DreamTeam", pulp.LpMaximize)
x = {a: pulp.LpVariable(f"x_{i}", cat="Binary") for i, a in enumerate(authors)}
prob += pulp.lpSum(challenges[a] * x[a] for a in authors)          # objective ('coefficient' col)
prob += pulp.lpSum(prices[a] * x[a] for a in authors) <= 1_500_000  # budget ('cost' col, dir/rhs row)
prob += pulp.lpSum(x[a] for a in authors) == 8                      # team size (<=8 AND >=8 → ==8)
prob.solve(pulp.PULP_CBC_CMD(msg=0))
team = [a for a in authors if pulp.value(x[a]) > 0.5]
```
**⚠ Alternate-optima validation — validate by OBJECTIVE + CONSTRAINTS, not exact rows.** A true LP/MILP often has multiple optima: when candidates tie for the last slot, CBC/glpk/SCIP can each pick a *different* tied item, so an exact-row diff **falsely fails a correct migration**. Validate (a) objective value matches, (b) every constraint binds (exact count, cost == cap), (c) non-tied members identical; only the tied slot may differ. (Inverse of the heuristic-macro rule: a true solver has no reproducible tiebreak — don't try to match one.)

---

## Predictive Tools (R-based macros)

Alteryx ships `Predictive Tools\*.yxmc` macros wrapping R (`forecast`, `nnet`, `glmnet`, …). In `.yxmd` they are `<Node>` with `<EngineSettings Macro="Predictive Tools\<Name>.yxmc" />` and an EMPTY `<GuiSettings Plugin>` → XML parsing returns an empty plugin name. **Always check `EngineSettings/@Macro` when `Plugin` is empty.**

**The model spec is in the PARENT node, NOT the `.yxmc`.** The macro reads parameters from the parent `<Node>`'s `<Configuration>` `<Value name="...">` elements. For `Linear_Regression.yxmc`: `<Value name="Y Var">Wins</Value>`, `<Value name="X Vars">R_G + R + HR + …</Value>` (` + `-joined → `[v.strip() for v in value.split("+")]`), `<Value name="Omit Constant">False</Value>`. `.yxmd` parsing alone recovers target + predictors + intercept — never open the `.yxmc`.

### ARIMA + TS_Forecast (time-series forecasting)

`ARIMA.yxmc` (fit) → `TS_Forecast.yxmc` (forecast + CIs). Output schema: `Period, Sub_Period, forecast, forecast_high_95, forecast_high_80, forecast_low_80, forecast_low_95`. Param map: `target_field`→`y`; `freq_*`→`freq` (labelling only); `max_p/max_q`→`auto_arima(max_p,max_q)`; `s_max_P/s_max_Q`→seasonal (only if `seas_dif=True`); `max_order`→bound on `p+q+P+Q`; `ic_*`→`information_criterion`; `drift`→`with_intercept=True` (d=0) / statsmodels `trend="t"/"ct"` (d≥1); `first_dif/seas_dif`→`d`/`D`; `box_cox`→`BoxCoxEndogTransformer` (rare).

No first-class visual auto-ARIMA — Python. Two libraries:

1. **`pmdarima`** (mirrors R `forecast::auto.arima`):
   ```python
   import pmdarima as pm
   model = pm.auto_arima(y, max_p=2, max_q=2, max_P=1, max_Q=1, max_order=5,
                         information_criterion="aicc", with_intercept=True,
                         seasonal=False, error_action="ignore", suppress_warnings=True)
   point, ci80 = model.predict(n_periods=horizon, return_conf_int=True, alpha=0.20)
   _,     ci95 = model.predict(n_periods=horizon, return_conf_int=True, alpha=0.05)
   ```
2. **`statsmodels.tsa.arima.ARIMA`** with manual grid search (pmdarima unavailable / NumPy-pinned):
   ```python
   from statsmodels.tsa.arima.model import ARIMA
   import itertools
   best = None
   for p, q in itertools.product(range(0, 3), range(0, 3)):
       if p + q > 5: continue
       for trend in ["c", "ct"]:  # "c"=intercept, "ct"=intercept+linear time (drift)
           res = ARIMA(y, order=(p, 0, q), trend=trend,
                       enforce_stationarity=False, enforce_invertibility=False).fit()
           if best is None or res.aicc < best[0]:
               best = (res.aicc, (p, 0, q), trend, res)
   fcst = best[3].get_forecast(steps=horizon)
   point, ci95, ci80 = fcst.predicted_mean, fcst.conf_int(alpha=0.05), fcst.conf_int(alpha=0.20)
   ```

**Output convention** (Period/Sub_Period): `Period = abs_idx // m + 1`, `Sub_Period = abs_idx % m + 1`, `abs_idx = n + i` (n=input length, m=periodicity — 52 weekly, 12 monthly). Macro-internal labels; for join-back to a date axis, derive a real timestamp from the input series.

**Numerical fidelity — shape-based validation only.** Alteryx R-ARIMA vs pmdarima/statsmodels diverge 5–15% on points, 10–20% on CI widths even with identical hyperparameters (different optimizer/tolerances/heuristics); exact-string match needs `rpy2`. Validate: row count, schema, sub-period range, trajectory direction, points in the same magnitude band, CIs widening (low_95 < low_80 < forecast < high_80 < high_95).

**Code-env.** Not in any default env — `dku code-env set-packages <env> --packages 'pandas>=2,<3\nnumpy>=1.22,<3\nstatsmodels>=0.14\npmdarima'` (pin numpy `<3`; pmdarima compiled against numpy<2 in some wheels). Bind: `dku recipe set-env R --env-mode EXPLICIT_ENV --env-name <env> --container-mode NONE -P PROJ` — do NOT hand-edit `envSelection` via `set-settings`.

**`TS Model Factory` + `TS Forecast Factory` (multi-series).** Grouped generalization: builds **one model per group, auto-selecting ETS-vs-ARIMA per series** by information criterion. Check `@Macro` (empty `Plugin`). **DSS port:** one Python recipe looping over the group key, running both `pm.auto_arima(...)` AND a `statsmodels ExponentialSmoothing` ETS fit per series, picking the lower-AICc, concatenating. The per-series bake-off IS the Factory's job — don't hardcode ARIMA. Same shape-validation + code-env caveats.

### Other Predictive Tools macros

| Alteryx macro | DSS path |
|---|---|
| `Linear_Regression.yxmc` | Exact-match → plain OLS Python (below). Deploy/metrics → Visual ML Lab (OLS) |
| `Logistic_Regression.yxmc` | Visual ML Lab Prediction (Logistic) — visual-first |
| `Decision_Tree.yxmc` | Visual ML Lab Prediction (Decision Tree) |
| `Random_Forest.yxmc` | Visual ML Lab Prediction (Random Forest) |
| `Boosted_Model.yxmc` | Visual ML Lab Prediction (XGBoost/LightGBM) |
| `K_Centroids_Cluster_Analysis.yxmc` | Visual ML Lab Clustering (K-Means) |
| `Neural_Network.yxmc` | Visual ML Lab Prediction (Deep Learning/MLP) |
| `ARIMA.yxmc` + `TS_Forecast.yxmc` | Python statsmodels/pmdarima (above) |
| `ETS.yxmc` | Python `statsmodels.tsa.holtwinters.ExponentialSmoothing` |
| `Spline_Model.yxmc` | Python `scipy.interpolate.UnivariateSpline` or `patsy.dmatrix("bs(...)")` |

Classification/regression → DSS Lab (graphical fit → saved-model, no Python). Time-series/spline → Python-only.

#### `Linear_Regression.yxmc` — pick the path by deliverable

- **Deployed model / sane metrics** → Visual ML Lab. Exact coefficient match is NOT achievable (DSS ridge regularization, CV folds, preprocessing). Validate by "trains, sane R²/RMSE, deployable."
- **Scored table that must equal a GT key** → **plain OLS in one Python recipe**, NOT the Lab. `Linear_Regression.yxmc` = R `lm()` = **unregularized OLS with intercept** — *as long as `regularization=False`* (a `lambda_*`/`internal_cv` config alone does NOT mean glmnet). `numpy.linalg.lstsq` reproduces it to floating-point; after the downstream `Select Int32` rounding the integer predictions match exactly. The Lab's ridge shifts every coefficient and will NOT match.
  ```python
  # Omit Constant=False → prepend a 1s column; Score = X_score @ beta; AlteryxSelect Int32 = round.
  import numpy as np
  X  = np.column_stack([np.ones(len(df)),  df[x_vars].astype(float).values])   # x_vars = "X Vars".split("+")
  beta, *_ = np.linalg.lstsq(X, df[y_var].astype(float).values, rcond=None)
  Xs = np.column_stack([np.ones(len(sub)), sub[x_vars].astype(float).values])  # sub = Filter([Tm] in(...))
  sub["Projected Wins"] = np.rint(Xs @ beta).astype(int)
  ```
  **The correlation branches are analysis-only — don't migrate as logic.** A shipped `Association_Analysis.yxmc` (Pearson) / `SpearmanCorrCoeff` branch only *discovers/justifies* the top-N predictors; it does NOT feed the regression (the predictor set is whatever `<Value name="X Vars">` lists). Skip them — documentation.

### Building the model headless (`dku ml`)

The Lab is scriptable end-to-end:
```bash
dku ml create-prediction <dataset> <Target> -t BINARY_CLASSIFICATION -P PROJ   # → analysis_id + mltask_id
dku ml algorithms <AID> <MID> -P PROJ           # LOGISTIC_REGRESSION + RANDOM_FOREST on by default
dku ml set-feature <AID> <MID> "<source col>" --role REJECT -P PROJ            # repeat per non-predictor
dku ml train <AID> <MID> -P PROJ --wait
dku ml details <AID> <MID> <MODEL_ID> -P PROJ   # auc / accuracy / f1
dku ml deploy <AID> <MID> <MODEL_ID> --name <SM> --train-dataset <dataset> -P PROJ
```
**CRITICAL:** DSS auto-includes ALL columns; the column the TARGET was derived from leaks → AUC 1.0. Reject every non-predictor (and IDs) via `set-feature --role REJECT`.

- **No shipped answer key is NOT an automatic block — the deciding factor is `regularization`.** Read `<Value name="regularization">` FIRST (the node ALWAYS carries `lambda_1se`/`lambda_min`/`alpha`/`nfolds`/`internal_cv`/`set_seed_*` as inert UI defaults even when regularization is OFF — do NOT infer from `lambda_*`):
  - **`regularization=False` (plain `lm()`/OLS) → FINISH by shape, do NOT block.** Deterministic + cross-engine reproducible (`statsmodels`/`lstsq` == R `lm()`); integer-rounded predictions match exactly even with `standardize_pred=True` (OLS fitted values invariant to predictor rescaling). Validate by row-equality, or by shape when no key ships (trains, sensible coefficient signs, plausible R²/F-p, predictions in range). **Prep trap:** a collapsed-away Alteryx `Imputation` macro may silently drop a non-event row (placeholder with a real label but blank stats) — drop non-event rows by a **blank TARGET**, not a blank label column, or `statsmodels` dies `exog contains inf or nans`.
  - **`regularization=True` (`glmnet`) AND no row-level GT → block.** Alteryx regularized `glmnet` vs DSS scikit differ in penalty/CV/seeding → nothing to diff. Tell-tale: `regularization=True` + 7× `BrowseV2` + no GT TextInput. Treat as "trains, sane R²/AUC, deployable"; validate only the deterministic ETL.
- **`Oversample Field` tool** → DSS **class rebalancing** in the ML task's train/test settings (sample weights / class-rebalance), NOT a separate recipe. On a rare positive (sub-1% prevalence) the un-rebalanced model gets high accuracy but ~0 recall — rebalancing is a faithful part of the migration.
