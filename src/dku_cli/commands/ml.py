"""dku ml — create, train, deploy, and manage ML tasks."""

from __future__ import annotations

import json
from typing import List, Optional

import typer

from dku_cli.enums import FeatureRole
from dku_cli.errors import exit_with_error, handle_api_error
from dku_cli.helpers import (
    get_client_from_ctx,
    resolve_project,
)
from dku_cli.output import (
    info,
    render,
    render_raw,
    resolve_output_format,
    success,
    warn,
)

app = typer.Typer(
    help="Create, train, and deploy ML models (prediction, clustering, timeseries, causal)."
)


# ---------------------------------------------------------------------------
# Create commands — use project-level shortcuts (create analysis + task in one call)
# ---------------------------------------------------------------------------


@app.command("create-prediction")
def create_prediction(
    ctx: typer.Context,
    dataset: str = typer.Argument(help="Input dataset name"),
    target: str = typer.Argument(help="Target variable to predict"),
    prediction_type: Optional[str] = typer.Option(
        None,
        "--type",
        "-t",
        help="BINARY_CLASSIFICATION, REGRESSION, or MULTICLASS (auto-detected if omitted)",
    ),
    guess_policy: str = typer.Option(
        "DEFAULT",
        "--guess-policy",
        help="DEFAULT, SIMPLE_FORMULA, DECISION_TREE, EXPLANATORY, or PERFORMANCE",
    ),
    backend: str = typer.Option(
        "PY_MEMORY", "--backend", help="ML backend: PY_MEMORY, MLLIB, or H2O"
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Create a prediction ML task from a dataset.

    Creates a visual analysis + ML task and waits for feature guessing to complete.
    Returns the analysis_id and mltask_id needed for 'dku ml train' and 'dku ml deploy'.
    """
    project_key = resolve_project(project)
    output = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        mltask = proj.create_prediction_ml_task(
            dataset,
            target,
            ml_backend_type=backend,
            guess_policy=guess_policy,
            prediction_type=prediction_type,
            wait_guess_complete=True,
        )
        result = {"analysis_id": mltask.analysis_id, "mltask_id": mltask.mltask_id}
        render_raw(result, output)
        success(
            f"ML task ready. Train with: dku ml train {mltask.analysis_id} {mltask.mltask_id} -P {project_key}"
        )
    except Exception as e:
        handle_api_error(e)


@app.command("create-clustering")
def create_clustering(
    ctx: typer.Context,
    dataset: str = typer.Argument(help="Input dataset name"),
    guess_policy: str = typer.Option(
        "KMEANS", "--guess-policy", help="KMEANS or ANOMALY_DETECTION"
    ),
    backend: str = typer.Option(
        "PY_MEMORY", "--backend", help="ML backend: PY_MEMORY, MLLIB, or H2O"
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Create a clustering ML task from a dataset.

    Creates a visual analysis + ML task and waits for feature guessing to complete.
    """
    project_key = resolve_project(project)
    output = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        mltask = proj.create_clustering_ml_task(
            dataset,
            ml_backend_type=backend,
            guess_policy=guess_policy,
            wait_guess_complete=True,
        )
        result = {"analysis_id": mltask.analysis_id, "mltask_id": mltask.mltask_id}
        render_raw(result, output)
        success(
            f"ML task ready. Train with: dku ml train {mltask.analysis_id} {mltask.mltask_id} -P {project_key}"
        )
    except Exception as e:
        handle_api_error(e)


@app.command("create-timeseries")
def create_timeseries(
    ctx: typer.Context,
    dataset: str = typer.Argument(help="Input dataset name"),
    target: str = typer.Argument(help="Target variable to forecast"),
    time_column: str = typer.Argument(help="Time variable column (must be Date type)"),
    identifiers: Optional[List[str]] = typer.Option(
        None,
        "--identifier",
        "-i",
        help="Time series identifier column(s) for multi-series (repeatable)",
    ),
    guess_policy: str = typer.Option(
        "TIMESERIES_DEFAULT",
        "--guess-policy",
        help="TIMESERIES_DEFAULT, TIMESERIES_STATISTICAL, or TIMESERIES_DEEP_LEARNING",
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Create a time series forecasting ML task from a dataset.

    Creates a visual analysis + ML task and waits for feature guessing to complete.
    """
    project_key = resolve_project(project)
    output = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        mltask = proj.create_timeseries_forecasting_ml_task(
            dataset,
            target,
            time_column,
            timeseries_identifiers=identifiers,
            guess_policy=guess_policy,
            wait_guess_complete=True,
        )
        result = {"analysis_id": mltask.analysis_id, "mltask_id": mltask.mltask_id}
        render_raw(result, output)
        success(
            f"ML task ready. Train with: dku ml train {mltask.analysis_id} {mltask.mltask_id} -P {project_key}"
        )
    except Exception as e:
        handle_api_error(e)


@app.command("create-causal")
def create_causal(
    ctx: typer.Context,
    dataset: str = typer.Argument(help="Input dataset name"),
    outcome: str = typer.Argument(help="Outcome variable to predict"),
    treatment: str = typer.Argument(help="Treatment variable"),
    prediction_type: Optional[str] = typer.Option(
        None,
        "--type",
        "-t",
        help="CAUSAL_BINARY_CLASSIFICATION or CAUSAL_REGRESSION (auto-detected if omitted)",
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Create a causal prediction ML task from a dataset.

    Creates a visual analysis + ML task for estimating treatment effects.
    """
    project_key = resolve_project(project)
    output = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        mltask = proj.create_causal_prediction_ml_task(
            dataset,
            outcome,
            treatment,
            prediction_type=prediction_type,
            wait_guess_complete=True,
        )
        result = {"analysis_id": mltask.analysis_id, "mltask_id": mltask.mltask_id}
        render_raw(result, output)
        success(
            f"ML task ready. Train with: dku ml train {mltask.analysis_id} {mltask.mltask_id} -P {project_key}"
        )
    except Exception as e:
        handle_api_error(e)


# ---------------------------------------------------------------------------
# List / status
# ---------------------------------------------------------------------------


@app.command("list")
def list_tasks(
    ctx: typer.Context,
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """List all ML tasks in a project."""
    project_key = resolve_project(project)
    output = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        raw = proj.list_ml_tasks()
        tasks = raw.get("mlTasks", []) if isinstance(raw, dict) else raw

        data = []
        for t in tasks:
            data.append(
                {
                    "analysis_id": t.get("analysisId", ""),
                    "mltask_id": t.get("mlTaskId", ""),
                    "type": t.get("taskType", ""),
                    "target": t.get("targetVariable", ""),
                    "dataset": t.get("inputDataset", ""),
                }
            )

        render(
            data,
            ["analysis_id", "mltask_id", "type", "target", "dataset"],
            output_format=output,
            title=f"ML Tasks ({project_key})",
        )
    except Exception as e:
        handle_api_error(e)


@app.command()
def status(
    ctx: typer.Context,
    analysis_id: str = typer.Argument(help="Analysis ID"),
    mltask_id: str = typer.Argument(help="ML task ID"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Show status of an ML task (guessing, training, model count)."""
    project_key = resolve_project(project)
    output = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        mltask = proj.get_ml_task(analysis_id, mltask_id)
        st = mltask.get_status()

        if output == "json":
            print(json.dumps(st, indent=2, default=str))
        else:
            model_ids = st.get("fullModelIds", [])
            data = [
                {"field": "Guessing", "value": str(st.get("guessing", ""))},
                {"field": "Training", "value": str(st.get("training", ""))},
                {"field": "Models trained", "value": str(len(model_ids))},
            ]
            render(
                data,
                ["field", "value"],
                output_format=output,
                title=f"ML Task Status: {mltask_id}",
            )
    except Exception as e:
        handle_api_error(e)


# ---------------------------------------------------------------------------
# Train
# ---------------------------------------------------------------------------


@app.command()
def train(
    ctx: typer.Context,
    analysis_id: str = typer.Argument(help="Analysis ID"),
    mltask_id: str = typer.Argument(help="ML task ID"),
    session_name: Optional[str] = typer.Option(
        None, "--session-name", help="Training session name"
    ),
    wait: bool = typer.Option(
        True, "--wait/--no-wait", help="Wait for training to complete"
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Train models for an ML task.

    By default waits for training to complete and returns trained model IDs.
    Use --no-wait to start asynchronously, then check with 'dku ml status'.
    """
    project_key = resolve_project(project)
    output = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        mltask = proj.get_ml_task(analysis_id, mltask_id)

        if wait:
            model_ids = mltask.train(session_name=session_name)
            result = {"model_ids": model_ids, "count": len(model_ids)}
            render_raw(result, output)
            success(
                f"Trained {len(model_ids)} model(s). "
                f"Deploy best: dku ml deploy {analysis_id} {mltask_id} MODEL_ID "
                f"--name NAME --train-dataset DS -P {project_key}"
            )
        else:
            mltask.start_train(session_name=session_name)
            success(
                f"Training started. Check progress: dku ml status {analysis_id} {mltask_id} -P {project_key}"
            )
    except Exception as e:
        handle_api_error(e)


# ---------------------------------------------------------------------------
# Models / details
# ---------------------------------------------------------------------------

# Scalar performance metrics the trained-model snippet already carries at its
# top level (verified live on DSS 14.6). Surfacing them here lets an agent
# pick the best model straight from `dku ml models` instead of N+1
# `dku ml details` calls.
_SNIPPET_METRICS = (
    "auc",
    "f1",
    "accuracy",
    "precision",
    "recall",
    "logLoss",  # classification
    "r2",
    "rmse",
    "mae",
    "mape",
    "evs",
    "rmsle",  # regression
    "silhouette",  # clustering
)

# evaluationMetric enum value → snippet field carrying that score.
_EVAL_METRIC_FIELDS = {
    "ROC_AUC": "auc",
    "F1": "f1",
    "ACCURACY": "accuracy",
    "PRECISION": "precision",
    "RECALL": "recall",
    "LOG_LOSS": "logLoss",
    "R2": "r2",
    "RMSE": "rmse",
    "MAE": "mae",
    "MAPE": "mape",
    "EVS": "evs",
    "RMSLE": "rmsle",
    "SILHOUETTE": "silhouette",
}

_LOWER_IS_BETTER_METRICS = {
    "LOG_LOSS",
    "RMSE",
    "MAE",
    "MAPE",
    "RMSLE",
}


def _score_direction(eval_metric: str) -> str:
    if eval_metric not in _EVAL_METRIC_FIELDS:
        return ""
    return "lower" if eval_metric in _LOWER_IS_BETTER_METRICS else "higher"


def _rank_score(score: object, direction: str) -> float | str:
    if isinstance(score, bool) or not isinstance(score, (int, float)):
        return ""
    ranked = -score if direction == "lower" else score
    return round(ranked, 4)


@app.command()
def models(
    ctx: typer.Context,
    analysis_id: str = typer.Argument(help="Analysis ID"),
    mltask_id: str = typer.Argument(help="ML task ID"),
    session: Optional[str] = typer.Option(
        None, "--session", help="Filter by session ID"
    ),
    algorithm: Optional[str] = typer.Option(
        None, "--algorithm", help="Filter by algorithm name"
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """List trained models in an ML task with their headline metric.

    The table shows METRIC/SCORE (the task's evaluation metric). JSON output
    additionally includes SCORE_DIRECTION, RANK_SCORE, and every scalar metric
    present in the snippet (auc, f1, accuracy, logLoss, r2, rmse, ...). Pick
    the best model with:
    dku ml models A M -P PROJ -o json | jq 'max_by(.rank_score)'
    """
    project_key = resolve_project(project)
    output = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        mltask = proj.get_ml_task(analysis_id, mltask_id)
        ids = mltask.get_trained_models_ids(session_id=session, algorithm=algorithm)

        data = []
        for mid in ids:
            snippet = mltask.get_trained_model_snippet(id=mid)
            eval_metric = snippet.get("evaluationMetric", "")
            score_field = _EVAL_METRIC_FIELDS.get(eval_metric, "")
            score = snippet.get(score_field) if score_field else None
            direction = _score_direction(eval_metric)
            row = {
                "id": mid,
                "algorithm": snippet.get("algorithm", ""),
                "session": snippet.get("sessionId", ""),
                "state": snippet.get("trainInfo", {}).get("state", ""),
                "metric": eval_metric,
                "score": (
                    round(score, 4)
                    if isinstance(score, (int, float)) and not isinstance(score, bool)
                    else ""
                ),
                "score_direction": direction,
                "rank_score": _rank_score(score, direction),
            }
            for field in _SNIPPET_METRICS:
                if field in snippet:
                    row[field] = snippet[field]
            data.append(row)

        columns = ["id", "algorithm", "session", "state", "metric", "score"]
        if output == "json":
            columns += ["score_direction", "rank_score"]
            columns += [f for f in _SNIPPET_METRICS if any(f in r for r in data)]

        render(
            data,
            columns,
            output_format=output,
            title=f"Trained Models ({mltask_id})",
        )
    except Exception as e:
        handle_api_error(e)


@app.command()
def details(
    ctx: typer.Context,
    analysis_id: str = typer.Argument(help="Analysis ID"),
    mltask_id: str = typer.Argument(help="ML task ID"),
    model_id: str = typer.Argument(help="Trained model ID (from 'dku ml models')"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Show performance metrics for a trained model."""
    project_key = resolve_project(project)
    output = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        mltask = proj.get_ml_task(analysis_id, mltask_id)
        model_details = mltask.get_trained_model_details(model_id)
        perf = model_details.get_performance_metrics()

        if output == "json":
            print(json.dumps(perf, indent=2, default=str))
        else:
            data = [
                {"metric": k, "value": v}
                for k, v in perf.items()
                if not isinstance(v, (dict, list))
            ]
            render(
                data,
                ["metric", "value"],
                output_format=output,
                title=f"Model Metrics: {model_id}",
            )
    except Exception as e:
        handle_api_error(e)


# ---------------------------------------------------------------------------
# Deploy
# ---------------------------------------------------------------------------


@app.command()
def deploy(
    ctx: typer.Context,
    analysis_id: str = typer.Argument(help="Analysis ID"),
    mltask_id: str = typer.Argument(help="ML task ID"),
    model_id: str = typer.Argument(help="Trained model ID (from 'dku ml models')"),
    name: str = typer.Option(
        ..., "--name", "-n", help="Name for the saved model in the flow"
    ),
    train_dataset: str = typer.Option(
        ..., "--train-dataset", help="Dataset to use as training set"
    ),
    test_dataset: Optional[str] = typer.Option(
        None, "--test-dataset", help="Optional test dataset"
    ),
    redo_optimization: bool = typer.Option(
        True,
        "--redo-optimization/--no-redo-optimization",
        help="Redo hyperparameter optimization on full train set",
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Deploy a trained model from the lab to the flow.

    Creates a saved model and training recipe in the project flow.
    Returns the saved model ID and training recipe name.
    """
    project_key = resolve_project(project)
    output = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        mltask = proj.get_ml_task(analysis_id, mltask_id)
        result = mltask.deploy_to_flow(
            model_id,
            name,
            train_dataset,
            test_dataset=test_dataset,
            redo_optimization=redo_optimization,
        )
        render_raw(result, output)
        sm_id = result.get("savedModelId", "")
        success(f"Deployed to flow. Saved model: {sm_id}")
    except Exception as e:
        if "non-DONE model" in str(e):
            exit_with_error(
                f"Model '{model_id}' is not in DONE state and cannot be deployed.",
                details=[
                    f"Check model states: dku ml models {analysis_id} {mltask_id} -P {project_key} (look for STATE=DONE)",
                    "If training failed silently, try retraining: dku ml train "
                    + analysis_id
                    + " "
                    + mltask_id
                    + " -P "
                    + (project_key or "PROJ"),
                    "If the model trained on a small dataset, XGBoost/GBT may fail — try RANDOM_FOREST_REGRESSION or RIDGE_REGRESSION",
                    "Deploy workaround: dku ml deploy ... --no-redo-optimization (skips optimization on full train set)",
                ],
            )
        handle_api_error(e)


@app.command()
def redeploy(
    ctx: typer.Context,
    analysis_id: str = typer.Argument(help="Analysis ID"),
    mltask_id: str = typer.Argument(help="ML task ID"),
    model_id: str = typer.Argument(help="Trained model ID"),
    saved_model_id: Optional[str] = typer.Option(
        None, "--saved-model-id", help="Existing saved model ID to update"
    ),
    recipe_name: Optional[str] = typer.Option(
        None, "--recipe-name", help="Existing training recipe name to update"
    ),
    activate: bool = typer.Option(
        True,
        "--activate/--no-activate",
        help="Make the new version active (default: yes)",
    ),
    redo_optimization: bool = typer.Option(
        False,
        "--redo-optimization/--no-redo-optimization",
        help="Redo hyperparameter optimization",
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Redeploy a trained model to an existing saved model in the flow.

    Either --saved-model-id or --recipe-name must be provided.
    """
    project_key = resolve_project(project)
    output = resolve_output_format(output)

    if saved_model_id is None and recipe_name is None:
        exit_with_error(
            "Either --saved-model-id or --recipe-name is required.",
            details=[
                "Use --saved-model-id to update an existing saved model.",
                "Use --recipe-name to update the training recipe.",
            ],
        )

    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        mltask = proj.get_ml_task(analysis_id, mltask_id)
        result = mltask.redeploy_to_flow(
            model_id,
            recipe_name=recipe_name,
            saved_model_id=saved_model_id,
            activate=activate,
            redo_optimization=redo_optimization,
        )
        render_raw(result, output)
        success("Redeployed to flow.")
        if recipe_name:
            _warn_if_training_recipe_input_stale(
                proj, analysis_id, recipe_name, project_key
            )
    except SystemExit:
        raise
    except Exception as e:
        handle_api_error(e)


def _warn_if_training_recipe_input_stale(
    proj, analysis_id: str, recipe_name: str, project_key: str
) -> None:
    """Warn when the training recipe's input differs from the analysis input.

    redeploy_to_flow swaps the saved-model version but does NOT repoint the
    training recipe's input (the SDK posts no dataset param — verified
    dataikuapi behavior). If the analysis was trained on a different dataset,
    a later flow rebuild of the saved model silently retrains on the OLD
    data. Advisory only — never fails the redeploy.
    """
    try:
        definition = proj.get_analysis(analysis_id).get_definition()
        raw = definition.get_raw() if hasattr(definition, "get_raw") else definition
        analysis_input = (
            raw.get("inputDatasetSmartName") or raw.get("inputDataset") or ""
        )
        settings = proj.get_recipe(recipe_name).get_settings()
        items = (settings.get_recipe_inputs() or {}).get("main", {}).get("items", [])
        recipe_input = items[0].get("ref", "") if items else ""
        if analysis_input and recipe_input and analysis_input != recipe_input:
            warn(
                f"Training recipe '{recipe_name}' still reads '{recipe_input}', "
                f"but this model was trained on '{analysis_input}'. A flow "
                "rebuild of the saved model would retrain on the OLD dataset."
            )
            info(
                f"Fix: dku recipe replace-input {recipe_name} {recipe_input} "
                f"{analysis_input} -P {project_key}  (or use 'dku ml deploy' "
                "to create a fresh training recipe)"
            )
    except Exception:
        pass  # best-effort advisory; the redeploy itself already succeeded


# ---------------------------------------------------------------------------
# Settings / algorithm management
# ---------------------------------------------------------------------------


@app.command()
def settings(
    ctx: typer.Context,
    analysis_id: str = typer.Argument(help="Analysis ID"),
    mltask_id: str = typer.Argument(help="ML task ID"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Show ML task settings (algorithms, features, validation).

    Returns the full settings as JSON.
    """
    project_key = resolve_project(project)
    resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        mltask = proj.get_ml_task(analysis_id, mltask_id)
        raw = mltask.get_settings().get_raw()
        print(json.dumps(raw, indent=2, default=str))
    except Exception as e:
        handle_api_error(e)


@app.command()
def algorithms(
    ctx: typer.Context,
    analysis_id: str = typer.Argument(help="Analysis ID"),
    mltask_id: str = typer.Argument(help="ML task ID"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """List available algorithms and which are enabled."""
    project_key = resolve_project(project)
    output = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        mltask = proj.get_ml_task(analysis_id, mltask_id)
        task_settings = mltask.get_settings()

        all_algos = task_settings.get_all_possible_algorithm_names()
        enabled = set(task_settings.get_enabled_algorithm_names())

        data = [{"name": a, "enabled": str(a in enabled)} for a in sorted(all_algos)]

        render(
            data,
            ["name", "enabled"],
            output_format=output,
            title=f"Algorithms ({mltask_id})",
        )
    except Exception as e:
        handle_api_error(e)


@app.command("set-algorithm")
def set_algorithm(
    ctx: typer.Context,
    analysis_id: str = typer.Argument(help="Analysis ID"),
    mltask_id: str = typer.Argument(help="ML task ID"),
    enable: Optional[List[str]] = typer.Option(
        None, "--enable", help="Algorithm(s) to enable (repeatable)"
    ),
    disable: Optional[List[str]] = typer.Option(
        None, "--disable", help="Algorithm(s) to disable (repeatable)"
    ),
    disable_all: bool = typer.Option(
        False, "--disable-all", help="Disable all algorithms first"
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Enable or disable algorithms for an ML task.

    Use --disable-all then --enable to select only specific algorithms.
    Use 'dku ml algorithms' to see available algorithm names.
    """
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        mltask = proj.get_ml_task(analysis_id, mltask_id)
        task_settings = mltask.get_settings()

        # Multi-algo footgun: agents who pass `--enable LOGISTIC_REGRESSION`
        # to "lock to one algorithm" silently end up training Random Forest
        # alongside it because DSS leaves RF enabled by default. The fix is
        # always to pair `--disable-all` with `--enable X` — warn loudly
        # when the user forgot, so they catch it before training.
        if enable and not disable_all:
            from dku_cli.output import warn

            warn(
                "Default-enabled algorithms (typically Random Forest) will train "
                "alongside the one(s) you just enabled — DSS does NOT auto-disable "
                "the rest. To lock to a single algorithm, re-run with --disable-all:"
            )
            warn(
                f"  dku ml set-algorithm {analysis_id} {mltask_id} "
                f"--disable-all {' '.join(f'--enable {a}' for a in enable)} -P {project_key}"
            )

        if disable_all:
            task_settings.disable_all_algorithms()

        for alg in disable or []:
            task_settings.set_algorithm_enabled(alg, False)

        for alg in enable or []:
            task_settings.set_algorithm_enabled(alg, True)

        task_settings.save()
        success("Algorithm settings updated.")
    except Exception as e:
        handle_api_error(e)


@app.command("set-feature")
def set_feature(
    ctx: typer.Context,
    analysis_id: str = typer.Argument(help="Analysis ID"),
    mltask_id: str = typer.Argument(help="ML task ID"),
    feature: str = typer.Argument(help="Feature (column) name"),
    role: FeatureRole = typer.Option(
        ...,
        "--role",
        case_sensitive=False,
        help="INPUT | REJECT | TARGET (prediction only) | WEIGHT (prediction only)",
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Change the role of a feature in an ML task (e.g. reject a leaky column).

    After create-prediction / create-clustering, DSS auto-guesses feature roles.
    Use this to reject columns that leak the target (labels, post-event columns)
    without rebuilding the upstream dataset.

    Example:
      dku ml set-feature ml_analysis_1 mltask_1 true_label --role REJECT -P PROJ
    """
    role_upper = role.value
    # DSS stores rejected role as "REJECT" internally.
    if role_upper == "REJECTED":
        role_upper = "REJECT"
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        mltask = proj.get_ml_task(analysis_id, mltask_id)
        task_settings = mltask.get_settings()
        try:
            feat = task_settings.get_feature_preprocessing(feature)
        except Exception:
            exit_with_error(
                f"Feature '{feature}' not found in ML task {mltask_id}.",
                code="not_found",
                details=[
                    f"Inspect features: dku ml settings {analysis_id} {mltask_id} -P {project_key} | jq '.preprocessing.per_feature | keys'",
                ],
                status=3,
            )
        feat["role"] = role_upper
        task_settings.save()
        success(f"Set feature '{feature}' role = {role_upper} in ML task {mltask_id}.")
    except Exception as e:
        handle_api_error(e)


def _feature_role_assignments(
    reject: Optional[str],
    input_features: Optional[str],
    target: Optional[str],
    weight: Optional[str],
) -> list[tuple[str, str]]:
    """Flatten the role flags into (feature, role) pairs (one comprehension)."""

    def _split(value: Optional[str]) -> list[str]:
        return [c.strip() for c in value.split(",") if c.strip()] if value else []

    role_lists = [
        (reject, "REJECT"),
        (input_features, "INPUT"),
        (target, "TARGET"),
        (weight, "WEIGHT"),
    ]
    return [(feat, role) for value, role in role_lists for feat in _split(value)]


@app.command("set-features")
def set_features(
    ctx: typer.Context,
    analysis_id: str = typer.Argument(help="Analysis ID"),
    mltask_id: str = typer.Argument(help="ML task ID"),
    reject: Optional[str] = typer.Option(
        None, "--reject", help="Comma-separated features to REJECT"
    ),
    input_features: Optional[str] = typer.Option(
        None, "--input", help="Comma-separated features to set as INPUT"
    ),
    target: Optional[str] = typer.Option(
        None, "--target", help="Feature to set as TARGET (prediction tasks only)"
    ),
    weight: Optional[str] = typer.Option(
        None, "--weight", help="Feature to set as WEIGHT (prediction tasks only)"
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Set multiple feature roles in ONE transactional write.

    Prefer this over a loop of `set-feature` calls. Each `set-feature` does a full
    get-settings -> modify -> save round-trip; firing many in quick succession
    races (a later save clobbers earlier ones, so some rejects silently don't
    stick — exactly the trap that trains a model on columns you meant to drop).
    `set-features` reads the settings once, applies every change, and saves once.

    Validates that all named features exist BEFORE saving, so a typo aborts the
    whole call rather than half-applying.

    Example:
      dku ml set-features A M --reject order_id --input quantity,price -P PROJ
    """
    project_key = resolve_project(project)
    assignments = _feature_role_assignments(reject, input_features, target, weight)

    if not assignments:
        exit_with_error(
            "No feature roles given. Provide at least one of "
            "--reject / --input / --target / --weight.",
            code="invalid_param",
            details=[
                "Example: dku ml set-features A M --reject id --input age -P PROJ",
            ],
        )

    try:
        client = get_client_from_ctx(ctx)
        mltask = client.get_project(project_key).get_ml_task(analysis_id, mltask_id)
        task_settings = mltask.get_settings()

        # Resolve every feature first; abort before saving if any is missing.
        resolved: list[tuple[dict, str, str]] = []
        missing: list[str] = []
        for feat, role in assignments:
            try:
                resolved.append(
                    (task_settings.get_feature_preprocessing(feat), role, feat)
                )
            except Exception:  # noqa: BLE001
                missing.append(feat)
        if missing:
            settings_cmd = f"dku ml settings {analysis_id} {mltask_id} -P {project_key}"
            exit_with_error(
                f"Feature(s) not found in ML task {mltask_id}: {', '.join(missing)}.",
                code="not_found",
                details=[f"Inspect features: {settings_cmd} -o json"],
                status=3,
            )

        for feat_settings, role, _feat in resolved:
            feat_settings["role"] = role
        task_settings.save()
        summary = ", ".join(f"{feat}={role}" for _, role, feat in resolved)
        success(
            f"Set {len(resolved)} feature role(s) in ML task {mltask_id}: {summary}"
        )
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------


@app.command()
def delete(
    ctx: typer.Context,
    analysis_id: str = typer.Argument(help="Analysis ID"),
    mltask_id: str = typer.Argument(help="ML task ID"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip safety guard"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Delete an ML task."""
    from dku_cli.safety import Tier, guard

    project_key = resolve_project(project)
    guard(
        ctx,
        tier=Tier.DELETE,
        action="ml.delete",
        subject=f"ML task '{mltask_id}' (analysis '{analysis_id}') in {project_key}",
        yes=yes,
        prompt=f"Delete ML task '{mltask_id}' in analysis '{analysis_id}' from {project_key}?",
    )
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        mltask = proj.get_ml_task(analysis_id, mltask_id)
        mltask.delete()
        success(f"Deleted ML task {mltask_id}")
    except Exception as e:
        handle_api_error(e)
