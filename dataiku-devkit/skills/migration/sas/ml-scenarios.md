# SAS ML and Scenario Translation

Visual ML and DSS scenario equivalents for SAS analytical and operational workflows.

## Visual ML

The Flow representation of an ML model in DSS is **always** the chain *training recipe → Saved Model → Predict recipe* — never a Python recipe configuring a model in the Lab. Use the `dku ml` namespace for setup and `dku recipe create-prediction-scoring` for the in-Flow scorer.

### Concept mapping

| SAS ML concept | Dataiku | Identify in SAS |
|---|---|---|
| Target variable | Visual ML target | `dm_dec_target`, `target=`, `response` |
| Binary target (0/1) | Two-class classification (`BINARY_CLASSIFICATION`) | `BAD`, `CHURN`, `DEFAULT` |
| Multi-class target | Multi-class (`MULTICLASS`) | discrete `CLASS` target with >2 levels |
| Continuous target | Regression (`REGRESSION`) | `PROC REG`, `PROC GLM` with continuous outcome |
| No target | Clustering | `PROC CLUSTER` |
| Imputation, OHE, train/test | Visual ML handles automatically | `SimpleImputer`, `OneHotEncoder`, `dm_traindf` |

### Canonical chain — PROC LOGISTIC / PROC REG / PROC GLM (regression) / PROC HPLOGISTIC / PROC GENMOD (with prediction)

```bash
# 1. Create the prediction ML task (auto-creates the Lab analysis + waits for feature guessing)
dku ml create-prediction joined_applicants loan_status \
    -t BINARY_CLASSIFICATION -P PROJ
# → returns analysis_id and mltask_id (e.g. bdZayVvy / WQ26griH)

# 2. Lock to the SAS-equivalent algorithm. After create-prediction the default
#    leaves both LOGISTIC_REGRESSION and RANDOM_FOREST enabled — without
#    --disable-all you ship two algorithms when SAS specified one.
dku ml set-algorithm <ANALYSIS> <MLTASK> \
    --disable-all --enable LOGISTIC_REGRESSION -P PROJ
# Algorithm names — match the SAS PROC:
#   PROC LOGISTIC, PROC HPLOGISTIC, binomial PROC GENMOD → LOGISTIC_REGRESSION
#   PROC REG, gaussian PROC GLM/GENMOD                    → LEASTSQUARE_REGRESSION
#                                                          (or RIDGE_REGRESSION
#                                                          for `lasso`/`ridge`
#                                                          options)
#   PROC GRADBOOST, PROC TREEBOOST                        → GBT_CLASSIFICATION
#                                                          / GBT_REGRESSION
#   PROC HPFOREST, PROC FOREST                            → RANDOM_FOREST_*
#   PROC HPSPLIT                                          → DECISION_TREE_*
#   PROC HPSVM                                            → SVM_CLASSIFICATION
# `dku ml algorithms <ANALYSIS> <MLTASK> -P PROJ` lists everything available.

# 3. Reject features outside the SAS MODEL spec. Repeat per non-spec column.
#    In a SAS PROC LOGISTIC `MODEL y = a b c;` only a/b/c are in scope; every
#    other column on the input dataset is implicitly excluded. DSS guess-time
#    accepts every column — you must reject the extras explicitly.
for col in $(dku dataset schema joined_applicants -P PROJ -o json \
              | jq -r '.[].name' \
              | grep -vxE 'annual_inc|dti|delinq_2yrs|inq_last_6mths|open_acc|total_acc|total_pymnt|home_ownership|initial_list_status|loan_status'); do
    dku ml set-feature <ANALYSIS> <MLTASK> "$col" --role REJECT -P PROJ
done

# 4. Train (waits for completion)
dku ml train <ANALYSIS> <MLTASK> -P PROJ --wait
# `dku ml models <ANALYSIS> <MLTASK> -P PROJ` lists the trained model IDs;
# pick the latest session (s2-pp1-m1 etc.).

# 5. Deploy the trained model into the Flow → creates a Saved Model + the
#    visual training recipe.
dku ml deploy <ANALYSIS> <MLTASK> <MODEL_ID> \
    --name "Loan Status (Logistic Regression)" \
    --train-dataset joined_applicants -P PROJ
# → returns savedModelId (e.g. du1rCRhU) and trainRecipeName.

# 6. Score new (or held-out) data — the in-Flow Predict recipe.
dku recipe create-prediction-scoring score_loan_status \
    -i joined_applicants \
    --output-ds joined_applicants_scored \
    --model <SAVED_MODEL_ID> -P PROJ
dku recipe apply-schema score_loan_status -P PROJ
dku recipe run score_loan_status -P PROJ --wait
```

