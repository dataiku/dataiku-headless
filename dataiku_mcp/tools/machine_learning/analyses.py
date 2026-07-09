"""Generic ML analysis and trained-model inspection tools."""

from __future__ import annotations

from typing import Any

from fastmcp import Context

from ... import mcp
from ..utils.async_executor import run_blocking
from ..utils.serialization import columnar, compact_json, omit_empty
from ..utils.auth import get_dss_client
from ..utils.validation import require_non_empty_string as _require_non_empty_string
from .shared.common import (
    find_analysis_input_dataset,
    require_single_ml_task,
)
from .shared.summaries import build_ml_task_summary
from .shared.training import train_models


def get_single_task_bundle(project_key: str, analysis_id: str):
    project = get_dss_client().get_project(project_key)
    analysis = project.get_analysis(analysis_id)
    task_ref = require_single_ml_task(analysis)
    mltask_id = task_ref["mlTaskId"]
    mltask = analysis.get_ml_task(mltask_id)
    return project, analysis, mltask_id, mltask


def slim_model_data(data: Any) -> Any:
    """Recursively strip *PerFeature arrays and other large per-feature metric blobs."""
    if isinstance(data, dict):
        return {
            key: slim_model_data(value)
            for key, value in data.items()
            if not key.endswith("PerFeature")
        }
    if isinstance(data, list):
        return [slim_model_data(item) for item in data]
    return data


def slim_mltask_settings(raw_settings: dict) -> dict:
    """Return mltask settings with disabled algorithm entries removed from modeling."""
    slimmed = dict(raw_settings)
    modeling = slimmed.get("modeling")
    if isinstance(modeling, dict):
        slimmed["modeling"] = {
            key: value
            for key, value in modeling.items()
            if not (
                isinstance(value, dict)
                and "enabled" in value
                and not value["enabled"]
            )
        }
    return slimmed


@mcp.tool()
async def list_ml_analyses(
    project_key: str,
    ctx: Context,
    input_dataset: str | None = None,
) -> str:
    """List the ML analyses in the project with their single-task summaries.

    Args:
        input_dataset: Optional dataset filter
    """
    project_key = _require_non_empty_string(project_key, "project_key")
    if input_dataset is not None:
        input_dataset = _require_non_empty_string(input_dataset, "input_dataset")

    await ctx.info(f"Listing ML analyses in {project_key}...")

    def _list() -> dict[str, Any]:
        project = get_dss_client().get_project(project_key)
        analyses = []
        for analysis_item in project.list_analyses():
            if input_dataset and analysis_item.get("inputDataset") != input_dataset:
                continue

            analysis_id = analysis_item["analysisId"]
            analysis = project.get_analysis(analysis_id)
            analysis_definition = analysis.get_definition().get_raw()
            task_ref = require_single_ml_task(analysis)
            mltask_id = task_ref["mlTaskId"]
            mltask = analysis.get_ml_task(mltask_id)
            settings = mltask.get_settings()

            analyses.append(
                build_ml_task_summary(
                    project_key=project_key,
                    analysis_id=analysis_id,
                    analysis_name=analysis_definition.get("name"),
                    input_dataset=analysis_item.get("inputDataset"),
                    mltask_id=mltask_id,
                    mltask=mltask,
                    settings=settings,
                    include_feature_details=False,
                    include_trained_models=False,
                )
            )

        return {
            # project_key dropped (LEVER 3): top-level scalar was an exact echo of
            # the project_key argument; the per-row project_key column is likewise a
            # pure echo of the same argument on every iteration, so it is removed
            # from the columnar column list below.
            "analyses": columnar(
                analyses,
                [
                    "analysis_id",
                    "analysis_name",
                    "input_dataset",
                    "mltask_id",
                    "task_type",
                    "prediction_type",
                    "target_column",
                    "backend_type",
                    "metric",
                    "metric_details",
                    "enabled_algorithms",
                    "guessing",
                    "training",
                    "trained_model_count",
                    "split",
                    "hyperparameter_search",
                    "weighting",
                    "diagnostics",
                    "feature_role_counts",
                    "features",
                ],
            ),
        }

    return compact_json(await run_blocking(_list))


