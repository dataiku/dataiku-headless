"""dku model — list, get, versions, set-active-version, metrics, delete-version, delete, usages, set-metadata, create-mlflow, import-mlflow, create-external."""

from __future__ import annotations

import json
from typing import List

import typer

from dku_cli.enums import (
    CrossProjectBuildBehavior,
    PredictionType,
    PublishPolicy,
    RebuildBehavior,
)
from dku_cli.errors import exit_with_error, handle_api_error, is_not_found_error
from dku_cli.helpers import (
    get_client_from_ctx,
    read_json_input,
    resolve_project,
    update_taggable_metadata,
)
from dku_cli.output import (
    error,
    info,
    render,
    render_raw,
    resolve_output_format,
    success,
)

app = typer.Typer(help="Manage DSS saved models.")


@app.command("list")
def list_models(
    ctx: typer.Context,
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """List saved models in a project."""
    project_key = resolve_project(project)
    output = resolve_output_format()
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        models = proj.list_saved_models()

        data = []
        for m in models:
            data.append(
                {
                    "id": m.get("id", ""),
                    "name": m.get("name", ""),
                    "type": m.get("type", ""),
                }
            )

        render(
            data,
            ["id", "name", "type"],
            output_format=output,
            title=f"Saved Models ({project_key})",
        )
    except Exception as e:
        handle_api_error(e)


@app.command()
def get(
    ctx: typer.Context,
    model_id: str = typer.Argument(help="Saved model ID"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Show saved model details."""
    project_key = resolve_project(project)
    output = resolve_output_format()
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        model = proj.get_saved_model(model_id)
        settings = model.get_settings()
        raw = settings.get_raw()
        active = model.get_active_version()

        # Saved-model settings raw dict has no top-level "type"; pull it from the project list.
        model_type = raw.get("type") or ""
        if not model_type:
            for m in proj.list_saved_models():
                if m.get("id") == model_id:
                    model_type = m.get("type", "")
                    break

        # Surface ML-specific structure when present so `model get` is
        # informative for PREDICTION/CLUSTERING/TIMESERIES_FORECAST without
        # forcing the caller to fall back to `get-definition`.
        prediction_type = raw.get("predictionType") or ""
        algorithm = raw.get("miniTask", {}).get("modeling", {}).get("algorithm") or ""

        if output == "json":
            detail = {
                "id": model_id,
                "name": raw.get("name", ""),
                "type": model_type,
                "active_version": active.get("id", "") if active else None,
            }
            if prediction_type:
                detail["prediction_type"] = prediction_type
            if algorithm:
                detail["algorithm"] = algorithm
            print(json.dumps(detail, indent=2, default=str))
        else:
            data = [
                {"field": "ID", "value": model_id},
                {"field": "Name", "value": raw.get("name", "")},
                {"field": "Type", "value": model_type},
                {
                    "field": "Active version",
                    "value": active.get("id", "") if active else "(none)",
                },
            ]
            if prediction_type:
                data.append({"field": "Prediction type", "value": prediction_type})
            if algorithm:
                data.append({"field": "Algorithm", "value": algorithm})
            render(
                data,
                ["field", "value"],
                output_format=output,
                title=f"Model: {model_id}",
            )
    except Exception as e:
        handle_api_error(e)


@app.command("get-definition")
def get_definition(
    ctx: typer.Context,
    model_id: str = typer.Argument(help="Saved model ID"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Get the full saved-model settings as JSON.

    Returns the raw settings dict (miniTask, prediction type, metrics config, etc.).
    Use this to inspect or template a model's training/scoring configuration.
    """
    project_key = resolve_project(project)
    output = resolve_output_format()
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        model = proj.get_saved_model(model_id)
        raw = model.get_settings().get_raw()
        render_raw(raw, output_format=output)
    except Exception as e:
        if is_not_found_error(e):
            exit_with_error(
                f"Saved model '{model_id}' not found in {project_key}.",
                status=3,
                details=[
                    f"List models: dku model list -P {project_key}",
                ],
            )
        handle_api_error(e)


@app.command("set-definition")
def set_definition(
    ctx: typer.Context,
    model_id: str = typer.Argument(help="Saved model ID"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    definition: str = typer.Option(
        ...,
        "--definition",
        "-d",
        help="Definition JSON (string, @file.json, or '-' for stdin)",
    ),
) -> None:
    """Replace the saved-model settings from JSON.

    Always GET → edit → SET. Pass the full settings dict; this is a full
    replace, not a merge.
    """
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        model = proj.get_saved_model(model_id)
        new_def = read_json_input(definition)
        settings = model.get_settings()
        settings.settings.clear()
        settings.settings.update(new_def)
        settings.save()
        success(f"Updated definition for saved model '{model_id}'")
    except Exception as e:
        if is_not_found_error(e):
            exit_with_error(
                f"Saved model '{model_id}' not found in {project_key}.",
                status=3,
                details=[
                    f"List models: dku model list -P {project_key}",
                ],
            )
        handle_api_error(e)


@app.command()
def versions(
    ctx: typer.Context,
    model_id: str = typer.Argument(help="Saved model ID"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """List versions of a saved model."""
    project_key = resolve_project(project)
    output = resolve_output_format()
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        model = proj.get_saved_model(model_id)
        vers = model.list_versions()

        data = []
        for v in vers:
            data.append(
                {
                    "id": v.get("id", ""),
                    "active": str(v.get("active", False)),
                    "algorithm": v.get("snippet", {}).get("algorithm", ""),
                }
            )

        render(
            data,
            ["id", "active", "algorithm"],
            output_format=output,
            title=f"Model Versions: {model_id}",
        )
    except Exception as e:
        handle_api_error(e)


@app.command("set-flow-options")
def set_flow_options(
    ctx: typer.Context,
    model_id: str = typer.Argument(help="Saved model ID"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    virtualizable: bool | None = typer.Option(
        None,
        "--virtualizable/--no-virtualizable",
        help="Allow this model to be virtualized in downstream flow zones (settings.flowOptions.virtualizable).",
    ),
    rebuild_behavior: RebuildBehavior | None = typer.Option(
        None,
        "--rebuild-behavior",
        case_sensitive=False,
        help=f"Rebuild behavior: {', '.join(m.value for m in RebuildBehavior)}. Sets settings.flowOptions.rebuildBehavior.",
    ),
    cross_project_build_behavior: CrossProjectBuildBehavior | None = typer.Option(
        None,
        "--cross-project-build-behavior",
        case_sensitive=False,
        help=f"Cross-project rebuild: {', '.join(m.value for m in CrossProjectBuildBehavior)}. Sets settings.flowOptions.crossProjectBuildBehavior.",
    ),
    ignore_error_status_on_build: bool | None = typer.Option(
        None,
        "--ignore-error-status-on-build/--respect-error-status-on-build",
        help="settings.flowOptions.ignoreErrorStatusOnBuild — when true, builds proceed even if upstream is in ERROR.",
    ),
) -> None:
    """Patch a saved model's flow options (virtualizable, rebuild behavior, ...).

    Reads → patches → writes the saved-model settings. Lets you avoid hand-rolling
    raw `dataikuapi.DSSSavedModelSettings.save()` from Python for these knobs.

    Example:
        dku model set-flow-options 7bdMB26q --virtualizable \\
            --rebuild-behavior NORMAL --ignore-error-status-on-build -P PROJ
    """
    if (
        virtualizable is None
        and rebuild_behavior is None
        and cross_project_build_behavior is None
        and ignore_error_status_on_build is None
    ):
        exit_with_error(
            "Pass at least one flow-option flag.",
            details=[
                "Examples: --virtualizable, --rebuild-behavior NORMAL, --cross-project-build-behavior DEFAULT"
            ],
        )

    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        model = proj.get_saved_model(model_id)
        settings = model.get_settings()
        raw = settings.get_raw()
        flow = raw.setdefault("flowOptions", {})
        if virtualizable is not None:
            flow["virtualizable"] = bool(virtualizable)
        if rebuild_behavior is not None:
            flow["rebuildBehavior"] = rebuild_behavior.value
        if cross_project_build_behavior is not None:
            flow["crossProjectBuildBehavior"] = cross_project_build_behavior.value
        if ignore_error_status_on_build is not None:
            flow["ignoreErrorStatusOnBuild"] = bool(ignore_error_status_on_build)
        settings.save()
        success(f"Updated flowOptions on saved model '{model_id}'")
    except Exception as e:
        if is_not_found_error(e):
            exit_with_error(
                f"Saved model '{model_id}' not found in {project_key}.",
                status=3,
                details=[f"List models: dku model list -P {project_key}"],
            )
        handle_api_error(e)


@app.command("set-publish-policy")
def set_publish_policy(
    ctx: typer.Context,
    model_id: str = typer.Argument(help="Saved model ID"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    policy: PublishPolicy = typer.Option(
        ...,
        "--policy",
        case_sensitive=False,
        help=f"Publish policy: {', '.join(m.value for m in PublishPolicy)}. Sets settings.publishPolicy.",
    ),
) -> None:
    """Set the publish policy on a saved model.

    UNCONDITIONAL = newly-trained versions become active immediately.
    CONDITIONAL  = only when newer version beats current on chosen metric.
    EXPLICIT     = no auto-activation; manual `set-active-version` only.
    """
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        model = proj.get_saved_model(model_id)
        settings = model.get_settings()
        raw = settings.get_raw()
        raw["publishPolicy"] = policy.value
        settings.save()
        success(f"Set publishPolicy={policy.value} on saved model '{model_id}'")
    except Exception as e:
        if is_not_found_error(e):
            exit_with_error(
                f"Saved model '{model_id}' not found in {project_key}.",
                status=3,
                details=[f"List models: dku model list -P {project_key}"],
            )
        handle_api_error(e)


@app.command("diagnostics")
def diagnostics(
    ctx: typer.Context,
    model_id: str = typer.Argument(help="Saved model ID"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    list_only: bool = typer.Option(
        False,
        "--list",
        help="List configured diagnostics with their enabled status (no mutation).",
    ),
    enable: list[str] | None = typer.Option(
        None,
        "--enable",
        help="Diagnostic key to enable (repeatable). Sets matching entry's enabled=true.",
    ),
    disable: list[str] | None = typer.Option(
        None,
        "--disable",
        help="Diagnostic key to disable (repeatable). Sets matching entry's enabled=false.",
    ),
) -> None:
    """List, enable, or disable model-level diagnostics.

    Diagnostics live at settings.miniTask.diagnosticsSettings.diagnostics[].
    Each entry has {type, enabled} where type is the diagnostic key (e.g.
    LEAKAGE_DETECTION, OVERFITTING_DETECTION).

    Example — list:
        dku model diagnostics 7bdMB26q --list -P PROJ
    Example — toggle:
        dku model diagnostics 7bdMB26q --enable LEAKAGE_DETECTION --disable OVERFITTING_DETECTION -P PROJ
    """
    if not (list_only or enable or disable):
        exit_with_error(
            "Pass --list, --enable, or --disable.",
        )
    project_key = resolve_project(project)
    output = resolve_output_format()
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        model = proj.get_saved_model(model_id)
        settings = model.get_settings()
        raw = settings.get_raw()
        mini = raw.get("miniTask", {})
        diag_settings = mini.setdefault("diagnosticsSettings", {})
        diags = diag_settings.setdefault("diagnostics", [])

        if list_only:
            data = [
                {"type": d.get("type", ""), "enabled": str(d.get("enabled", False))}
                for d in diags
            ]
            render(
                data,
                ["type", "enabled"],
                output_format=output,
                title=f"Diagnostics: {model_id}",
            )
            return

        # Apply --enable / --disable mutations
        diag_by_type = {d.get("type"): d for d in diags}
        for t in enable or []:
            if t in diag_by_type:
                diag_by_type[t]["enabled"] = True
            else:
                diags.append({"type": t, "enabled": True})
                diag_by_type[t] = diags[-1]
        for t in disable or []:
            if t in diag_by_type:
                diag_by_type[t]["enabled"] = False
            else:
                diags.append({"type": t, "enabled": False})
                diag_by_type[t] = diags[-1]
        settings.save()
        success(f"Updated diagnostics on saved model '{model_id}'")
    except Exception as e:
        if is_not_found_error(e):
            exit_with_error(
                f"Saved model '{model_id}' not found in {project_key}.",
                status=3,
                details=[f"List models: dku model list -P {project_key}"],
            )
        handle_api_error(e)


@app.command("set-active-version")
def set_active_version(
    ctx: typer.Context,
    model_id: str = typer.Argument(help="Saved model ID"),
    version_id: str = typer.Argument(help="Version ID to activate"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Set the active version of a saved model.

    After activation, downstream prediction recipes and API endpoints use this version.
    Use 'dku model versions MODEL_ID' to see available version IDs.
    """
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        model = proj.get_saved_model(model_id)
        model.set_active_version(version_id)
        success(f"Activated version {version_id} on model {model_id}")
    except Exception as e:
        if is_not_found_error(e):
            exit_with_error(
                "Version or model not found.",
                details=[
                    f"List available versions: dku model versions {model_id} -P {project_key}",
                ],
                status=3,
            )
        handle_api_error(e)


@app.command()
def metrics(
    ctx: typer.Context,
    model_id: str = typer.Argument(help="Saved model ID"),
    version_id: str = typer.Option(
        None, "--version", "-v", help="Version ID (default: active version)"
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Show performance metrics for a model version.

    Defaults to the active version. Use --version to inspect a specific one.
    Returns metrics like AUC, accuracy, precision, recall, F1, RMSE, MAE
    depending on model type.
    """
    project_key = resolve_project(project)
    output = resolve_output_format()
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        model = proj.get_saved_model(model_id)

        if version_id is None:
            active = model.get_active_version()
            if active is None:
                exit_with_error(
                    "No active version on this model.",
                    details=[
                        f"List versions: dku model versions {model_id} -P {project_key}",
                        f"Activate one: dku model set-active-version {model_id} VERSION_ID -P {project_key}",
                    ],
                )
            version_id = active["id"]

        details = model.get_version_details(version_id)
        perf = details.get_performance_metrics()

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
                title=f"Metrics: {model_id} (version {version_id})",
            )
    except SystemExit:
        raise
    except Exception as e:
        if is_not_found_error(e):
            exit_with_error(
                "Model or version not found.",
                details=[
                    f"List versions: dku model versions {model_id} -P {project_key}",
                ],
                status=3,
            )
        handle_api_error(e)


@app.command("delete-version")
def delete_version(
    ctx: typer.Context,
    model_id: str = typer.Argument(help="Saved model ID"),
    version: List[str] = typer.Option(
        ..., "--version", "-v", help="Version ID(s) to delete (repeatable)"
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip safety guard"),
) -> None:
    """Delete one or more versions from a saved model.

    Pass --version multiple times to delete several at once.
    Use 'dku model versions MODEL_ID' to see available version IDs.
    """
    from dku_cli.safety import Tier, guard

    project_key = resolve_project(project)
    version_list = list(version)
    guard(
        ctx,
        tier=Tier.DELETE,
        action="model.delete_version",
        subject=f"{len(version_list)} version(s) of model '{model_id}' in {project_key}",
        yes=yes,
        prompt=f"Delete {len(version_list)} version(s) from saved model '{model_id}'?",
    )
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        model = proj.get_saved_model(model_id)
        model.delete_versions(version_list)
        success(f"Deleted {len(version_list)} version(s) from model {model_id}")
    except typer.Exit:
        raise
    except Exception as e:
        if is_not_found_error(e):
            exit_with_error(
                "Model or version not found.",
                details=[
                    f"List versions: dku model versions {model_id} -P {project_key}",
                ],
                status=3,
            )
        handle_api_error(e)


@app.command()
def delete(
    ctx: typer.Context,
    model_id: str = typer.Argument(help="Saved model ID"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip safety guard"),
) -> None:
    """Delete a saved model.

    Use 'dku model list' to see available model IDs.
    """
    from dku_cli.safety import Tier, guard

    project_key = resolve_project(project)
    guard(
        ctx,
        tier=Tier.DELETE,
        action="model.delete",
        subject=f"saved model '{model_id}' in {project_key}",
        yes=yes,
        prompt=f"Delete saved model '{model_id}' from {project_key}?",
    )
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        sm = proj.get_saved_model(model_id)
        sm.delete()
        success(f"Deleted saved model '{model_id}'")
    except typer.Exit:
        raise
    except Exception as e:
        if is_not_found_error(e):
            exit_with_error(
                f"Model '{model_id}' not found.",
                details=[
                    f"List models: dku model list -P {project_key}",
                ],
                status=3,
            )
        handle_api_error(e)


@app.command()
def usages(
    ctx: typer.Context,
    model_id: str = typer.Argument(help="Saved model ID"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Show where a saved model is used (recipes, endpoints, etc.)."""
    project_key = resolve_project(project)
    output = resolve_output_format()
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        sm = proj.get_saved_model(model_id)
        usage_list = sm.get_usages()
        render_raw(usage_list, output_format=output)
    except Exception as e:
        if is_not_found_error(e):
            exit_with_error(
                f"Model '{model_id}' not found.",
                details=[
                    f"List models: dku model list -P {project_key}",
                ],
                status=3,
            )
        handle_api_error(e)


@app.command("set-metadata")
def set_metadata(
    ctx: typer.Context,
    model_id: str = typer.Argument(help="Saved model ID"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    description: str | None = typer.Option(
        None, "--description", "-d", help="Model description"
    ),
    short_desc: str | None = typer.Option(
        None, "--short-desc", help="Short description"
    ),
    tags: str | None = typer.Option(
        None, "--tags", help="Comma-separated tags (replaces existing)"
    ),
) -> None:
    """Update saved model description, short description, and/or tags.

    No JSON needed — updates metadata fields directly.
    """
    if description is None and short_desc is None and tags is None:
        error("Provide --description, --short-desc, and/or --tags to update.")
        raise typer.Exit(1)
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        model = proj.get_saved_model(model_id)
        settings = model.get_settings()
        update_taggable_metadata(settings, description, short_desc, tags)
        success(f"Updated metadata for model '{model_id}'")
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command("create-mlflow")
def create_mlflow(
    ctx: typer.Context,
    name: str = typer.Argument(help="Name for the MLflow saved model"),
    prediction_type: PredictionType | None = typer.Option(
        None,
        "--prediction-type",
        "-t",
        case_sensitive=False,
        help="BINARY_CLASSIFICATION, MULTICLASS, or REGRESSION (optional)",
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Create a saved model for storing MLflow pyfunc models.

    After creation, import a model version with 'dku model import-mlflow'.

    Example:
      dku model create-mlflow "Churn Model" -t BINARY_CLASSIFICATION -P PROJ
      dku model create-mlflow "Custom Model" -P PROJ
    """
    project_key = resolve_project(project)
    fmt = resolve_output_format()
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        model = proj.create_mlflow_pyfunc_model(name, prediction_type=prediction_type)

        if fmt == "json":
            render_raw(
                {"id": model.sm_id, "name": name, "project": project_key},
                output_format="json",
            )
        else:
            success(
                f"Created MLflow model '{name}' (ID: {model.sm_id}) in {project_key}"
            )
            info(
                f"Import a version: dku model import-mlflow {model.sm_id} "
                f"--version-id v1 --path /path/to/mlflow/model -P {project_key}"
            )
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command("import-mlflow")
def import_mlflow(
    ctx: typer.Context,
    model_id: str = typer.Argument(help="Saved model ID"),
    version_id: str = typer.Option(
        ..., "--version-id", "-v", help="Version identifier for the import"
    ),
    path: str = typer.Option(..., "--path", help="Local path to MLflow model folder"),
    code_env: str = typer.Option(
        "LOCAL-CODE-ENV",
        "--code-env",
        help="Code env name (default: active env, or 'INHERIT' for project default)",
    ),
    set_active: bool = typer.Option(
        True, "--set-active/--no-set-active", help="Set as active version"
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Import a MLflow model version from a local path.

    The saved model must have been created with 'dku model create-mlflow'.
    The path must contain a valid MLflow model (MLmodel file + artifacts).

    Example:
      dku model import-mlflow MODEL_ID -v v1 --path ./mlflow_model -P PROJ
    """
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        model = proj.get_saved_model(model_id)
        model.import_mlflow_version_from_path(
            version_id,
            path,
            code_env_name=code_env,
            set_active=set_active,
        )
        success(f"Imported MLflow version '{version_id}' into model '{model_id}'")
        if set_active:
            info(f"Version '{version_id}' set as active")
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command("create-external")
def create_external(
    ctx: typer.Context,
    name: str = typer.Argument(help="Name for the external model"),
    prediction_type: PredictionType = typer.Option(
        ...,
        "--prediction-type",
        "-t",
        case_sensitive=False,
        help="BINARY_CLASSIFICATION, MULTICLASS, or REGRESSION",
    ),
    protocol: str = typer.Option(
        ...,
        "--protocol",
        help="Provider protocol: sagemaker, databricks, azure-ml, vertex-ai",
    ),
    connection: str | None = typer.Option(
        None, "--connection", "-c", help="DSS connection for authentication"
    ),
    region: str | None = typer.Option(
        None, "--region", help="Cloud region (required for sagemaker, vertex-ai)"
    ),
    config: str | None = typer.Option(
        None,
        "--config",
        help="Full configuration JSON (overrides --protocol/--connection/--region)",
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Create a saved model for external remote endpoints (SageMaker, Databricks, etc).

    Example:
      dku model create-external "SageMaker Model" -t BINARY_CLASSIFICATION \\
        --protocol sagemaker --region eu-west-1 -P PROJ
      dku model create-external "Vertex Model" -t REGRESSION \\
        --protocol vertex-ai --region europe-west1 --connection vertex_conn -P PROJ
    """
    project_key = resolve_project(project)
    fmt = resolve_output_format()
    try:
        if config:
            configuration = read_json_input(config)
        else:
            configuration = {"protocol": protocol}
            if connection:
                configuration["connection"] = connection
            if region:
                configuration["region"] = region

        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        model = proj.create_external_model(name, prediction_type, configuration)

        if fmt == "json":
            render_raw(
                {"id": model.sm_id, "name": name, "project": project_key},
                output_format="json",
            )
        else:
            success(
                f"Created external model '{name}' (ID: {model.sm_id}) in {project_key}"
            )
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)