After step 6 the Flow contains: source dataset → `train_*` (visual training recipe) → Saved Model → `score_*` (visual Predict recipe) → `*_scored` dataset (with `prediction`, `proba_0`, `proba_1` columns appended). Zero Python recipes.

### Known frictions in the chain (workarounds, not blockers)

| Friction | Workaround |
|---|---|
| `dku ml set-algorithm --enable X` (without `--disable-all`) leaves Random Forest enabled alongside the explicit algo | Always pair `--disable-all` with `--enable X` to lock to one algorithm |
| `dku recipe create-prediction-scoring NAME …` reports `DSS API error: 'recipe'` *on success* (response parser bug); auto-names the recipe `score_<input_dataset>` ignoring the `NAME` arg | Ignore the error — the recipe and output ARE created. Then `dku recipe rename score_<input> --name <wanted> -P PROJ` |
| `dku flow move <SAVED_MODEL_NAME> -t SAVED_MODEL` falls through to "no managed folders" | Pass the saved-model ID with `-t AUTO`: `dku flow move <SAVED_MODEL_ID> -t AUTO -z ML -P PROJ` |
| `dku analysis tasks <id>` may crash with `'str' object has no attribute 'get'` | Use `dku ml status <ANALYSIS> <MLTASK>` and `dku ml models <ANALYSIS> <MLTASK>` instead |

### SAS Viya / Enterprise Miner ML PROCs

SAS Viya HP PROCs are all tree/ensemble/neural algorithms available in Visual ML. Migrate via the same chain above, swapping the `--enable` algorithm name. Don't rewrite in Python unless the SAS call uses an option Visual ML can't express (custom loss, monotonic constraints, etc.).

| SAS PROC | Dataiku | Algorithm / note |
|---|---|---|
| `PROC GRADBOOST` (Viya) / `PROC TREEBOOST` (EM) | Visual ML | Gradient Boosted Trees (XGBoost / LightGBM backend) — `--enable GBT_CLASSIFICATION` / `GBT_REGRESSION` |
| `PROC HPFOREST` / `PROC FOREST` | Visual ML | Random Forest — `--enable RANDOM_FOREST_CLASSIFICATION` / `RANDOM_FOREST_REGRESSION` |
| `PROC HPSPLIT` | Visual ML | Decision Tree — `--enable DECISION_TREE_CLASSIFICATION` |
| `PROC HPSVM` / `PROC SVMACHINE` | Visual ML | SVM — `--enable SVM_CLASSIFICATION` (kernel from SAS `kernel=` option) |
| `PROC PLS` | Python recipe | `sklearn.cross_decomposition.PLSRegression` — no Visual ML equivalent |
| Neural / `PROC NEURAL` / `PROC HPNEURAL` | Visual ML (MLP) or Python (`keras`/`pytorch`) | Visual ML MLP (`--enable NEURAL_NETWORK`) for shallow nets; Python for bespoke architectures |
| k-NN (`PROC DISCRIM method=npar k=`) | Visual ML (K-Nearest Neighbors) | `--enable KNN`. Distance metric usually euclidean — verify SAS `METRIC=` option |
| `PROC HPCLUS` | Visual ML clustering (`dku ml create-clustering`) | K-means / hierarchical |
| `PROC FACTMAC` (factorization machines) | Python recipe | `lightfm` or `xlearn` |

**Hyperparameter mapping:** SAS `ntrees= maxdepth= minleafsize=` → Visual ML GBT / RF grid. Translate the search space, don't pin single values — Visual ML tunes across the grid and picks the best. Tune via `dku ml settings <ANALYSIS> <MLTASK> -P PROJ` to inspect the grid; edit and re-`set-settings` if the defaults don't match the SAS call.

---

## Scheduling, checks, reporting → DSS scenarios

Most SAS installs orchestrate their jobs outside the `.sas` files: a batch scheduler (cron, Control-M, Autosys, LSF, SAS Enterprise Scheduler) runs programs on a calendar; `PUT` / `PUTLOG` lines plus `PROC COMPARE` / custom macros act as checks; `FILENAME EMAIL` or `PROC REPORT` produce reports. In Dataiku, all three collapse into a **scenario**: one scenario per pipeline, with steps, triggers, checks, and reporters.

