"""Shared ML task settings mutation helpers."""

from __future__ import annotations

from typing import Any

from ...utils.parsing import deep_merge_dict as _deep_merge_dict
from .metrics import normalize_metric

_ENV_MODES = {"EXPLICIT_ENV", "INHERIT", "USE_BUILTIN_MODE"}


def apply_env_selection(
    raw_settings: dict,
    env_mode: str | None,
    env_name: str | None,
) -> None:
    if env_mode is None:
        return
    if env_mode not in _ENV_MODES:
        raise ValueError(f"'env_mode' must be one of: {sorted(_ENV_MODES)}")
    if env_mode == "EXPLICIT_ENV" and not env_name:
        raise ValueError("'env_name' is required when env_mode is 'EXPLICIT_ENV'")
    raw_settings["envSelection"] = (
        {"envMode": env_mode, "envName": env_name}
        if env_mode == "EXPLICIT_ENV"
        else {"envMode": env_mode}
    )


def validate_feature_names(
    raw_settings: dict,
    feature_names: list[str],
    field_name: str,
) -> None:
    available = set(raw_settings.get("preprocessing", {}).get("per_feature", {}).keys())
    unknown = sorted(set(feature_names) - available)
    if unknown:
        raise ValueError(
            f"Unknown feature(s) in '{field_name}': {unknown}. "
            f"Available features: {sorted(available)}"
        )


def apply_algorithm_selection(settings, algorithms: list[str] | None) -> None:
    if algorithms is None:
        return

    available_algorithms = set(settings.get_all_possible_algorithm_names())
    unknown_algorithms = sorted(set(algorithms) - available_algorithms)
    if unknown_algorithms:
        raise ValueError(
            f"Unknown algorithm(s): {unknown_algorithms}. "
            f"Available algorithms: {sorted(available_algorithms)}"
        )
    settings.disable_all_algorithms()
    for algorithm in algorithms:
        settings.set_algorithm_enabled(algorithm, True)


def apply_feature_selection(
    *,
    settings,
    raw_settings: dict[str, Any],
    included_features: list[str] | None,
    rejected_features: list[str] | None,
    protected_roles: set[str] | None = None,
    protected_feature_names: set[str] | None = None,
) -> None:
    if included_features is not None and rejected_features is not None:
        raise ValueError(
            "Use either 'included_features' or 'rejected_features', not both in one call."
        )

    protected_roles = protected_roles or set()
    protected_feature_names = protected_feature_names or set()

    if included_features is not None:
        validate_feature_names(raw_settings, included_features, "included_features")
        protected_included = sorted(set(included_features) & protected_feature_names)
        if protected_included:
            raise ValueError(
                f"'included_features' must not contain protected feature(s): {protected_included}."
            )
        selected = set(included_features)
        for feature_name, feature_params in raw_settings.get("preprocessing", {}).get("per_feature", {}).items():
            if (
                feature_name in protected_feature_names
                or feature_params.get("role") in protected_roles
            ):
                continue
            if feature_name in selected:
                settings.use_feature(feature_name)
            else:
                settings.reject_feature(feature_name)

    if rejected_features is not None:
        validate_feature_names(raw_settings, rejected_features, "rejected_features")
        protected_rejected = sorted(set(rejected_features) & protected_feature_names)
        if protected_rejected:
            raise ValueError(
                f"'rejected_features' must not contain protected feature(s): {protected_rejected}."
            )
        for feature_name in rejected_features:
            feature_role = (
                raw_settings.get("preprocessing", {})
                .get("per_feature", {})
                .get(feature_name, {})
                .get("role")
            )
            if feature_role in protected_roles:
                raise ValueError(
                    f"'rejected_features' must not contain features with protected role '{feature_role}': '{feature_name}'."
                )
            settings.reject_feature(feature_name)


def validate_json_object_map(
    patch_obj: dict[str, Any],
    field_name: str,
) -> None:
    for key, value in patch_obj.items():
        if not isinstance(value, dict):
            raise ValueError(
                f"Each value in '{field_name}' must be a JSON object. "
                f"Key '{key}' received {type(value).__name__}."
            )


