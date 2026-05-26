"""Tests for insight commands."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

from typer.testing import CliRunner

from dku_cli.main import app

runner = CliRunner()


def test_insight_list(patch_client):
    result = runner.invoke(app, ["insight", "list", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "insight1" in result.output


def test_insight_list_json(patch_client):
    result = runner.invoke(app, ["insight", "list", "--project", "PROJ1", "-o", "json"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed[0]["id"] == "insight1"
    assert parsed[0]["type"] == "chart"


def test_insight_get(patch_client):
    result = runner.invoke(app, ["insight", "get", "insight1", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "insight1" in result.output


def test_insight_get_json(patch_client):
    result = runner.invoke(
        app, ["insight", "get", "insight1", "--project", "PROJ1", "-o", "json"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["id"] == "insight1"
    assert parsed["type"] == "chart"


def test_insight_create(patch_client):
    result = runner.invoke(
        app, ["insight", "create", "My Insight", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    assert "Created insight" in result.output
    assert "new_insight_1" in result.output
    proj = patch_client.get_project("PROJ1")
    proj.create_insight.assert_called_once_with(
        {"type": "dataset_table", "name": "My Insight"}
    )


def test_insight_create_json(patch_client):
    result = runner.invoke(
        app, ["insight", "create", "My Insight", "--project", "PROJ1", "-o", "json"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed == {
        "id": "new_insight_1",
        "name": "My Insight",
        "type": "dataset_table",
    }


def test_insight_create_with_type(patch_client):
    result = runner.invoke(
        app,
        ["insight", "create", "My Chart", "--project", "PROJ1", "--type", "chart"],
    )
    assert result.exit_code == 0
    proj = patch_client.get_project("PROJ1")
    proj.create_insight.assert_called_once_with({"type": "chart", "name": "My Chart"})


def test_insight_create_with_dataset(patch_client):
    result = runner.invoke(
        app,
        [
            "insight",
            "create",
            "My Chart",
            "--project",
            "PROJ1",
            "--type",
            "chart",
            "--dataset",
            "sales_monthly",
        ],
    )
    assert result.exit_code == 0
    proj = patch_client.get_project("PROJ1")
    call_args = proj.create_insight.call_args[0][0]
    assert call_args["type"] == "chart"
    assert call_args["params"]["datasetSmartName"] == "sales_monthly"


def test_insight_create_dataset_with_definition(patch_client):
    """--dataset should set datasetSmartName even when --definition is provided."""
    defn = json.dumps({"type": "chart", "params": {"engineType": "LINO"}})
    result = runner.invoke(
        app,
        [
            "insight",
            "create",
            "My Chart",
            "--project",
            "PROJ1",
            "--dataset",
            "forecast",
            "--definition",
            defn,
        ],
    )
    assert result.exit_code == 0
    proj = patch_client.get_project("PROJ1")
    call_args = proj.create_insight.call_args[0][0]
    assert call_args["params"]["datasetSmartName"] == "forecast"
    assert call_args["params"]["engineType"] == "LINO"


def test_insight_create_with_definition(patch_client):
    defn = json.dumps({"type": "chart", "name": "Custom", "chartDef": {"type": "bars"}})
    result = runner.invoke(
        app,
        ["insight", "create", "Custom", "--project", "PROJ1", "--definition", defn],
    )
    assert result.exit_code == 0
    proj = patch_client.get_project("PROJ1")
    call_args = proj.create_insight.call_args[0][0]
    assert call_args["type"] == "chart"
    assert call_args["chartDef"] == {"type": "bars"}


def test_insight_create_if_not_exists(patch_client):
    proj = patch_client.get_project("PROJ1")
    proj.create_insight.side_effect = Exception("409 Conflict: insight already exists")
    result = runner.invoke(
        app,
        ["insight", "create", "Existing", "--project", "PROJ1", "--if-not-exists"],
    )
    assert result.exit_code == 0
    assert "already exists" in result.output


def test_insight_create_already_exists_fails(patch_client):
    proj = patch_client.get_project("PROJ1")
    proj.create_insight.side_effect = Exception("409 Conflict: insight already exists")
    result = runner.invoke(
        app,
        ["insight", "create", "Existing", "--project", "PROJ1"],
    )
    assert result.exit_code != 0


def test_insight_delete(patch_client):
    result = runner.invoke(
        app, ["insight", "delete", "insight1", "--project", "PROJ1", "--yes"]
    )
    assert result.exit_code == 0
    assert "Deleted insight" in result.output
    proj = patch_client.get_project("PROJ1")
    insight = proj.get_insight("insight1")
    insight.delete.assert_called_once()


def test_insight_get_definition(patch_client):
    result = runner.invoke(
        app, ["insight", "get-definition", "insight1", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["id"] == "insight1"
    assert parsed["type"] == "chart"


def test_insight_set_definition(patch_client):
    new_def = json.dumps(
        {"id": "insight1", "name": "Updated", "type": "chart", "params": {"x": 1}}
    )
    result = runner.invoke(
        app,
        [
            "insight",
            "set-definition",
            "insight1",
            "--project",
            "PROJ1",
            "--definition",
            new_def,
        ],
    )
    assert result.exit_code == 0
    assert "Updated definition" in result.output
    proj = patch_client.get_project("PROJ1")
    insight = proj.get_insight("insight1")
    insight.get_settings().save.assert_called_once()


def test_insight_set_definition_from_file(tmp_path, patch_client):
    defn_file = tmp_path / "insight_def.json"
    defn_file.write_text(
        json.dumps({"id": "insight1", "name": "FromFile", "type": "chart"})
    )
    result = runner.invoke(
        app,
        [
            "insight",
            "set-definition",
            "insight1",
            "--project",
            "PROJ1",
            "--definition",
            f"@{defn_file}",
        ],
    )
    assert result.exit_code == 0
    assert "Updated definition" in result.output
    proj = patch_client.get_project("PROJ1")
    insight = proj.get_insight("insight1")
    insight.get_settings().save.assert_called_once()


# --- validate command tests ---


def _setup_chart_insight(
    patch_client, chart_columns, schema_columns, insight_type="chart"
):
    """Helper to configure mocks for validate tests."""
    proj = patch_client.get_project("PROJ1")

    # Build chart def with column refs
    chart_def = {
        "type": "lines",
        "genericDimension0": [
            {"column": c, "type": "ALPHANUM"} for c in chart_columns.get("dim0", [])
        ],
        "genericDimension1": [
            {"column": c, "type": "ALPHANUM"} for c in chart_columns.get("dim1", [])
        ],
        "genericMeasures": [
            {"column": c, "function": "SUM"} for c in chart_columns.get("measures", [])
        ],
    }

    insight_settings = MagicMock()
    insight_settings.get_raw.return_value = {
        "id": "insight1",
        "name": "Test Chart",
        "type": insight_type,
        "params": {
            "datasetSmartName": "sales",
            "def": chart_def,
        },
    }
    insight_mock = MagicMock()
    insight_mock.get_settings.return_value = insight_settings
    proj.get_insight.return_value = insight_mock

    # Dataset schema
    ds_mock = MagicMock()
    ds_mock.get_definition.return_value = {
        "schema": {"columns": [{"name": c} for c in schema_columns]},
    }
    proj.get_dataset.return_value = ds_mock

    return proj


def test_insight_validate_valid_columns(patch_client):
    _setup_chart_insight(
        patch_client,
        chart_columns={"dim0": ["month"], "measures": ["revenue"]},
        schema_columns=["month", "revenue", "product"],
    )
    result = runner.invoke(
        app, ["insight", "validate", "insight1", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    assert "2 column reference(s) valid" in result.output


def test_insight_validate_invalid_column_with_suggestion(patch_client):
    _setup_chart_insight(
        patch_client,
        chart_columns={"dim0": ["month"], "measures": ["revnue"]},
        schema_columns=["month", "revenue", "product"],
    )
    result = runner.invoke(
        app, ["insight", "validate", "insight1", "--project", "PROJ1"]
    )
    assert result.exit_code == 1
    assert "revnue" in result.output
    assert "revenue" in result.output


def test_insight_validate_missing_dataset_binding(patch_client):
    proj = patch_client.get_project("PROJ1")
    insight_settings = MagicMock()
    insight_settings.get_raw.return_value = {
        "id": "insight1",
        "name": "No Dataset",
        "type": "chart",
        "params": {},
    }
    insight_mock = MagicMock()
    insight_mock.get_settings.return_value = insight_settings
    proj.get_insight.return_value = insight_mock

    result = runner.invoke(
        app, ["insight", "validate", "insight1", "--project", "PROJ1"]
    )
    assert result.exit_code != 0
    assert "datasetSmartName" in result.output


def test_insight_validate_non_chart_type(patch_client):
    _setup_chart_insight(
        patch_client,
        chart_columns={"dim0": ["month"], "measures": ["revenue"]},
        schema_columns=["month", "revenue"],
        insight_type="dataset_table",
    )
    result = runner.invoke(
        app, ["insight", "validate", "insight1", "--project", "PROJ1"]
    )
    assert result.exit_code != 0
    assert "dataset_table" in result.output


# --- set-metadata ---


def test_insight_set_metadata_description(patch_client):
    result = runner.invoke(
        app,
        [
            "insight",
            "set-metadata",
            "insight1",
            "--description",
            "Monthly revenue chart",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "Updated metadata" in result.output
    insight = patch_client.get_project("PROJ1").get_insight("insight1")
    insight.get_settings().save.assert_called()


def test_insight_set_metadata_no_args(patch_client):
    result = runner.invoke(
        app, ["insight", "set-metadata", "insight1", "--project", "PROJ1"]
    )
    assert result.exit_code != 0


# --- list filters ---


def test_insight_list_filter_by_type(patch_client):
    result = runner.invoke(
        app, ["insight", "list", "--project", "PROJ1", "--type", "chart"]
    )
    assert result.exit_code == 0
    assert "insight1" in result.output


def test_insight_list_filter_by_type_no_match(patch_client):
    result = runner.invoke(
        app, ["insight", "list", "--project", "PROJ1", "--type", "report"]
    )
    assert result.exit_code == 0
    assert "insight1" not in result.output


def test_insight_list_filter_by_dataset(patch_client):
    proj = patch_client.get_project("PROJ1")
    insight_settings = MagicMock()
    insight_settings.get_raw.return_value = {
        "id": "insight1",
        "type": "chart",
        "params": {"datasetSmartName": "sales"},
    }
    insight_mock = MagicMock()
    insight_mock.get_settings.return_value = insight_settings
    proj.get_insight.return_value = insight_mock

    result = runner.invoke(
        app, ["insight", "list", "--project", "PROJ1", "--dataset", "sales"]
    )
    assert result.exit_code == 0
    assert "insight1" in result.output


def test_insight_list_filter_by_dataset_no_match(patch_client):
    proj = patch_client.get_project("PROJ1")
    insight_settings = MagicMock()
    insight_settings.get_raw.return_value = {
        "id": "insight1",
        "type": "chart",
        "params": {"datasetSmartName": "other_ds"},
    }
    insight_mock = MagicMock()
    insight_mock.get_settings.return_value = insight_settings
    proj.get_insight.return_value = insight_mock

    result = runner.invoke(
        app, ["insight", "list", "--project", "PROJ1", "--dataset", "sales"]
    )
    assert result.exit_code == 0
    assert "insight1" not in result.output


# --- head ---


def test_insight_head(patch_client):
    proj = patch_client.get_project("PROJ1")
    insight_settings = MagicMock()
    insight_settings.get_raw.return_value = {
        "id": "insight1",
        "type": "chart",
        "params": {"datasetSmartName": "sales"},
    }
    insight_mock = MagicMock()
    insight_mock.get_settings.return_value = insight_settings
    proj.get_insight.return_value = insight_mock

    result = runner.invoke(
        app, ["insight", "head", "insight1", "--project", "PROJ1", "-n", "3"]
    )
    assert result.exit_code == 0
    proj.get_dataset.assert_called_with("sales")


def test_insight_head_no_dataset_binding(patch_client):
    proj = patch_client.get_project("PROJ1")
    insight_settings = MagicMock()
    insight_settings.get_raw.return_value = {
        "id": "insight1",
        "type": "chart",
        "params": {},
    }
    insight_mock = MagicMock()
    insight_mock.get_settings.return_value = insight_settings
    proj.get_insight.return_value = insight_mock

    result = runner.invoke(app, ["insight", "head", "insight1", "--project", "PROJ1"])
    assert result.exit_code != 0
    assert "datasetSmartName" in result.output


# --- set-chart-type ---


def _chart_insight_mock(patch_client, chart_type="chart"):
    proj = patch_client.get_project("PROJ1")
    raw = {
        "id": "insight1",
        "type": chart_type,
        "params": {
            "def": {"type": "lines", "genericDimension0": [], "genericMeasures": []}
        },
    }
    insight_settings = MagicMock()
    insight_settings.get_raw.return_value = raw
    insight_mock = MagicMock()
    insight_mock.get_settings.return_value = insight_settings
    proj.get_insight.return_value = insight_mock
    return raw, insight_settings


def test_insight_set_chart_type(patch_client):
    raw, settings = _chart_insight_mock(patch_client)
    result = runner.invoke(
        app,
        [
            "insight",
            "set-chart-type",
            "insight1",
            "grouped_columns",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "grouped_columns" in result.output
    assert raw["params"]["def"]["type"] == "grouped_columns"
    settings.save.assert_called_once()


def test_insight_set_chart_type_invalid(patch_client):
    _chart_insight_mock(patch_client)
    result = runner.invoke(
        app, ["insight", "set-chart-type", "insight1", "donut", "--project", "PROJ1"]
    )
    assert result.exit_code != 0
    assert "donut" in result.output


def test_insight_set_chart_type_wrong_insight_type(patch_client):
    _chart_insight_mock(patch_client, chart_type="dataset_table")
    result = runner.invoke(
        app, ["insight", "set-chart-type", "insight1", "pie", "--project", "PROJ1"]
    )
    assert result.exit_code != 0
    assert "dataset_table" in result.output


# --- add-dimension ---


def test_insight_add_dimension(patch_client):
    raw, settings = _chart_insight_mock(patch_client)
    result = runner.invoke(
        app,
        [
            "insight",
            "add-dimension",
            "insight1",
            "--column",
            "order_date",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert raw["params"]["def"]["genericDimension0"] == [{"column": "order_date"}]
    settings.save.assert_called_once()


def test_insight_add_dimension_slot1(patch_client):
    raw, settings = _chart_insight_mock(patch_client)
    result = runner.invoke(
        app,
        [
            "insight",
            "add-dimension",
            "insight1",
            "--column",
            "region",
            "--slot",
            "1",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert raw["params"]["def"]["genericDimension1"] == [{"column": "region"}]


def test_insight_add_dimension_invalid_slot(patch_client):
    _chart_insight_mock(patch_client)
    result = runner.invoke(
        app,
        [
            "insight",
            "add-dimension",
            "insight1",
            "--column",
            "x",
            "--slot",
            "5",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code != 0


# --- add-measure ---


def test_insight_add_measure(patch_client):
    raw, settings = _chart_insight_mock(patch_client)
    result = runner.invoke(
        app,
        [
            "insight",
            "add-measure",
            "insight1",
            "--column",
            "revenue",
            "--agg",
            "SUM",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert raw["params"]["def"]["genericMeasures"] == [
        {"column": "revenue", "function": "SUM"}
    ]
    settings.save.assert_called_once()


def test_insight_add_measure_count_distinct_uses_dss_function_name(patch_client):
    raw, settings = _chart_insight_mock(patch_client)
    result = runner.invoke(
        app,
        [
            "insight",
            "add-measure",
            "insight1",
            "--column",
            "customer_id",
            "--agg",
            "COUNT_DISTINCT",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert raw["params"]["def"]["genericMeasures"] == [
        {"column": "customer_id", "function": "COUNTD"}
    ]
    settings.save.assert_called_once()


def test_insight_add_measure_invalid_agg(patch_client):
    _chart_insight_mock(patch_client)
    result = runner.invoke(
        app,
        [
            "insight",
            "add-measure",
            "insight1",
            "--column",
            "x",
            "--agg",
            "MEDIAN",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code != 0
    assert "MEDIAN" in result.output


# --- clear-columns ---


def test_insight_clear_columns(patch_client):
    raw, settings = _chart_insight_mock(patch_client)
    raw["params"]["def"]["genericDimension0"] = [{"column": "date"}]
    raw["params"]["def"]["genericMeasures"] = [{"column": "rev", "function": "SUM"}]

    result = runner.invoke(
        app, ["insight", "clear-columns", "insight1", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    assert raw["params"]["def"]["genericDimension0"] == []
    assert raw["params"]["def"]["genericDimension1"] == []
    assert raw["params"]["def"]["genericMeasures"] == []
    settings.save.assert_called_once()