### Scheduling trigger

| SAS side | DSS equivalent | Command |
|---|---|---|
| Cron line `0 6 * * 1-5 sas program.sas` | Scenario `time_trigger` | `dku scenario add-trigger NAME -t time_trigger --params '{"repeatFrequency":"DAY","hour":6,"minute":0,"daysOfWeek":["MON","TUE","WED","THU","FRI"]}' -P PROJ` |
| Cron `*/15 * * * *` (every 15 min) | `time_trigger` with `repeatFrequency=MINUTE`, `intervalMinutes=15` | — |
| Control-M / Autosys dependency ("after job X succeeds") | Upstream scenario's reporter runs downstream via `run_scenario` step, or downstream uses a `dataset_modified` trigger on the upstream's output | Avoid cross-scenario success polling |
| Event-driven: "run when file lands" | `dataset_modified` trigger on the ingest dataset | `-t dataset_modified --params '{"datasetsToMonitor":[...]}'` |
| On-demand button | No trigger — run manually via `dku scenario run NAME -P PROJ` | — |

### Pipeline orchestration

| SAS side | DSS scenario step | Notes |
|---|---|---|
| `%include 'build_step1.sas';` ... `'build_step2.sas';` in order | One `build_flowitem` step per output dataset, in order | DSS infers the build order from the flow DAG — usually one step building the terminal dataset is enough |
| `if &rc. ne 0 then %abort;` after each step | Scenario step `onFailure: "FAIL"` (default) | Scenarios stop on first failure unless the step is marked non-blocking |
| Retry loop around a failing step | Step `onFailure: "CONTINUE"` + a downstream `check_dataset` | Don't replicate the retry loop — let the scheduler re-fire the scenario |
| Per-month expansion (`%do m = 1 %to 12`) running the same pipeline 12× | Scenario with a `custom_python` step looping and invoking each build | `project.get_scenario().run(variables={...})` from the Python step |
| `%JOB_CONTROL_UPDT` writing run metadata | Scenario run history — automatic | `dku scenario last-run NAME -P PROJ -o json` returns start/end/status |

### Checks (QA / data quality)

SAS programs often include ad-hoc checks: `if nobs = 0 then abort;`, `proc compare base=expected compare=actual;`, custom macros counting nulls. In Dataiku, attach checks to the relevant dataset (metrics + checks) and reference them from the scenario.

| SAS check pattern | DSS equivalent |
|---|---|
| `proc sql; select count(*) from ds; …if 0 then abort;` | Dataset metric `Record count` + check `Record count > 0` + scenario `check_dataset` step |
| `proc freq data=ds; tables status / missing;` used for null audits | Metric `Column values count (not empty)` per column + check |
| `proc compare base=expected compare=actual;` | Two datasets + a Prepare recipe producing a diff, plus a `check_dataset` on `count == 0` |
| Custom threshold (e.g. `avg(revenue) > 1000`) | Metric `Column statistics` (avg) + check `value > 1000` |
| Schema drift (SAS `var_exist` macro) | Metric + check on `Record count` per column type, or a Python-coded check |

`dku scenario add-step` supports `check_dataset` and `compute_metrics`. Set these on the *input* dataset to the step they guard, not the output — guarding the output means the check runs after the expensive build.

### Reporting / notifications

| SAS side | DSS reporter |
|---|---|
| `FILENAME mail EMAIL ...; data _null_; file mail; put ...;` | Email reporter on scenario — `dku scenario add-reporter NAME -t mail --params '{"recipient":"ops@x","subject":"…"}'` |
| Slack via custom macro / webhook | Webhook reporter (`msteams-webhook`, `slack-webhook`) |
| `PROC REPORT` → PDF attached | Dashboard export via reporter (attach dashboard PDF to email) |
| Per-step logs mailed on failure | Default scenario behavior: mail reporter with `onSuccess: false, onFailure: true` |

### Dispatching reminder

Not every `.sas` file is a scenario step. Inventory SAS jobs into three piles before writing recipes:

1. **Transformation** (DATA/PROC producing a dataset) → recipe in the flow
2. **Orchestration** (master driver calling transformation files) → scenario with `build_flowitem` steps
3. **Checks / reports** (no new dataset, just audits or emails) → scenario check/reporter, not a recipe

Misclassifying reports as Python recipes is the most common scheduling-migration error. A Python recipe writes a dataset; if there's no dataset to produce, it's a reporter.

---