def validate_bool_map(
    patch_obj: dict[str, Any],
    field_name: str,
) -> None:
    for key, value in patch_obj.items():
        if not isinstance(value, bool):
            raise ValueError(
                f"Each value in '{field_name}' must be a boolean. "
                f"Key '{key}' received {type(value).__name__}."
            )


def apply_split_settings(
    *,
    settings,
    raw_settings: dict[str, Any],
    split_method: str | None,
    train_ratio: float | None,
    n_folds: int | None,
    stratified: bool | None,
    time_ordering_feature: str | None,
    time_ordering_ascending: bool,
    disable_time_ordering: bool,
    split_seed: int | None,
) -> None:
    split_method = split_method or ("KFOLD" if n_folds is not None else None)
    split_params_handler = settings.get_split_params()
    current_split = raw_settings.setdefault("splitParams", {})

    if split_method == "RANDOM":
        split_params_handler.set_split_random(
            train_ratio=train_ratio if train_ratio is not None else current_split.get("ssdTrainingRatio", 0.8)
        )
    elif split_method == "KFOLD":
        split_params_handler.set_split_kfold(
            n_folds=n_folds if n_folds is not None else current_split.get("nFolds", 5)
        )
    elif train_ratio is not None:
        split_params_handler.set_split_random(train_ratio=train_ratio)

    if stratified is not None:
        current_split["ssdStratified"] = stratified

    if split_seed is not None:
        current_split["ssdSeed"] = split_seed
        current_split["subSamplingSeed"] = split_seed

    if disable_time_ordering:
        split_params_handler.unset_time_ordering()

    if time_ordering_feature is not None:
        validate_feature_names(raw_settings, [time_ordering_feature], "time_ordering_feature")
        split_params_handler.set_time_ordering(
            time_ordering_feature,
            ascending=time_ordering_ascending,
        )
    elif time_ordering_ascending is not True:
        raise ValueError(
            "'time_ordering_ascending' can only be set when 'time_ordering_feature' is provided."
        )


def apply_custom_metric(
    *,
    settings,
    prediction_type: str | None,
    metric: str | None,
    custom_metric_code: str | None,
    custom_metric_name: str | None,
    custom_metric_greater_is_better: bool,
    custom_metric_use_probabilities: bool,
) -> None:
    if custom_metric_code is not None and metric is not None:
        raise ValueError(
            "Use either 'metric' or 'custom_metric_code' in one call, not both."
        )
    if custom_metric_name is not None and custom_metric_code is None:
        raise ValueError(
            "'custom_metric_name' requires 'custom_metric_code' to be set in the same call."
        )
    if custom_metric_code is not None:
        settings.set_metric(
            custom_metric=custom_metric_code,
            custom_metric_name=custom_metric_name,
            custom_metric_greater_is_better=custom_metric_greater_is_better,
            custom_metric_use_probas=custom_metric_use_probabilities,
        )
    elif metric is not None:
        settings.set_metric(metric=normalize_metric(metric, prediction_type))


