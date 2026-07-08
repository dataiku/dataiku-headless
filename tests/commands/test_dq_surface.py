"""Tests for dq rule-types / rule-schema and col_stats probe auto-provisioning."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from dku_cli.commands.dq import (
    RULE_TEMPLATES,
    _ensure_col_stats_probe,
    _required_col_stats,
)
from dku_cli.main import app

runner = CliRunner()


# --- rule-types / rule-schema (#264) ---


def test_rule_types_lists_every_template():
    result = runner.invoke(app, ["dq", "rule-types"])
    assert result.exit_code == 0
    for type_id in RULE_TEMPLATES:
        assert type_id in result.output


def test_rule_types_json():
    result = runner.invoke(app, ["--format", "json", "dq", "rule-types"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert {row["type"] for row in parsed} == set(RULE_TEMPLATES)
    assert all(row["scope"] in ("dataset", "column") for row in parsed)


def test_rule_schema_emits_template_json():
    result = runner.invoke(app, ["dq", "rule-schema", "ValuesInSetRule"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["type"] == "ValuesInSetRule"
    assert parsed["valueSet"] == ["VALUE_1", "VALUE_2"]


def test_rule_schema_case_insensitive():
    result = runner.invoke(app, ["dq", "rule-schema", "recordcountinrangerule"])
    assert result.exit_code == 0
    assert json.loads(result.output)["type"] == "RecordCountInRangeRule"


def test_rule_schema_unknown_type_prescriptive():
    result = runner.invoke(app, ["dq", "rule-schema", "NopeRule"])
    assert result.exit_code != 0
    assert "dku dq rule-types" in result.output
    assert "RecordCountInRangeRule" in result.output


def test_templates_are_self_consistent():
    for type_id, (template, description) in RULE_TEMPLATES.items():
        assert template["type"] == type_id
        assert template.get("displayName")
        assert description
        if type_id.startswith("Drift"):
            drift = template["driftParams"]
            assert set(drift) == {
                "iqrFactor",
                "iqrFactorEnabled",
                "lookbackPeriod",
                "periodUnit",
                "softIqrFactor",
                "softIqrFactorEnabled",
                "learningPeriod",
            }
    assert (
        RULE_TEMPLATES["ColumnNotEmptyRule"][0]["thresholdType"]
        == "ENTIRE_COLUMN_NOT_EMPTY"
    )
    assert RULE_TEMPLATES["ColumnUniqueValuesRule"][0]["thresholdType"] == (
        "ENTIRE_COLUMN"
    )
    assert "columns" in RULE_TEMPLATES["DatasetSchemaEqualsRule"][0]["expectedSchema"]


# --- col_stats probe provisioning (#265) ---


class _FakeSettings:
    def __init__(self, raw):
        self._raw = raw
        self.saved = False

    def get_raw(self):
        return self._raw

    def save(self):
        self.saved = True


class _FakeDataset:
    def __init__(self, columns, raw_settings=None):
        self._columns = columns
        self.settings = _FakeSettings(raw_settings if raw_settings is not None else {})

    def get_schema(self):
        return {"columns": self._columns}

    def get_settings(self):
        return self.settings


def test_required_col_stats_derives_aggregates():
    rules = [
        {"type": "ColumnMinInRangeRule", "columns": ["a"], "enabled": True},
        {"type": "ColumnAvgInRangeRule", "columns": ["a", "b"]},
        {"type": "ColumnMaxInRangeRule", "columns": ["c"], "enabled": False},
        {"type": "RecordCountInRangeRule"},
    ]
    assert _required_col_stats(rules) == [("a", "MIN"), ("a", "AVG"), ("b", "AVG")]


def test_ensure_col_stats_probe_provisions_whole_dataset(capsys):
    ds = _FakeDataset([{"name": "score", "type": "bigint"}])
    _ensure_col_stats_probe(
        ds, [{"type": "ColumnMinInRangeRule", "columns": ["score"]}]
    )
    probes = ds.settings.get_raw()["metrics"]["probes"]
    assert len(probes) == 1
    probe = probes[0]
    assert probe["type"] == "col_stats"
    assert probe["computeOnBuildMode"] == "WHOLE_DATASET"
    assert probe["configuration"]["aggregates"] == [
        {"column": "score", "aggregated": "MIN"}
    ]
    assert ds.settings.saved


def test_ensure_col_stats_probe_merges_into_existing(capsys):
    raw = {
        "metrics": {
            "probes": [
                {
                    "type": "col_stats",
                    "enabled": True,
                    "computeOnBuildMode": "WHOLE_DATASET",
                    "configuration": {
                        "aggregates": [{"column": "score", "aggregated": "MIN"}]
                    },
                }
            ]
        }
    }
    ds = _FakeDataset([{"name": "score", "type": "double"}], raw)
    # Already provisioned → no save
    _ensure_col_stats_probe(
        ds, [{"type": "ColumnMinInRangeRule", "columns": ["score"]}]
    )
    assert not ds.settings.saved
    # New aggregate → merged, saved, no duplicate
    _ensure_col_stats_probe(
        ds, [{"type": "ColumnMaxInRangeRule", "columns": ["score"]}]
    )
    aggregates = raw["metrics"]["probes"][0]["configuration"]["aggregates"]
    assert aggregates == [
        {"column": "score", "aggregated": "MIN"},
        {"column": "score", "aggregated": "MAX"},
    ]
    assert ds.settings.saved


def test_ensure_col_stats_probe_skips_non_numeric_with_warning(capsys):
    ds = _FakeDataset(
        [{"name": "name", "type": "string"}, {"name": "score", "type": "int"}]
    )
    _ensure_col_stats_probe(
        ds,
        [
            {"type": "ColumnMinInRangeRule", "columns": ["name"]},
            {"type": "ColumnSumInRangeRule", "columns": ["score"]},
        ],
    )
    err = capsys.readouterr().err
    assert "Skipping col_stats MIN on 'name'" in err
    assert "string" in err
    aggregates = ds.settings.get_raw()["metrics"]["probes"][0]["configuration"][
        "aggregates"
    ]
    assert aggregates == [{"column": "score", "aggregated": "SUM"}]


def test_ensure_col_stats_probe_noop_without_metric_rules():
    ds = _FakeDataset([{"name": "score", "type": "int"}])
    _ensure_col_stats_probe(ds, [{"type": "RecordCountInRangeRule"}])
    assert ds.settings.get_raw() == {}
    assert not ds.settings.saved


def test_dq_compute_still_succeeds_with_mock(patch_client):
    result = runner.invoke(app, ["dq", "compute", "ds1", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "computed" in result.output
