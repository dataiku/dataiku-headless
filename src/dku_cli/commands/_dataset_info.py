from __future__ import annotations

from datetime import datetime, timezone

from dataikuapi.utils import DataikuException

from dku_cli.output import warn


def read_last_build(ds, dataset_name: str, fmt: str):
    last_build_time = None
    build_success = None
    try:
        raw_info = ds.get_info().get_raw()
        last_build = raw_info.get("lastBuild", {})
        if last_build.get("buildEndTime"):
            ts = last_build["buildEndTime"] / 1000
            last_build_time = datetime.fromtimestamp(ts, tz=timezone.utc).strftime(
                "%Y-%m-%d %H:%M UTC"
            )
        build_success = last_build.get("buildSuccess")
    except DataikuException as exc:
        if fmt != "json":
            warn(f"Could not fetch last build status for '{dataset_name}': {exc}")
    return last_build_time, build_success


def read_metric_counts(ds, dataset_name: str, fmt: str, fresh_values: dict[str, str]):
    row_count = _fresh_int(fresh_values, "records:COUNT_RECORDS")
    data_size_bytes = _fresh_int(fresh_values, "basic:SIZE")
    file_count = _fresh_int(fresh_values, "basic:COUNT_FILES")
    metrics_stale = row_count is None and data_size_bytes is None
    if row_count is not None and data_size_bytes is not None and file_count is not None:
        return row_count, data_size_bytes, file_count, metrics_stale

    try:
        metrics = ds.get_last_metric_values()
        available_ids = metrics.get_all_ids()
        row_count, metrics_stale = _read_metric(
            metrics,
            available_ids,
            row_count,
            metrics_stale,
            "records:COUNT_RECORDS",
            "row-count",
            dataset_name,
            fmt,
        )
        data_size_bytes, metrics_stale = _read_metric(
            metrics,
            available_ids,
            data_size_bytes,
            metrics_stale,
            "basic:SIZE",
            "size",
            dataset_name,
            fmt,
        )
        file_count, metrics_stale = _read_metric(
            metrics,
            available_ids,
            file_count,
            metrics_stale,
            "basic:COUNT_FILES",
            "file-count",
            dataset_name,
            fmt,
        )
    except DataikuException as exc:
        if fmt != "json":
            warn(f"Could not fetch stored metrics for '{dataset_name}': {exc}")
    return row_count, data_size_bytes, file_count, metrics_stale


def _fresh_int(fresh_values: dict[str, str], metric_id: str):
    value = fresh_values.get(metric_id)
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _read_metric(
    metrics,
    available_ids,
    current,
    metrics_stale: bool,
    metric_id: str,
    label: str,
    dataset_name: str,
    fmt: str,
):
    if current is not None or metric_id not in available_ids:
        return current, metrics_stale
    try:
        return metrics.get_global_value(metric_id), False
    except Exception as exc:  # quality-ratchet: allow-broad-exception
        # dataikuapi's ComputedMetrics.get_global_value raises a BARE Exception
        # (not DataikuException) when a registered metric has no NP/ALL global
        # value — the common "metric present but not computed" state. Catch it
        # broadly so `dku dataset info` degrades to "not computed" instead of
        # crashing; a narrow DataikuException catch lets it propagate (exit 1).
        if fmt != "json":
            warn(f"Could not read {label} metric for '{dataset_name}': {exc}")
        return current, metrics_stale