@mcp.tool()
async def get_ml_analysis_summary(
    project_key: str,
    analysis_id: str,
    ctx: Context,
) -> str:
    """Get the normalized single-task summary for an ML analysis.

    Args:
        analysis_id: Analysis ID from list_ml_analyses
    """
    project_key = _require_non_empty_string(project_key, "project_key")
    analysis_id = _require_non_empty_string(analysis_id, "analysis_id")

    await ctx.info(f"Loading ML analysis summary for {analysis_id}...")

    def _get() -> dict[str, Any]:
        project, analysis, mltask_id, mltask = get_single_task_bundle(
            project_key, analysis_id
        )
        analysis_definition = analysis.get_definition().get_raw()
        settings = mltask.get_settings()
        return build_ml_task_summary(
            project_key=project_key,
            analysis_id=analysis_id,
            analysis_name=analysis_definition.get("name"),
            input_dataset=find_analysis_input_dataset(project, analysis_id),
            mltask_id=mltask_id,
            mltask=mltask,
            settings=settings,
            include_feature_details=True,
            include_trained_models=False,
        )

    return compact_json(await run_blocking(_get))


@mcp.tool()
async def get_ml_analysis_settings(
    project_key: str,
    analysis_id: str,
    ctx: Context,
) -> str:
    """Get the raw analysis and ML task settings for an ML analysis.

    Args:
        analysis_id: Analysis ID from list_ml_analyses
    """
    project_key = _require_non_empty_string(project_key, "project_key")
    analysis_id = _require_non_empty_string(analysis_id, "analysis_id")

    await ctx.info(f"Loading ML analysis settings for {analysis_id}...")

    def _get() -> dict[str, Any]:
        project, analysis, mltask_id, mltask = get_single_task_bundle(
            project_key, analysis_id
        )
        analysis_definition = analysis.get_definition().get_raw()
        settings = mltask.get_settings()
        result = {
            # project_key / analysis_id dropped (LEVER 3): each is a pure echo of the
            # like-named argument (validator-only pass-through), so the caller already
            # has them. mltask_id is server-resolved from the analysis, not an input.
            "analysis_name": analysis_definition.get("name"),
            "input_dataset": find_analysis_input_dataset(project, analysis_id),
            "mltask_id": mltask_id,
            "mltask_settings": slim_mltask_settings(settings.get_raw()),
        }
        # LEVER 4: omit analysis_name / input_dataset when empty (None/""); absent
        # reads as empty. mltask_settings is a raw passthrough blob — left intact.
        return omit_empty(result)

    return compact_json(await run_blocking(_get))


@mcp.tool()
async def train_ml_analysis(
    project_key: str,
    analysis_id: str,
    ctx: Context,
    session_name: str | None = None,
    session_description: str | None = None,
    run_queue: bool = False,
) -> str:
    """Train the single ML task contained in an analysis.

    Args:
        analysis_id: Analysis ID from list_ml_analyses
    """
    project_key = _require_non_empty_string(project_key, "project_key")
    analysis_id = _require_non_empty_string(analysis_id, "analysis_id")
    if session_name is not None:
        session_name = _require_non_empty_string(session_name, "session_name")

    await ctx.info(f"Starting training for ML analysis {analysis_id}...")

    def _runner() -> dict[str, Any]:
        _, _, mltask_id, _ = get_single_task_bundle(project_key, analysis_id)
        return {
            # analysis_id dropped (LEVER 3): pure echo of the analysis_id argument.
            # mltask_id is server-resolved from the analysis, so it is kept.
            "mltask_id": mltask_id,
            "trained_models": columnar(
                train_models(
                    project_key,
                    analysis_id,
                    mltask_id,
                    session_name,
                    session_description,
                    run_queue,
                ),
                ["id", "algorithm", "metrics"],
            ),
        }

    result = await run_blocking(_runner)
    await ctx.report_progress(1, 1)
    return compact_json(result)


