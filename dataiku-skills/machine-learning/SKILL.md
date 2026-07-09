---
name: machine-learning
description: Inspect Dataiku visual ML analyses and use MCP tools to create, update, train, and deploy ML tasks. Use when an agent must work with DSS ML training jobs rather than only flow recipes.
---

# Machine Learning Operations

## Workflow

1. Discover ML state proportionately:
   - for existing or ambiguous ML work, start with `list_ml_analyses`
   - to inspect an existing ML analysis, use `get_ml_analysis_summary` for a compact overview and `get_ml_analysis_settings` when you need raw feature, preprocessing, or modeling details (e.g. for updates).
2. **Create or update:**
   - Create: `create_prediction_analysis`, `create_clustering_analysis`, `create_causal_prediction_analysis`, `create_timeseries_forecasting_analysis` — DSS runs initial guessing automatically.
   - Update: `update_prediction_analysis`, `update_clustering_analysis`, `update_causal_prediction_analysis`, `update_timeseries_forecasting_analysis`.
   - Prefer iterating on one analysis over creating many near-duplicate analyses.
3. **Train:** `train_ml_analysis`. Inspect results with `list_ml_analysis_models` and `get_ml_model_details`.
4. **Deploy:** `deploy_ml_analysis_model` — two modes:
   - Fresh deploy (no existing saved model in the flow): provide `train_dataset`. Creates a new saved model + training recipe.
   - Redeploy to existing: call `list_saved_models` for the `saved_model_id`, pass as `existing_saved_model_id`.
   - Prefer `redo_optimization=false` — `redo_optimization=true` creates an unfired training recipe that must run before any downstream scoring recipe can be created.
   - For batch scoring on new data, load the `recipes` skill and create a `prediction_scoring` (or `clustering_scoring`) recipe from the deployed saved model.

## Family Subskills

Load only the relevant child when the task family is known:
- `task-types/prediction/SKILL.md` — prediction
- `task-types/clustering/SKILL.md` — clustering
- `task-types/causal-prediction/SKILL.md` — causal prediction
- `task-types/timeseries-forecasting/SKILL.md` — time series forecasting

## Prediction Heuristics

- Reject obvious identifiers and non-useful free-text columns unless the baseline shows they help.
- Prefer `ROC_AUC` for binary classification unless the user asks for a threshold-specific metric.
- Use `CLASS_WEIGHT` when classes are imbalanced.
- Reuse successful feature-role and preprocessing choices from the best existing analysis before inventing new ones.
- Prefer at least one follow-up optimization iteration after the first successful run when model quality, leakage risk, or algorithm comparison is still unclear. Skip the extra iteration when the user's goal is only to get a working first version into the flow, or when the first run is already clearly sufficient.
- Use first-class tool controls (split mode, stratification, K-fold, search strategy/validation/budget, diagnostics) before falling back to raw patches.

## Deployed Training Recipes

After `deploy_ml_analysis_model`, DSS creates a `prediction_training` (or equivalent) recipe in the flow. It is ML-managed:
- Inspect with `get_ml_analysis_settings` / `get_ml_analysis_summary`, not `get_recipe_settings`.
- Edit with `update_prediction_analysis`, not `set_recipe_settings`.
- Run the `prediction_training` recipe with `run_recipe` to retrain the model.
- For long-running training runs, load `../jobs/SKILL.md`.

## Model Interpretation

After training, explain results — don't just report the top metric.

**Classification:**
- AUC ranks positives above negatives regardless of threshold; high AUC alone doesn't confirm deployability at a specific operating point.
- Ask whether false positives or false negatives are more costly — this determines the right threshold.
- On imbalanced data, accuracy is misleading; use AUC, F1, or the precision/recall curve.

**Regression:**
- R² tells you fraction of variance explained — sanity-check against the target variable's typical range.
- Report RMSE alongside the target range to give it meaning ("RMSE of 12 on a 0–500 target" vs. "0–15" are very different).
- Flag when residuals are systematically larger for certain value ranges.

**Feature importance:**
- Explain which features drive predictions and whether that makes intuitive sense.
- Flag any single feature with >70% importance — often leakage or a target proxy.
- Importance measures correlation with the target, not causal effect.

Always connect model performance back to the business question.

## Red Flags — Investigate Before Reporting

- AUC/accuracy >0.99 on a non-trivial problem → check feature importances for leakage.
- Large train/test gap → overfitting; try simpler algorithms or stronger regularization.
- One feature >70% importance → likely leakage, near-duplicate of target, or fragile signal.
- Under ~1,000 rows → flag results as directional, not production-ready.
- Imbalanced classes with accuracy as metric → verify the metric actually finds the minority class.

## Baseline Rule

Before claiming "best," compare against: the best existing model on the same task, the strongest model in the current run, and the previous run's best score if you iterated.

## Safety Rules

- Never invent `analysis_id`, dataset names, or model IDs — discover them first.
- Announce the action before training or deployment; report validation after.
- Preserve existing task settings unless explicitly asked to change them.
- Inspect live analysis settings before changing algorithms, features, weighting, or target.
- Keep raw DSS patches minimal; report the exact patched paths in the summary.
