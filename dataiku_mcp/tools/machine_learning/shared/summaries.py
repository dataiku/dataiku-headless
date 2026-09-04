# Copyright 2026 Dataiku SAS
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Summary builders for machine learning tool responses."""

from __future__ import annotations

from typing import Any


def summarize_trained_models(mltask, model_ids: list[str] | None = None) -> list[dict]:
    summaries = []
    selected_model_ids = model_ids or mltask.get_trained_models_ids()
    for model_id in selected_model_ids:
        details = mltask.get_trained_model_details(model_id)
        summaries.append(
            {
                "id": model_id,
                "algorithm": details.get_modeling_settings().get(
                    "algorithm", "unknown"
                ),
                "metrics": details.get_performance_metrics(),
            }
        )
    return summaries


def build_feature_summaries(
    raw_settings: dict,
    include_feature_details: bool,
) -> dict[str, Any]:
    per_feature = raw_settings.get("preprocessing", {}).get("per_feature", {})
    role_counts: dict[str, int] = {}
    feature_details = []
    for feature_name in sorted(per_feature):
        feature = per_feature[feature_name]
        role = feature.get("role", "UNKNOWN")
        role_counts[role] = role_counts.get(role, 0) + 1
        if include_feature_details:
            feature_details.append(
                {
                    "name": feature_name,
                    "role": role,
                    "type": feature.get("type"),
                    "missing_handling": feature.get("missing_handling"),
                }
            )
    return {
        "feature_role_counts": role_counts,
        "features": feature_details if include_feature_details else None,
    }


def build_split_summary(raw_settings: dict) -> dict[str, Any]:
    split = raw_settings.get("splitParams", {})
    return {
        "policy": split.get("ttPolicy"),
        "mode": split.get("ssdSplitMode"),
        "train_ratio": split.get("ssdTrainingRatio"),
        "kfold": split.get("kfold"),
        "n_folds": split.get("nFolds"),
        "stratified": split.get("ssdStratified"),
    }


def build_metric_summary(raw_settings: dict) -> dict[str, Any]:
    metrics = raw_settings.get("modeling", {}).get("metrics", {})
    custom_metrics = metrics.get("customMetrics", [])
    active_custom_metric_name = metrics.get("customEvaluationMetricName")
    active_custom_metric = next(
        (
            item
            for item in custom_metrics
            if item.get("name") == active_custom_metric_name
        ),
        None,
    )
    return {
        "evaluation_metric": metrics.get("evaluationMetric"),
        "custom_evaluation_metric_name": active_custom_metric_name,
        "active_custom_metric": active_custom_metric,
    }


def build_hyperparameter_search_summary(raw_settings: dict) -> dict[str, Any] | None:
    search = raw_settings.get("modeling", {}).get("gridSearchParams")
    if not search:
        return None
    strategy = search.get("strategy")
    return {
        "strategy": strategy,
        "validation_mode": search.get("mode"),
        "n_iter": search.get("nIter")
        if strategy == "GRID"
        else search.get("nIterRandom"),
        "randomized_grid": search.get("randomized"),
        "seed": search.get("seed"),
        "split_ratio": search.get("splitRatio"),
        "n_folds": search.get("nFolds"),
        "cv_seed": search.get("cvSeed"),
        "stratified": search.get("stratified"),
        "timeout": search.get("timeout"),
        "parallelism": search.get("nJobs"),
        "distributed": search.get("distributed"),
        "n_containers": search.get("nContainers"),
        "has_custom_validation_code": bool(search.get("code")),
    }


def build_diagnostics_summary(raw_settings: dict) -> dict[str, Any] | None:
    diagnostics = raw_settings.get("diagnosticsSettings")
    if not diagnostics:
        return None
    per_type = {
        item.get("type"): item.get("enabled")
        for item in diagnostics.get("settings", [])
        if item.get("type")
    }
    return {
        "enabled": diagnostics.get("enabled"),
        "per_type": per_type,
        "disabled_types": sorted(
            diagnostic_type
            for diagnostic_type, enabled in per_type.items()
            if enabled is False
        ),
    }


def build_ml_task_summary(
    *,
    project_key: str,
    analysis_id: str,
    analysis_name: str | None,
    input_dataset: str | None,
    mltask_id: str,
    mltask,
    settings,
    include_feature_details: bool,
    include_trained_models: bool,
) -> dict[str, Any]:
    raw_settings = settings.get_raw()
    status = mltask.get_status()

    summary = {
        "project_key": project_key,
        "analysis_id": analysis_id,
        "analysis_name": analysis_name,
        "input_dataset": input_dataset,
        "mltask_id": mltask_id,
        "task_type": raw_settings.get("taskType"),
        "prediction_type": raw_settings.get("predictionType"),
        "target_column": raw_settings.get("targetVariable"),
        "backend_type": raw_settings.get("backendType"),
        "metric": raw_settings.get("modeling", {})
        .get("metrics", {})
        .get("evaluationMetric"),
        "metric_details": build_metric_summary(raw_settings),
        "enabled_algorithms": (
            settings.get_enabled_algorithm_names()
            if hasattr(settings, "get_enabled_algorithm_names")
            else []
        ),
        "guessing": status.get("guessing"),
        "training": status.get("training"),
        "trained_model_count": len(status.get("fullModelIds", [])),
        "split": build_split_summary(raw_settings),
        "hyperparameter_search": build_hyperparameter_search_summary(raw_settings),
        "weighting": raw_settings.get("weight"),
        "diagnostics": build_diagnostics_summary(raw_settings),
    }
    summary.update(build_feature_summaries(raw_settings, include_feature_details))

    if include_trained_models:
        summary["trained_models"] = summarize_trained_models(mltask)

    return summary
