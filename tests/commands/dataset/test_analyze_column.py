"""Dataset command tests split from tests/commands/test_dataset.py."""

from __future__ import annotations

import json
from unittest.mock import MagicMock
from tests.commands.dataset.helpers import app, runner


# --- analyze-column ---


def _wire_worksheet(patch_client, raw_result, dataset_name="ds1"):
    """Configure create_statistics_worksheet → run_computation → get_raw()."""
    proj = patch_client.get_project("PROJ1")
    ds = proj.get_dataset(dataset_name)
    ws = MagicMock()
    result = MagicMock()
    result.get_raw.return_value = raw_result
    ws.run_computation.return_value = result
    ws.delete.return_value = None
    ds.create_statistics_worksheet.return_value = ws
    return ds, ws


def test_dataset_analyze_column_numeric(patch_client):
    raw = {
        "results": [
            {"type": "count", "count": 1000},
            {"type": "count_distinct", "count": 950},
            {
                "type": "grouped",
                "groups": {
                    "type": "anum",
                    "values": ["10", "20"],
                    "hasOthers": True,
                    "hasAllValues": False,
                },
                "results": [{"count": 300}, {"count": 200}],
            },
            {
                "type": "grouped",
                "groups": {"type": "subset", "filter": {"type": "missing"}},
                "results": [{"count": 50}],
            },
            {"type": "mean", "value": 42.5},
            {"type": "std_dev", "value": 7.25},
            {
                "type": "quantiles",
                "quantiles": [
                    {"freq": 0.0, "quantile": 1},
                    {"freq": 0.5, "quantile": 40},
                    {"freq": 1.0, "quantile": 99},
                ],
            },
        ]
    }
    _wire_worksheet(patch_client, raw)
    result = runner.invoke(
        app, ["dataset", "analyze-column", "ds1", "col2", "--project", "PROJ1"]
    )
    assert result.exit_code == 0, result.output
    assert "Column Analysis: ds1.col2" in result.output
    assert "1000" in result.output  # total rows
    assert "5.0%" in result.output  # null rate 50/1000
    assert "42.5" in result.output  # mean
    assert "Top 2 Values" in result.output


def test_dataset_analyze_column_numeric_json(patch_client):
    raw = {
        "results": [
            {"type": "count", "count": 200},
            {"type": "count_distinct", "count": 190},
            {
                "type": "grouped",
                "groups": {
                    "type": "anum",
                    "values": ["a"],
                    "hasOthers": False,
                    "hasAllValues": True,
                },
                "results": [{"count": 150}],
            },
            {
                "type": "grouped",
                "groups": {"type": "subset", "filter": {"type": "missing"}},
                "results": [{"count": 10}],
            },
            {"type": "mean", "value": 5.0},
        ]
    }
    _wire_worksheet(patch_client, raw)
    result = runner.invoke(
        app,
        [
            "dataset",
            "analyze-column",
            "ds1",
            "col2",
            "--project",
            "PROJ1",
            "-o",
            "json",
        ],
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["row_count"] == 200
    assert parsed["distinct_count"] == 190
    assert parsed["null_count"] == 10
    assert parsed["mean"] == 5.0
    assert parsed["top_values"][0] == {"value": "a", "count": 150}


def test_dataset_analyze_column_string_infers_zero_null(patch_client):
    # String column: full coverage (hasAllValues + top counts == total) → null 0.
    raw = {
        "results": [
            {"type": "count", "count": 100},
            {"type": "count_distinct", "count": 3},
            {
                "type": "grouped",
                "groups": {
                    "type": "anum",
                    "values": ["x", "y", "z"],
                    "hasOthers": False,
                    "hasAllValues": True,
                },
                "results": [{"count": 60}, {"count": 30}, {"count": 10}],
            },
        ]
    }
    _wire_worksheet(patch_client, raw)
    result = runner.invoke(
        app,
        [
            "dataset",
            "analyze-column",
            "ds1",
            "col1",
            "--project",
            "PROJ1",
            "-o",
            "json",
        ],
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["null_count"] == 0
    # Inference scratch keys are stripped from the string-column payload.
    assert "has_others" not in parsed
    assert "has_all_values" not in parsed


def test_dataset_analyze_column_not_found(patch_client):
    result = runner.invoke(
        app, ["dataset", "analyze-column", "ds1", "nonexistent", "--project", "PROJ1"]
    )
    assert result.exit_code != 0
    assert "Column 'nonexistent' not found" in result.output
    assert "dku dataset schema ds1" in result.output


def test_dataset_analyze_column_deletes_worksheet(patch_client):
    raw = {"results": [{"type": "count", "count": 5}]}
    _, ws = _wire_worksheet(patch_client, raw)
    result = runner.invoke(
        app, ["dataset", "analyze-column", "ds1", "col1", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    # Temp worksheet must be cleaned up even on the happy path.
    ws.delete.assert_called_once()
