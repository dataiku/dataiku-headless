"""Tests for dq (data quality) commands."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from dku_cli.main import app

runner = CliRunner()


# ── list ─────────────────────────────────────────────────────────────────


def test_dq_list_table(patch_client):
    result = runner.invoke(app, ["dq", "list", "ds1", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "rule1" in result.output
    assert "Record count" in result.output


def test_dq_list_json(patch_client):
    result = runner.invoke(
        app, ["dq", "list", "ds1", "--project", "PROJ1", "-o", "json"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert isinstance(parsed, list)
    assert len(parsed) == 2
    assert parsed[0]["id"] == "rule1"


def test_dq_list_env_project(patch_client, monkeypatch):
    monkeypatch.setenv("DKU_PROJECT", "PROJ1")
    result = runner.invoke(app, ["dq", "list", "ds1"])
    assert result.exit_code == 0


# ── create ───────────────────────────────────────────────────────────────


def test_dq_create_with_config(patch_client):
    config = json.dumps(
        {
            "type": "RecordCountInRangeRule",
            "softMinimum": 1,
            "softMinimumEnabled": True,
            "displayName": "Has records",
        }
    )
    result = runner.invoke(
        app, ["dq", "create", "ds1", "--config", config, "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    assert "Created rule" in result.output

    proj = patch_client.get_project("PROJ1")
    ds = proj.get_dataset("ds1")
    ruleset = ds.get_data_quality_rules()
    ruleset.create_rule.assert_called_once()


def test_dq_create_with_config_file(patch_client, tmp_path):
    config_file = tmp_path / "rule.json"
    config_file.write_text(
        json.dumps(
            {
                "type": "RecordCountInRangeRule",
                "softMinimum": 10,
                "softMinimumEnabled": True,
            }
        )
    )
    result = runner.invoke(
        app,
        ["dq", "create", "ds1", "--config", f"@{config_file}", "--project", "PROJ1"],
    )
    assert result.exit_code == 0
    assert "Created rule" in result.output


def test_dq_create_with_type_record_count(patch_client):
    result = runner.invoke(
        app,
        [
            "dq",
            "create",
            "ds1",
            "--type",
            "record-count",
            "--min",
            "1",
            "--name",
            "Has records",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "Created rule" in result.output

    proj = patch_client.get_project("PROJ1")
    ds = proj.get_dataset("ds1")
    ruleset = ds.get_data_quality_rules()
    call_args = ruleset.create_rule.call_args[0][0]
    assert call_args["type"] == "RecordCountInRangeRule"
    assert call_args["softMinimum"] == 1.0
    assert call_args["softMinimumEnabled"] is True


def test_dq_create_with_type_not_empty(patch_client):
    result = runner.invoke(
        app,
        [
            "dq",
            "create",
            "ds1",
            "--type",
            "not-empty",
            "--column",
            "CountryISO",
            "--name",
            "Country not blank",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0

    proj = patch_client.get_project("PROJ1")
    ds = proj.get_dataset("ds1")
    ruleset = ds.get_data_quality_rules()
    call_args = ruleset.create_rule.call_args[0][0]
    assert call_args["type"] == "ColumnNotEmptyRule"
    assert call_args["columns"] == ["CountryISO"]


def test_dq_create_with_type_not_empty_threshold(patch_client):
    """not-empty must set thresholdType=ENTIRE_COLUMN_NOT_EMPTY or compute fails."""
    result = runner.invoke(
        app,
        [
            "dq",
            "create",
            "ds1",
            "--type",
            "not-empty",
            "--column",
            "CountryISO",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0

    proj = patch_client.get_project("PROJ1")
    ds = proj.get_dataset("ds1")
    ruleset = ds.get_data_quality_rules()
    call_args = ruleset.create_rule.call_args[0][0]
    assert call_args["thresholdType"] == "ENTIRE_COLUMN_NOT_EMPTY"


def test_dq_create_with_type_column_count(patch_client):
    """column-count sets hard minimum/maximum bounds with their *Enabled flags."""
    result = runner.invoke(
        app,
        [
            "dq",
            "create",
            "ds1",
            "--type",
            "column-count",
            "--min",
            "6",
            "--max",
            "6",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "Created rule" in result.output

    proj = patch_client.get_project("PROJ1")
    ds = proj.get_dataset("ds1")
    ruleset = ds.get_data_quality_rules()
    call_args = ruleset.create_rule.call_args[0][0]
    assert call_args["type"] == "ColumnCountInRangeRule"
    assert call_args["minimum"] == 6.0
    assert call_args["minimumEnabled"] is True
    assert call_args["maximum"] == 6.0
    assert call_args["maximumEnabled"] is True


def test_dq_create_column_count_requires_min_or_max(patch_client):
    """column-count with neither --min nor --max exits with a prescriptive error."""
    result = runner.invoke(
        app,
        [
            "dq",
            "create",
            "ds1",
            "--type",
            "column-count",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code != 0
    assert "--min and/or --max is required" in result.output


def test_dq_create_with_type_value_in_range(patch_client):
    """value-in-range creates TWO rules: ColumnMinInRangeRule + ColumnMaxInRangeRule."""
    result = runner.invoke(
        app,
        [
            "dq",
            "create",
            "ds1",
            "--type",
            "value-in-range",
            "--column",
            "Latitude",
            "--min",
            "-90",
            "--max",
            "90",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0

    proj = patch_client.get_project("PROJ1")
    ds = proj.get_dataset("ds1")
    ruleset = ds.get_data_quality_rules()
    # Two rules created
    assert ruleset.create_rule.call_count == 2
    first_call = ruleset.create_rule.call_args_list[0][0][0]
    second_call = ruleset.create_rule.call_args_list[1][0][0]
    assert first_call["type"] == "ColumnMinInRangeRule"
    assert first_call["columns"] == ["Latitude"]
    assert first_call["softMinimum"] == -90.0
    assert second_call["type"] == "ColumnMaxInRangeRule"
    assert second_call["columns"] == ["Latitude"]
    assert second_call["softMaximum"] == 90.0


def test_dq_create_requires_config_or_type(patch_client):
    result = runner.invoke(app, ["dq", "create", "ds1", "--project", "PROJ1"])
    assert result.exit_code != 0


def test_dq_create_rejects_config_and_type(patch_client):
    result = runner.invoke(
        app,
        [
            "dq",
            "create",
            "ds1",
            "--config",
            '{"type":"RecordCountInRangeRule"}',
            "--type",
            "record-count",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code != 0


def test_dq_create_not_empty_requires_column(patch_client):
    result = runner.invoke(
        app,
        [
            "dq",
            "create",
            "ds1",
            "--type",
            "not-empty",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code != 0


def test_dq_create_not_empty(patch_client):
    """not-empty creates cleanly: the DSS 14.5 compute bug is worked around via
    thresholdType, so no bug warning is emitted."""
    result = runner.invoke(
        app,
        [
            "dq",
            "create",
            "ds1",
            "--type",
            "not-empty",
            "--column",
            "CountryISO",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "Created rule" in result.output
    assert "Known DSS 14.5 beta bug" not in result.output


def test_dq_create_not_empty_raw_config(patch_client):
    """ColumnNotEmptyRule via raw --config creates without a bug warning."""
    config = json.dumps(
        {
            "type": "ColumnNotEmptyRule",
            "columns": ["CountryISO"],
            "displayName": "Country not blank",
        }
    )
    result = runner.invoke(
        app, ["dq", "create", "ds1", "--config", config, "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    assert "Created rule" in result.output
    assert "Known DSS 14.5 beta bug" not in result.output


def test_dq_create_column_empty_raw_config(patch_client):
    """ColumnEmptyRule via raw --config creates without a bug warning."""
    config = json.dumps(
        {
            "type": "ColumnEmptyRule",
            "columns": ["OptionalField"],
        }
    )
    result = runner.invoke(
        app, ["dq", "create", "ds1", "--config", config, "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    assert "Created rule" in result.output
    assert "Known DSS 14.5 beta bug" not in result.output


def test_dq_create_record_count_no_warning(patch_client):
    """Non-buggy rule types should not emit the DSS 14.5 warning."""
    result = runner.invoke(
        app,
        [
            "dq",
            "create",
            "ds1",
            "--type",
            "record-count",
            "--min",
            "1",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "Known DSS 14.5 beta bug" not in result.output


# ── compute ──────────────────────────────────────────────────────────────


def test_dq_compute(patch_client):
    result = runner.invoke(app, ["dq", "compute", "ds1", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "computed" in result.output.lower()


def test_dq_compute_no_wait(patch_client):
    result = runner.invoke(
        app, ["dq", "compute", "ds1", "--no-wait", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    assert "started" in result.output.lower()


def test_dq_compute_single_rule(patch_client):
    result = runner.invoke(
        app, ["dq", "compute", "ds1", "--rule-id", "rule1", "--project", "PROJ1"]
    )
    assert result.exit_code == 0


# ── status ───────────────────────────────────────────────────────────────


def test_dq_status(patch_client):
    result = runner.invoke(app, ["dq", "status", "ds1", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "OK" in result.output


def test_dq_status_json(patch_client):
    result = runner.invoke(
        app, ["dq", "status", "ds1", "--project", "PROJ1", "-o", "json"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert "status" in parsed
    assert parsed["status"] == "OK"


# ── results ──────────────────────────────────────────────────────────────


def test_dq_results(patch_client):
    result = runner.invoke(app, ["dq", "results", "ds1", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "rule1" in result.output


def test_dq_results_json(patch_client):
    result = runner.invoke(
        app, ["dq", "results", "ds1", "--project", "PROJ1", "-o", "json"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert isinstance(parsed, list)
    assert parsed[0]["id"] == "rule1"


# ── delete ───────────────────────────────────────────────────────────────


def test_dq_delete_with_yes(patch_client):
    result = runner.invoke(
        app,
        ["dq", "delete", "ds1", "--rule-id", "rule1", "--yes", "--project", "PROJ1"],
    )
    assert result.exit_code == 0
    assert "Deleted" in result.output


def test_dq_delete_not_found(patch_client):
    result = runner.invoke(
        app,
        [
            "dq",
            "delete",
            "ds1",
            "--rule-id",
            "nonexistent",
            "--yes",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code != 0


# ── project-status ───────────────────────────────────────────────────────


def test_dq_project_status(patch_client):
    result = runner.invoke(app, ["dq", "project-status", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "ds1" in result.output


def test_dq_project_status_json(patch_client):
    result = runner.invoke(
        app, ["dq", "project-status", "--project", "PROJ1", "-o", "json"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert "ds1" in parsed
    assert parsed["ds1"]["status"] == "OK"
