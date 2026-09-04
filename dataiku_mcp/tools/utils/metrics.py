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

"""Shared helpers for metrics-oriented tool handlers."""

from __future__ import annotations

import json
from typing import Any

from .validation import require_non_empty_strings


def parse_metric_ids(metric_ids: str | None) -> list[str] | None:
    """Parse optional metric id JSON array into a cleaned string list."""
    if metric_ids is None:
        return None

    try:
        parsed = json.loads(metric_ids)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON for 'metric_ids': {exc}") from exc

    if not isinstance(parsed, list):
        raise ValueError("'metric_ids' must be a JSON array when provided")

    return require_non_empty_strings(parsed, "metric_ids")


def select_metrics(
    raw_metrics: list[dict[str, Any]], metric_ids: list[str] | None
) -> dict:
    """Select and annotate metric values for either all ids or a requested subset."""
    if metric_ids is None:
        return {"metrics": raw_metrics}

    requested = set(metric_ids)
    filtered_metrics = []
    found_ids = set()
    for metric in raw_metrics:
        metric_id = metric.get("metric", {}).get("id")
        if metric_id in requested:
            filtered_metrics.append(metric)
            found_ids.add(metric_id)

    result = {
        "metrics": filtered_metrics,
        "requested_metric_ids": metric_ids,
    }
    missing_metric_ids = [
        metric_id for metric_id in metric_ids if metric_id not in found_ids
    ]
    if missing_metric_ids:
        result["missing_metric_ids"] = missing_metric_ids
    return result