def apply_hyperparameter_search_settings(
    *,
    settings,
    search_strategy: str | None,
    search_randomize_grid: bool | None,
    search_seed: int | None,
    search_n_iter: int | None,
    search_timeout: int | None,
    search_parallelism: int | None,
    search_distributed: bool | None,
    search_n_containers: int | None,
    search_validation_mode: str | None,
    search_validation_ratio: float | None,
    search_n_folds: int | None,
    search_stratified: bool | None,
    search_cv_seed: int | None,
    custom_search_validation_code: str | None,
) -> None:
    search_settings = settings.get_hyperparameter_search_settings()
    raw_search = search_settings._raw_settings
    current_validation_mode = raw_search.get("mode")

    if search_strategy == "GRID":
        search_settings.set_grid_search(
            shuffle=(
                search_randomize_grid
                if search_randomize_grid is not None
                else raw_search.get("randomized", True)
            ),
            seed=search_seed if search_seed is not None else raw_search.get("seed", 1337),
        )
    elif search_strategy == "RANDOM":
        search_settings.set_random_search(
            seed=search_seed if search_seed is not None else raw_search.get("seed", 1337)
        )
    elif search_strategy == "BAYESIAN":
        search_settings.set_bayesian_search(
            seed=search_seed if search_seed is not None else raw_search.get("seed", 1337)
        )
    else:
        if search_randomize_grid is not None:
            if raw_search.get("strategy") != "GRID":
                raise ValueError(
                    "'search_randomize_grid' can only be set when the hyperparameter search strategy is GRID."
                )
            raw_search["randomized"] = search_randomize_grid
        if search_seed is not None:
            raw_search["seed"] = search_seed

    search_validation_mode = search_validation_mode or (
        "CUSTOM" if custom_search_validation_code is not None else None
    )
    search_validation_mode = search_validation_mode or (
        "KFOLD" if search_n_folds is not None else None
    )
    search_validation_mode = search_validation_mode or (
        "SINGLE_SPLIT" if search_validation_ratio is not None else None
    )
    search_validation_mode = search_validation_mode or (
        {
            "KFOLD": "KFOLD",
            "TIME_SERIES_KFOLD": "KFOLD",
            "SHUFFLE": "SINGLE_SPLIT",
            "TIME_SERIES_SINGLE_SPLIT": "SINGLE_SPLIT",
            "CUSTOM": "CUSTOM",
        }.get(current_validation_mode)
        if any(
            value is not None
            for value in [search_stratified, search_cv_seed]
        )
        else None
    )

    if search_validation_mode == "KFOLD":
        search_settings.set_kfold_validation(
            n_folds=search_n_folds if search_n_folds is not None else raw_search.get("nFolds", 5),
            stratified=(
                search_stratified
                if search_stratified is not None
                else raw_search.get("stratified", True)
            ),
            cv_seed=search_cv_seed if search_cv_seed is not None else raw_search.get("cvSeed", 1337),
        )
    elif search_validation_mode == "SINGLE_SPLIT":
        search_settings.set_single_split_validation(
            split_ratio=(
                search_validation_ratio
                if search_validation_ratio is not None
                else raw_search.get("splitRatio", 0.8)
            ),
            stratified=(
                search_stratified
                if search_stratified is not None
                else raw_search.get("stratified", True)
            ),
            cv_seed=search_cv_seed if search_cv_seed is not None else raw_search.get("cvSeed", 1337),
        )
    elif search_validation_mode == "CUSTOM":
        search_settings.set_custom_validation(code=custom_search_validation_code)
        if search_cv_seed is not None:
            search_settings.cv_seed = search_cv_seed
    elif custom_search_validation_code is not None:
        raise ValueError(
            "'custom_search_validation_code' requires 'search_validation_mode=\"CUSTOM\"' or no explicit validation mode."
        )

    if search_n_iter is not None:
        search_settings.n_iter = search_n_iter
    if search_timeout is not None:
        search_settings.timeout = search_timeout
    if search_parallelism is not None:
        search_settings.parallelism = search_parallelism
    if search_distributed is not None or search_n_containers is not None:
        search_settings.set_search_distribution(
            distributed=(
                search_distributed
                if search_distributed is not None
                else raw_search.get("distributed", False)
            ),
            n_containers=(
                search_n_containers
                if search_n_containers is not None
                else raw_search.get("nContainers", 4)
            ),
        )


def apply_diagnostics_settings(
    *,
    settings,
    diagnostics_enabled: bool | None,
    diagnostic_type_overrides: dict[str, bool] | None,
) -> None:
    if diagnostics_enabled is not None:
        settings.set_diagnostics_enabled(diagnostics_enabled)
    if diagnostic_type_overrides is not None:
        validate_bool_map(diagnostic_type_overrides, "diagnostic_type_overrides")
        for diagnostic_type, enabled in diagnostic_type_overrides.items():
            settings.set_diagnostic_type_enabled(diagnostic_type, enabled)


