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

"""Tests for dataset metric freshness.

The fake mirrors DSS defaults: a build records ``basic:*`` metrics, but the
built-in ``records:COUNT_RECORDS`` probe does not compute on build, so its stored
value keeps describing the data from before the build until it is recomputed.
"""

import asyncio
import json

import pytest

from dataiku_mcp.tools import datasets
from dataiku_mcp.tools.utils.metrics import stale_metric_ids
from tests.utils.fakes import FakeContext

OLD_COUNT_TIME = 1_000
BUILD_START = 2_000
BUILD_METRIC_TIME = 2_100
REFRESH_TIME = 3_000


def _metric(metric_id: str, value: str, computed: int) -> dict:
    return {
        "metric": {"id": metric_id},
        "lastValues": [
            {
                "computed": computed,
                "partition": "NP",
                "dataType": "BIGINT",
                "value": value,
            }
        ],
    }


class _Raw:
    def __init__(self, raw: dict):
        self.raw = raw

    def get_raw(self) -> dict:
        return self.raw


class _StaleCountDataset:
    """Holds 250 rows now; its stored record count still says 100."""

    def __init__(self, *, compute_error=None, engine_error=None, count_enabled=True):
        self.live_count = "250"
        self.stored = {
            "records:COUNT_RECORDS": _metric(
                "records:COUNT_RECORDS", "100", OLD_COUNT_TIME
            ),
            "basic:SIZE": _metric("basic:SIZE", "4096", BUILD_METRIC_TIME),
        }
        self.compute_error = compute_error
        self.engine_error = engine_error
        self.count_enabled = count_enabled
        self.compute_calls: list = []

    def compute_metrics(self, partition="", metric_ids=None, probes=None):
        self.compute_calls.append(metric_ids)
        if self.compute_error:
            raise self.compute_error
        runs = [{"engine": "SQL"}]
        computed = []
        if self.engine_error:
            runs[0]["error"] = {"message": self.engine_error}
        else:
            enabled_ids = ["basic:SIZE"]
            if self.count_enabled:
                enabled_ids.append("records:COUNT_RECORDS")
            for metric_id in enabled_ids if metric_ids is None else metric_ids:
                if metric_id not in self.stored:
                    continue
                value = (
                    self.live_count if metric_id == "records:COUNT_RECORDS" else "4096"
                )
                self.stored[metric_id] = _metric(metric_id, value, REFRESH_TIME)
                computed.append({"metricId": metric_id, "value": value})
        return {"hasResult": True, "result": {"computed": computed, "runs": runs}}

    def get_last_metric_values(self, partition=""):
        return _Raw({"metrics": list(self.stored.values())})

    def get_info(self):
        return _Raw({"lastBuild": {"buildStartTime": BUILD_START}})


class _Client:
    def __init__(self, dataset):
        self.dataset = dataset

    def get_project(self, project_key):
        assert project_key == "PROJECT"
        return self

    def get_dataset(self, dataset_name):
        assert dataset_name == "orders"
        return self.dataset


def _get_metrics(monkeypatch, dataset, **kwargs) -> dict:
    monkeypatch.setattr(datasets, "get_dss_client", lambda: _Client(dataset))
    return json.loads(
        asyncio.run(
            datasets.get_dataset_metrics("PROJECT", "orders", FakeContext(), **kwargs)
        )
    )


def _value(result: dict, metric_id: str) -> str:
    for metric in result["metrics"]:
        if metric["metric"]["id"] == metric_id:
            return metric["lastValues"][0]["value"]
    raise AssertionError(f"{metric_id} not returned")


def test_default_recomputes_instead_of_returning_the_stored_count(monkeypatch):
    dataset = _StaleCountDataset()

    result = _get_metrics(monkeypatch, dataset)

    assert dataset.compute_calls == [None]
    assert result["refreshed"] is True
    assert _value(result, "records:COUNT_RECORDS") == "250"
    assert "stale_metric_ids" not in result


def test_requested_ids_are_the_ones_recomputed(monkeypatch):
    dataset = _StaleCountDataset()

    result = _get_metrics(monkeypatch, dataset, metric_ids='["records:COUNT_RECORDS"]')

    assert dataset.compute_calls == [["records:COUNT_RECORDS"]]
    assert [m["metric"]["id"] for m in result["metrics"]] == ["records:COUNT_RECORDS"]
    assert _value(result, "records:COUNT_RECORDS") == "250"


def test_disabled_probe_does_not_make_its_stored_count_fresh(monkeypatch):
    dataset = _StaleCountDataset(count_enabled=False)

    result = _get_metrics(monkeypatch, dataset)

    assert dataset.compute_calls == [None]
    assert result["refreshed"] is False
    assert result["unrefreshed_metric_ids"] == ["records:COUNT_RECORDS"]
    assert "refresh_error" in result
    assert _value(result, "records:COUNT_RECORDS") == "100"
    assert result["stale_metric_ids"] == ["records:COUNT_RECORDS"]


def test_stored_read_flags_values_older_than_the_last_build(monkeypatch):
    dataset = _StaleCountDataset()

    result = _get_metrics(monkeypatch, dataset, refresh=False)

    assert dataset.compute_calls == []
    assert result["refreshed"] is False
    assert _value(result, "records:COUNT_RECORDS") == "100"
    assert result["stale_metric_ids"] == ["records:COUNT_RECORDS"]


def test_failed_recompute_falls_back_to_flagged_stored_values(monkeypatch):
    dataset = _StaleCountDataset(compute_error=RuntimeError("Action forbidden"))

    result = _get_metrics(monkeypatch, dataset)

    assert result["refreshed"] is False
    assert result["refresh_error"] == "Action forbidden"
    assert _value(result, "records:COUNT_RECORDS") == "100"
    assert result["stale_metric_ids"] == ["records:COUNT_RECORDS"]


def test_engine_failure_inside_the_report_is_not_treated_as_fresh(monkeypatch):
    dataset = _StaleCountDataset(engine_error="Connection refused")

    result = _get_metrics(monkeypatch, dataset)

    assert result["refreshed"] is False
    assert result["refresh_error"] == "SQL: Connection refused"
    assert result["stale_metric_ids"] == ["records:COUNT_RECORDS"]


@pytest.mark.parametrize("last_build_start", [None, 0])
def test_never_built_datasets_have_no_staleness_reference(last_build_start):
    metrics = [_metric("records:COUNT_RECORDS", "100", OLD_COUNT_TIME)]

    assert stale_metric_ids(metrics, last_build_start) == []
