"""Metric helpers for machine learning tools."""

_CLASSIFICATION_METRICS = {
    "ACCURACY",
    "F1",
    "LOG_LOSS",
    "PRECISION",
    "RECALL",
    "ROC_AUC",
}

_REGRESSION_METRICS = {
    "MAE",
    "MAPE",
    "R2",
    "RMSE",
}


def normalize_metric(metric: str, prediction_type: str | None = None) -> str:
    cleaned = metric.strip().upper()
    if cleaned == "AUC":
        cleaned = "ROC_AUC"

    if prediction_type == "REGRESSION" and cleaned not in _REGRESSION_METRICS:
        allowed = sorted(_REGRESSION_METRICS)
        raise ValueError(
            f"Invalid 'metric' for regression task: '{metric}'. Allowed values: {allowed}"
        )

    if prediction_type in {"BINARY_CLASSIFICATION", "MULTICLASS"} and cleaned not in _CLASSIFICATION_METRICS:
        allowed = sorted(_CLASSIFICATION_METRICS | {"AUC"})
        raise ValueError(
            f"Invalid 'metric' for classification task: '{metric}'. Allowed values: {allowed}"
        )

    return cleaned