@mcp.tool()
async def list_ml_analysis_models(
    project_key: str,
    analysis_id: str,
    ctx: Context,
) -> str:
    """List the trained models for the single ML task in an analysis.

    Args:
        analysis_id: Analysis ID from list_ml_analyses
    """
    project_key = _require_non_empty_string(project_key, "project_key")
    analysis_id = _require_non_empty_string(analysis_id, "analysis_id")

    await ctx.info(f"Listing trained models for ML analysis {analysis_id}...")

    def _list() -> dict[str, Any]:
        _, _, mltask_id, mltask = get_single_task_bundle(project_key, analysis_id)
        trained_model_ids = mltask.get_trained_models_ids()
        snippets = (
            mltask.get_trained_model_snippet(ids=trained_model_ids)
            if trained_model_ids
            else {}
        )
        models = []
        for trained_model_id in trained_model_ids:
            snippet = snippets.get(trained_model_id, {})
            # full_model_id / algorithm / session_id dropped (LEVER 2): each is an
            # exact copy of snippet["fullModelId"] / ["algorithm"] / ["sessionId"],
            # and slim_model_data only strips *PerFeature keys, so those keys always
            # survive in the emitted snippet — reconstructable per row.
            models.append(
                {
                    "trained_model_id": trained_model_id,
                    "snippet": slim_model_data(snippet),
                }
            )
        return {
            # project_key / analysis_id dropped (LEVER 3): each is a pure echo of the
            # like-named argument. mltask_id is server-resolved from the analysis.
            "mltask_id": mltask_id,
            "models": columnar(
                models,
                [
                    "trained_model_id",
                    "snippet",
                ],
            ),
        }

    return compact_json(await run_blocking(_list))


@mcp.tool()
async def get_ml_model_details(
    project_key: str,
    analysis_id: str,
    trained_model_id: str,
    ctx: Context,
) -> str:
    """Get the snippet for a trained model: algorithm, performance metrics, hyperparameters, feature importances, ML diagnostics, and train/test row counts.

    Args:
        analysis_id: Analysis ID from list_ml_analyses
        trained_model_id: Trained model ID from list_ml_analysis_models
    """
    project_key = _require_non_empty_string(project_key, "project_key")
    analysis_id = _require_non_empty_string(analysis_id, "analysis_id")
    trained_model_id = _require_non_empty_string(trained_model_id, "trained_model_id")

    await ctx.info(
        f"Loading trained model {trained_model_id} from analysis {analysis_id}..."
    )

    def _get() -> dict[str, Any]:
        _, _, mltask_id, mltask = get_single_task_bundle(project_key, analysis_id)
        details = mltask.get_trained_model_details(trained_model_id)
        return {
            # project_key / analysis_id / trained_model_id dropped (LEVER 3): each is a
            # pure echo of the like-named argument. mltask_id is server-resolved from
            # the analysis, and full_model_id is the server-side details.full_id, so
            # both are kept.
            "mltask_id": mltask_id,
            "full_model_id": details.full_id,
            "details_class": details.__class__.__name__,
            "snippet": details.get_raw_snippet(),
        }

    return compact_json(await run_blocking(_get))


