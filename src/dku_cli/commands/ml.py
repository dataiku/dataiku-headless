"""dku ml — create, train, deploy, and manage ML tasks."""

from __future__ import annotations

import json
from typing import List, Optional

import typer

from dku_cli.errors import exit_with_error, handle_api_error
from dku_cli.helpers import get_client_from_ctx, resolve_project
from dku_cli.output import render, render_raw, resolve_output_format, success

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
        tasks = proj.list_ml_tasks()

        data = []
        for t in tasks:
            data.append(
                {
                    "analysis_id": t.get("analysisId", ""),
                    "mltask_id": t.get("mlTaskId", ""),
                    "type": t.get("taskType", ""),
                    "target": t.get("targetVariable", ""),
                }
            )

        render(
            data,
            ["analysis_id", "mltask_id", "type", "target"],
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
    """List trained models in an ML task."""
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
            data.append(
                {
                    "model_id": mid,
                    "algorithm": snippet.get("algorithm", ""),
                    "session": snippet.get("sessionId", ""),
                }
            )

        render(
            data,
            ["model_id", "algorithm", "session"],
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
    except SystemExit:
        raise
    except Exception as e:
        handle_api_error(e)


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

        data = [
            {"algorithm": a, "enabled": str(a in enabled)} for a in sorted(all_algos)
        ]

        render(
            data,
            ["algorithm", "enabled"],
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


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------


@app.command()
def delete(
    ctx: typer.Context,
    analysis_id: str = typer.Argument(help="Analysis ID"),
    mltask_id: str = typer.Argument(help="ML task ID"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Delete an ML task."""
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        mltask = proj.get_ml_task(analysis_id, mltask_id)
        mltask.delete()
        success(f"Deleted ML task {mltask_id}")
    except Exception as e:
        handle_api_error(e)
