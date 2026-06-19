"""Tests for insight commands."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

from typer.testing import CliRunner

from dku_cli.main import app
from tests.helpers import strip_ansi

runner = CliRunner()


def test_insight_list(patch_client):
    result = runner.invoke(app, ["insight", "list", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "insight1" in result.output


def test_insight_list_json(patch_client):
    result = runner.invoke(
        app, ["--format", "json", "insight", "list", "--project", "PROJ1"]
    )
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
        app, ["--format", "json", "insight", "get", "insight1", "--project", "PROJ1"]
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
        app,
        ["--format", "json", "insight", "create", "My Insight", "--project", "PROJ1"],
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
    creation_info = proj.create_insight.call_args[0][0]
    assert creation_info["type"] == "chart"
    assert creation_info["name"] == "My Chart"
    # Charts always get a sampling block (DSS 14.6 NPEs without one).
    assert "refreshableSelection" in creation_info["params"]


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
    patch_client,
    chart_columns,
    schema_columns,
    insight_type="chart",
    include_sampling=True,
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

    params = {
        "datasetSmartName": "sales",
        "def": chart_def,
    }
    if include_sampling:
        params["refreshableSelection"] = {
            "selection": {"samplingMethod": "FULL", "maxRecords": 10000},
            "autoRefreshSample": False,
        }

    insight_settings = MagicMock()
    insight_settings.get_raw.return_value = {
        "id": "insight1",
        "name": "Test Chart",
        "type": insight_type,
        "params": params,
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
    # Invalid chart type is rejected at parse time by click.Choice (exit 2).
    assert result.exit_code == 2
    stripped = strip_ansi(result.output)
    assert "Invalid value" in stripped


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
    # Invalid aggregation is rejected at parse time by click.Choice (exit 2).
    assert result.exit_code == 2
    stripped = strip_ansi(result.output)
    assert "Invalid value" in stripped


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


# ── chart sampling defaults + column typing (DSS 14.6 NPE / COUNTD fixes) ──


def test_insight_create_chart_injects_refreshable_selection(patch_client):
    """Chart insights created without params.refreshableSelection NPE at
    render time on DSS 14.6 ("spec.sampleSettings is null", HTTP 500)."""
    result = runner.invoke(
        app,
        [
            "insight",
            "create",
            "Sales Chart",
            "-t",
            "chart",
            "--dataset",
            "sales",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    creation_info = patch_client.get_project("PROJ1").create_insight.call_args[0][0]
    sel = creation_info["params"]["refreshableSelection"]
    assert sel["selection"]["samplingMethod"] == "FULL"
    assert sel["selection"]["maxRecords"] == 10000


def test_insight_create_chart_keeps_caller_selection(patch_client):
    """A caller-provided refreshableSelection must not be overwritten."""
    definition = (
        '{"params": {"refreshableSelection": {"selection": {"samplingMethod": '
        '"HEAD_SEQUENTIAL", "maxRecords": 50}}}}'
    )
    result = runner.invoke(
        app,
        [
            "insight",
            "create",
            "Sales Chart",
            "-t",
            "chart",
            "-d",
            definition,
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    creation_info = patch_client.get_project("PROJ1").create_insight.call_args[0][0]
    sel = creation_info["params"]["refreshableSelection"]["selection"]
    assert sel["samplingMethod"] == "HEAD_SEQUENTIAL"


def test_insight_create_non_chart_no_selection_injected(patch_client):
    result = runner.invoke(
        app,
        [
            "insight",
            "create",
            "My Table",
            "-t",
            "dataset_table",
            "--dataset",
            "sales",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    creation_info = patch_client.get_project("PROJ1").create_insight.call_args[0][0]
    assert "refreshableSelection" not in creation_info.get("params", {})


def _bound_chart_with_schema(patch_client):
    raw, settings = _chart_insight_mock(patch_client)
    raw["params"]["datasetSmartName"] = "sales_ds"
    proj = patch_client.get_project("PROJ1")
    proj.get_dataset.return_value.get_schema.return_value = {
        "columns": [
            {"name": "revenue", "type": "double"},
            {"name": "declaration_id", "type": "string"},
            {"name": "order_date", "type": "date"},
        ]
    }
    return raw, settings


def test_insight_add_measure_types_numeric_column(patch_client):
    raw, settings = _bound_chart_with_schema(patch_client)
    result = runner.invoke(
        app,
        [
            "insight",
            "add-measure",
            "insight1",
            "-c",
            "revenue",
            "--agg",
            "SUM",
            "-P",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert raw["params"]["def"]["genericMeasures"] == [
        {"column": "revenue", "function": "SUM", "type": "NUMERICAL"}
    ]


def test_insight_add_measure_countd_on_string_types_alphanum(patch_client):
    """COUNTD on a string column must carry type ALPHANUM — an omitted type is
    treated as NUMERICAL and fails at render ("found STRING_DICT")."""
    raw, settings = _bound_chart_with_schema(patch_client)
    result = runner.invoke(
        app,
        [
            "insight",
            "add-measure",
            "insight1",
            "-c",
            "declaration_id",
            "--agg",
            "COUNT_DISTINCT",
            "-P",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert raw["params"]["def"]["genericMeasures"] == [
        {"column": "declaration_id", "function": "COUNTD", "type": "ALPHANUM"}
    ]


def test_insight_add_measure_blocks_numeric_agg_on_string(patch_client):
    raw, settings = _bound_chart_with_schema(patch_client)
    result = runner.invoke(
        app,
        [
            "insight",
            "add-measure",
            "insight1",
            "-c",
            "declaration_id",
            "--agg",
            "SUM",
            "-P",
            "PROJ1",
        ],
    )
    assert result.exit_code != 0
    assert "COUNT" in result.output  # prescriptive alternative offered
    settings.save.assert_not_called()


def test_insight_add_measure_unknown_column_lists_available(patch_client):
    raw, settings = _bound_chart_with_schema(patch_client)
    result = runner.invoke(
        app,
        [
            "insight",
            "add-measure",
            "insight1",
            "-c",
            "revnue",
            "--agg",
            "SUM",
            "-P",
            "PROJ1",
        ],
    )
    assert result.exit_code != 0
    assert "revenue" in result.output  # available columns listed
    settings.save.assert_not_called()


def test_insight_add_dimension_types_date_column(patch_client):
    raw, settings = _bound_chart_with_schema(patch_client)
    result = runner.invoke(
        app,
        ["insight", "add-dimension", "insight1", "-c", "order_date", "-P", "PROJ1"],
    )
    assert result.exit_code == 0
    assert raw["params"]["def"]["genericDimension0"] == [
        {"column": "order_date", "type": "DATE"}
    ]


# --- new helper flags: --breakdown / --date-mode / --axis / --as / set-colors ---


def test_add_dimension_breakdown_goes_to_dim1(patch_client):
    raw, settings = _bound_chart_with_schema(patch_client)
    result = runner.invoke(
        app,
        [
            "insight",
            "add-dimension",
            "insight1",
            "-c",
            "declaration_id",
            "--breakdown",
            "-P",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert [d["column"] for d in raw["params"]["def"]["genericDimension1"]] == [
        "declaration_id"
    ]
    assert raw["params"]["def"]["genericDimension0"] == []


def test_add_dimension_date_mode_bins(patch_client):
    raw, _ = _bound_chart_with_schema(patch_client)
    result = runner.invoke(
        app,
        [
            "insight",
            "add-dimension",
            "insight1",
            "-c",
            "order_date",
            "--date-mode",
            "MONTH",
            "-P",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    dim = raw["params"]["def"]["genericDimension0"][0]
    assert dim["type"] == "DATE"
    assert dim["dateParams"]["mode"] == "MONTH"


def test_add_dimension_dateonly_resolves_to_date(patch_client):
    # The bug fix: a `dateonly` storage column must resolve to chart type DATE
    # (it used to fall through to ALPHANUM). No --date-mode → no binning.
    raw, _ = _chart_insight_mock(patch_client)
    raw["params"]["datasetSmartName"] = "ds1"
    proj = patch_client.get_project("PROJ1")
    proj.get_dataset.return_value.get_schema.return_value = {
        "columns": [{"name": "d", "type": "dateonly"}]
    }
    result = runner.invoke(
        app, ["insight", "add-dimension", "insight1", "-c", "d", "-P", "PROJ1"]
    )
    assert result.exit_code == 0
    dim = raw["params"]["def"]["genericDimension0"][0]
    assert dim["type"] == "DATE"
    assert "dateParams" not in dim


def test_add_dimension_date_mode_invalid(patch_client):
    _bound_chart_with_schema(patch_client)
    result = runner.invoke(
        app,
        [
            "insight",
            "add-dimension",
            "insight1",
            "-c",
            "order_date",
            "--date-mode",
            "DECADE",
            "-P",
            "PROJ1",
        ],
    )
    assert result.exit_code != 0
    assert "date-mode" in result.output


def test_add_dimension_date_mode_on_non_date_warns(patch_client):
    raw, _ = _bound_chart_with_schema(patch_client)
    result = runner.invoke(
        app,
        [
            "insight",
            "add-dimension",
            "insight1",
            "-c",
            "declaration_id",
            "--date-mode",
            "MONTH",
            "-P",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0  # still adds it
    assert "ignored" in result.output
    assert "dateParams" not in raw["params"]["def"]["genericDimension0"][0]


def test_add_measure_axis2_as_line(patch_client):
    raw, _ = _bound_chart_with_schema(patch_client)
    result = runner.invoke(
        app,
        [
            "insight",
            "add-measure",
            "insight1",
            "-c",
            "revenue",
            "--agg",
            "SUM",
            "--axis",
            "2",
            "--as",
            "line",
            "-P",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    m = raw["params"]["def"]["genericMeasures"][0]
    assert m["displayAxis"] == "axis2"
    assert m["displayType"] == "line"


def test_add_measure_default_axis1(patch_client):
    raw, _ = _bound_chart_with_schema(patch_client)
    runner.invoke(
        app,
        [
            "insight",
            "add-measure",
            "insight1",
            "-c",
            "revenue",
            "--agg",
            "SUM",
            "-P",
            "PROJ1",
        ],
    )
    # axis1 is the implicit default — a plain measure keeps its minimal shape.
    assert "displayAxis" not in raw["params"]["def"]["genericMeasures"][0]


def test_add_measure_axis_invalid(patch_client):
    _bound_chart_with_schema(patch_client)
    result = runner.invoke(
        app,
        [
            "insight",
            "add-measure",
            "insight1",
            "-c",
            "revenue",
            "--axis",
            "3",
            "-P",
            "PROJ1",
        ],
    )
    assert result.exit_code != 0


def test_add_measure_as_invalid(patch_client):
    _bound_chart_with_schema(patch_client)
    result = runner.invoke(
        app,
        [
            "insight",
            "add-measure",
            "insight1",
            "-c",
            "revenue",
            "--as",
            "donut",
            "-P",
            "PROJ1",
        ],
    )
    assert result.exit_code != 0


def test_set_colors_category(patch_client):
    raw, settings = _bound_chart_with_schema(patch_client)
    result = runner.invoke(
        app,
        [
            "insight",
            "set-colors",
            "insight1",
            "--category",
            "EU=#2E5EAA",
            "--category",
            "US=#D1495B",
            "-P",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    co = raw["params"]["def"]["colorOptions"]
    assert co["customColors"] == {"EU": "#2E5EAA", "US": "#D1495B"}
    assert co["paletteType"] == "CATEGORY"
    settings.save.assert_called_once()


def test_set_colors_single_palette_transparency(patch_client):
    raw, _ = _bound_chart_with_schema(patch_client)
    runner.invoke(
        app,
        [
            "insight",
            "set-colors",
            "insight1",
            "--single",
            "#2678b2",
            "--palette",
            "pastel",
            "--transparency",
            "0.5",
            "-P",
            "PROJ1",
        ],
    )
    co = raw["params"]["def"]["colorOptions"]
    assert co["singleColor"] == "#2678b2"
    assert co["colorPalette"] == "pastel"
    assert co["transparency"] == 0.5


def test_set_colors_requires_an_option(patch_client):
    _bound_chart_with_schema(patch_client)
    result = runner.invoke(app, ["insight", "set-colors", "insight1", "-P", "PROJ1"])
    assert result.exit_code != 0
    assert "at least one" in result.output


def test_set_colors_bad_category_pair(patch_client):
    _bound_chart_with_schema(patch_client)
    result = runner.invoke(
        app,
        ["insight", "set-colors", "insight1", "--category", "EU", "-P", "PROJ1"],
    )
    assert result.exit_code != 0
    assert "VALUE=HEX" in result.output


# ── sampling-block guard: validate fails fast, set-definition self-heals ──


def test_insight_validate_fails_without_sampling_block(patch_client):
    """A chart with valid columns but no params.refreshableSelection cannot
    render (DSS 14.6 NPE) — validate must fail it, not report green."""
    _setup_chart_insight(
        patch_client,
        chart_columns={"dim0": ["month"], "measures": ["revenue"]},
        schema_columns=["month", "revenue"],
        include_sampling=False,
    )
    result = runner.invoke(
        app, ["insight", "validate", "insight1", "--project", "PROJ1"]
    )
    assert result.exit_code != 0
    assert "sampling block" in result.output
    assert "spec.sampleSettings" in result.output
    assert "set-definition" in result.output


def test_insight_validate_fails_on_empty_sampling_block(patch_client):
    """A refreshableSelection without a selection inside still NPEs."""
    proj = _setup_chart_insight(
        patch_client,
        chart_columns={"dim0": ["month"]},
        schema_columns=["month"],
        include_sampling=False,
    )
    raw = proj.get_insight.return_value.get_settings.return_value.get_raw.return_value
    raw["params"]["refreshableSelection"] = {"autoRefreshSample": False}
    result = runner.invoke(
        app, ["insight", "validate", "insight1", "--project", "PROJ1"]
    )
    assert result.exit_code != 0
    assert "sampling block" in result.output


def test_insight_set_definition_chart_injects_sampling_block(patch_client):
    new_def = json.dumps(
        {"id": "insight1", "name": "Chart", "type": "chart", "params": {"x": 1}}
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
    assert "Injected default sampling block" in result.output
    written = (
        patch_client.get_project("PROJ1")
        .get_insight("insight1")
        .get_settings()
        .get_raw()
    )
    assert (
        written["params"]["refreshableSelection"]["selection"]["samplingMethod"]
        == "FULL"
    )


def test_insight_set_definition_chart_keeps_caller_sampling_block(patch_client):
    new_def = json.dumps(
        {
            "type": "chart",
            "params": {
                "refreshableSelection": {
                    "selection": {"samplingMethod": "HEAD_SEQUENTIAL", "maxRecords": 50}
                }
            },
        }
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
    assert "Injected" not in result.output
    written = (
        patch_client.get_project("PROJ1")
        .get_insight("insight1")
        .get_settings()
        .get_raw()
    )
    sel = written["params"]["refreshableSelection"]["selection"]
    assert sel["samplingMethod"] == "HEAD_SEQUENTIAL"


def test_insight_set_definition_non_chart_untouched(patch_client):
    new_def = json.dumps({"type": "dataset_table", "params": {"shakerScript": {}}})
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
    assert "Injected" not in result.output
    written = (
        patch_client.get_project("PROJ1")
        .get_insight("insight1")
        .get_settings()
        .get_raw()
    )
    assert "refreshableSelection" not in written["params"]