def coerce_hyperparams_to_grid_objects(current_algo_settings: dict, patch: dict) -> dict:
    """Coerce plain lists in patch to DSS grid objects when the current setting is already a grid object."""
    coerced = {}
    for key, patch_value in patch.items():
        current_value = current_algo_settings.get(key)
        if (
            isinstance(patch_value, list)
            and isinstance(current_value, dict)
            and "values" in current_value
        ):
            coerced[key] = {**current_value, "values": patch_value}
        else:
            coerced[key] = patch_value
    return coerced


def apply_algorithm_settings_patch(settings, patch_obj: dict[str, Any]) -> None:
    if not patch_obj:
        return
    validate_json_object_map(patch_obj, "algorithm_settings_patch")

    available_algorithms = set(settings.get_all_possible_algorithm_names())
    unknown_algorithms = sorted(set(patch_obj) - available_algorithms)
    if unknown_algorithms:
        raise ValueError(
            f"Unknown algorithm(s) in 'algorithm_settings_patch': {unknown_algorithms}. "
            f"Available algorithms: {sorted(available_algorithms)}"
        )

    for algorithm_name, algorithm_patch in patch_obj.items():
        algorithm_settings = settings.get_algorithm_settings(algorithm_name)
        current = dict(algorithm_settings)
        coerced_patch = coerce_hyperparams_to_grid_objects(current, algorithm_patch)
        merged_settings = _deep_merge_dict(current, coerced_patch)
        algorithm_settings.clear()
        algorithm_settings.update(merged_settings)


def apply_feature_preprocessing_patch(
    settings,
    raw_settings: dict[str, Any],
    patch_obj: dict[str, Any],
) -> None:
    if not patch_obj:
        return
    validate_json_object_map(patch_obj, "feature_preprocessing_patch")
    validate_feature_names(raw_settings, list(patch_obj.keys()), "feature_preprocessing_patch")

    for feature_name, feature_patch in patch_obj.items():
        feature_settings = settings.get_feature_preprocessing(feature_name)
        merged_settings = _deep_merge_dict(dict(feature_settings), feature_patch)
        feature_settings.clear()
        feature_settings.update(merged_settings)


def apply_feature_reduction_settings(
    *,
    raw_settings: dict[str, Any],
    feature_reduction_method: str | None,
    feature_reduction_n_features: int | None,
    feature_reduction_variance_proportion: float | None,
) -> None:
    if (
        feature_reduction_method is None
        and feature_reduction_n_features is None
        and feature_reduction_variance_proportion is None
    ):
        return

    if feature_reduction_variance_proportion is not None and feature_reduction_method not in {None, "PCA"}:
        raise ValueError(
            "'feature_reduction_variance_proportion' can only be set when feature_reduction_method is 'PCA'."
        )

    preprocessing = raw_settings.setdefault("preprocessing", {})
    fsp = preprocessing.setdefault("feature_selection_params", {})

    if feature_reduction_method is not None:
        fsp["method"] = feature_reduction_method

    method = fsp.get("method")
    if feature_reduction_n_features is not None:
        if method == "RANDOM_FOREST":
            fsp.setdefault("random_forest_params", {})["n_features"] = feature_reduction_n_features
        elif method == "PCA":
            fsp.setdefault("pca_params", {})["n_features"] = feature_reduction_n_features
        elif method == "ICA":
            fsp.setdefault("ica_params", {})["n_components"] = feature_reduction_n_features
        elif method == "CORRELATION":
            fsp.setdefault("correlation_params", {})["n_features"] = feature_reduction_n_features
        else:
            raise ValueError(
                f"'feature_reduction_n_features' is not applicable for method '{method}'. "
                "Use with RANDOM_FOREST, PCA, ICA, or CORRELATION."
            )

    if feature_reduction_variance_proportion is not None:
        fsp.setdefault("pca_params", {})["variance_proportion"] = feature_reduction_variance_proportion