@mcp.tool()
async def deploy_ml_analysis_model(
    project_key: str,
    analysis_id: str,
    trained_model_id: str,
    ctx: Context,
    # Fresh deployment — required when existing_saved_model_id is not set
    train_dataset: str | None = None,
    saved_model_name: str | None = None,
    test_dataset: str | None = None,
    redo_optimization: bool = True,
    # Redeploy to existing saved model — triggers redeploy mode when set
    existing_saved_model_id: str | None = None,
    activate: bool = True,
    redo_threshold_optimization: bool = True,
    fixed_threshold: float | None = None,
) -> str:
    """Deploy a trained model from an analysis to the flow. Two modes:
    - Fresh deploy: provide train_dataset (omit existing_saved_model_id) — creates a new saved model and training recipe.
    - Redeploy: provide existing_saved_model_id — updates the saved model in place.

    Args:
        analysis_id: Analysis ID from list_ml_analyses
        trained_model_id: Trained model ID from list_ml_analysis_models
        existing_saved_model_id: Saved model ID from list_saved_models (for redeploy mode)
    """
    project_key = _require_non_empty_string(project_key, "project_key")
    analysis_id = _require_non_empty_string(analysis_id, "analysis_id")
    trained_model_id = _require_non_empty_string(trained_model_id, "trained_model_id")
    if train_dataset is not None:
        train_dataset = _require_non_empty_string(train_dataset, "train_dataset")
    if saved_model_name is not None:
        saved_model_name = _require_non_empty_string(
            saved_model_name, "saved_model_name"
        )
    if test_dataset is not None:
        test_dataset = _require_non_empty_string(test_dataset, "test_dataset")
    if existing_saved_model_id is not None:
        existing_saved_model_id = _require_non_empty_string(
            existing_saved_model_id, "existing_saved_model_id"
        )

    if existing_saved_model_id:
        await ctx.info(
            f"Redeploying trained model {trained_model_id} to existing saved model {existing_saved_model_id}..."
        )
    else:
        if not train_dataset:
            raise ValueError("train_dataset is required for a fresh deployment.")
        await ctx.info(
            f"Deploying trained model {trained_model_id} from analysis {analysis_id}..."
        )

    def _deploy() -> dict[str, Any]:
        _, _, mltask_id, mltask = get_single_task_bundle(project_key, analysis_id)
        if existing_saved_model_id:
            result = mltask.redeploy_to_flow(
                model_id=trained_model_id,
                saved_model_id=existing_saved_model_id,
                activate=activate,
                redo_optimization=redo_optimization,
                redo_threshold_optimization=redo_threshold_optimization,
                fixed_threshold=fixed_threshold,
            )
            redeployed = {
                # status:"redeployed" dropped (LEVER 5): constant literal, invariant on
                # this return path; redeploy_to_flow raises on failure, so receiving the
                # result already implies success — the word carries no per-call info.
                # project_key / analysis_id / trained_model_id / existing_saved_model_id
                # / activate dropped (LEVER 3): each is a pure echo of the like-named
                # argument on this path. mltask_id is server-resolved; impacts_downstream
                # is server-returned, so both are kept.
                "mltask_id": mltask_id,
                "impacts_downstream": result.get("impactsDownstream"),
            }
            # LEVER 4: omit impacts_downstream when None/empty; absent reads as empty.
            # activate kept even when False (false boolean carries information).
            return omit_empty(redeployed)
        else:
            result = mltask.deploy_to_flow(
                model_id=trained_model_id,
                model_name=saved_model_name
                or f"model_{trained_model_id.split('-')[-1]}",
                train_dataset=train_dataset,
                test_dataset=test_dataset,
                redo_optimization=redo_optimization,
            )
            deployed = {
                # status:"deployed" dropped (LEVER 5): constant literal, invariant on
                # this return path; deploy_to_flow raises on failure, so receiving the
                # result already implies success — the word carries no per-call info.
                # project_key / analysis_id / trained_model_id dropped (LEVER 3): each is
                # a pure echo of the like-named argument. mltask_id is server-resolved;
                # saved_model_id and train_recipe_name are server-GENERATED by the
                # deploy_to_flow call, so all three are kept.
                "mltask_id": mltask_id,
                "saved_model_id": result.get("savedModelId"),
                "train_recipe_name": result.get("trainRecipeName"),
            }
            # LEVER 4: omit saved_model_id / train_recipe_name when None/empty;
            # absent reads as empty.
            return omit_empty(deployed)

    return compact_json(await run_blocking(_deploy))
