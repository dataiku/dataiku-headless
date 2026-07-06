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
    parsed = json.loads(result.output)
    assert parsed["id"] == "insight1"
    assert parsed["type"] == "chart"


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
        # the "_" after the id is load-bearing: a bare id (and a trailing
        # slash) 404 in the DSS UI
        "url": (
            "https://dss.example.com/projects/PROJ1"
            "/dashboards/insights/new_insight_1_/view"
        ),
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

    # Build chart def with column refs; measures are SUMs, so their columns
    # get a numeric storage type in the schema below (SUM on a non-numeric
    # column is itself a render failure the linter flags).
    measure_cols = set(chart_columns.get("measures", []))
    chart_def = {
        "type": "lines",
        "genericDimension0": [
            {"column": c, "type": "ALPHANUM"} for c in chart_columns.get("dim0", [])
        ],
        "genericDimension1": [
            {"column": c, "type": "ALPHANUM"} for c in chart_columns.get("dim1", [])
        ],
        "genericMeasures": [
            {"column": c, "function": "SUM", "type": "NUMERICAL"}
            for c in chart_columns.get("measures", [])
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

    # Dataset schema: measure columns are numeric, the rest strings
    ds_mock = MagicMock()
    ds_mock.get_definition.return_value = {
        "schema": {
            "columns": [
                {"name": c, "type": "double" if c in measure_cols else "string"}
                for c in schema_columns
            ]
        },
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
    assert "passes pre-flight" in result.output
    assert "2 column ref(s) valid" in result.output


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


def _mk_chart(patch_client, chart_def, schema_columns):
    """Set up a chart insight with an arbitrary def + schema (cols may be
    dicts with type/meaning, or bare name strings)."""
    proj = patch_client.get_project("PROJ1")
    settings = MagicMock()
    settings.get_raw.return_value = {
        "id": "insight1",
        "name": "C",
        "type": "chart",
        "params": {
            "datasetSmartName": "sales",
            "def": chart_def,
            "refreshableSelection": {"selection": {"samplingMethod": "FULL"}},
        },
    }
    insight_mock = MagicMock()
    insight_mock.get_settings.return_value = settings
    proj.get_insight.return_value = insight_mock
    cols = [{"name": c} if isinstance(c, str) else c for c in schema_columns]
    ds_mock = MagicMock()
    ds_mock.get_definition.return_value = {"schema": {"columns": cols}}
    proj.get_dataset.return_value = ds_mock
    return proj


def test_insight_validate_empty_required_slot(patch_client):
    # binned_xy reads xDimension/yDimension — an empty xDimension renders AIOOBE
    _mk_chart(
        patch_client,
        {"type": "binned_xy", "xDimension": [], "yDimension": [{"column": "revenue"}]},
        ["units", "revenue"],
    )
    result = runner.invoke(app, ["insight", "validate", "insight1", "-P", "PROJ1"])
    assert result.exit_code == 1
    assert "xDimension" in result.output


def test_insight_validate_nulled_type(patch_client):
    _mk_chart(
        patch_client,
        {"type": "bubble", "uaXDimension": [{"column": "units"}]},
        ["units", "revenue"],
    )
    result = runner.invoke(app, ["insight", "validate", "insight1", "-P", "PROJ1"])
    assert result.exit_code == 1
    assert "nulled" in result.output
    assert "scatter" in result.output


def test_insight_validate_geo_missing_meaning(patch_client):
    # scatter_map with a geometry column that has no geo meaning builds empty
    _mk_chart(
        patch_client,
        {
            "type": "admin_map",
            "geometry": [{"column": "geopoint"}],
            "colorMeasure": [{"column": "revenue"}],
        },
        [{"name": "geopoint", "type": "string"}, {"name": "revenue", "type": "double"}],
    )
    result = runner.invoke(app, ["insight", "validate", "insight1", "-P", "PROJ1"])
    assert result.exit_code == 1
    assert "geo meaning" in result.output


def test_insight_validate_geo_with_meaning_passes(patch_client):
    _mk_chart(
        patch_client,
        {
            "type": "admin_map",
            "geometry": [{"column": "geopoint"}],
            "colorMeasure": [{"column": "revenue"}],
        },
        [
            {"name": "geopoint", "type": "string", "meaning": "GeoPoint"},
            {"name": "revenue", "type": "double"},
        ],
    )
    result = runner.invoke(app, ["insight", "validate", "insight1", "-P", "PROJ1"])
    assert result.exit_code == 0
    assert "passes pre-flight" in result.output


# ── measure/dimension type coherence ──
# The pivot engine reads an omitted/unknown `type` as NUMERICAL, and any
# NUMERICAL/DATE binding on a non-numeric column fails at render time with
# "Column X was expected to be NUMERICAL but is not (found STRING_DICT)".

_TYPED_SCHEMA = [
    {"name": "model_id", "type": "string"},
    {"name": "release_status", "type": "string"},
    {"name": "materiality_score", "type": "double"},
]


def _status_dim():
    return {"column": "release_status", "type": "ALPHANUM"}


def test_insight_validate_numerical_measure_on_string_column(patch_client):
    # the exact incident shape: COUNT typed NUMERICAL on a string column,
    # saved via set-definition, previously passed validate and broke at render
    _mk_chart(
        patch_client,
        {
            "type": "grouped_columns",
            "genericDimension0": [_status_dim()],
            "genericMeasures": [
                {"column": "model_id", "function": "COUNT", "type": "NUMERICAL"}
            ],
        },
        _TYPED_SCHEMA,
    )
    result = runner.invoke(app, ["insight", "validate", "insight1", "-P", "PROJ1"])
    assert result.exit_code == 1
    assert "NUMERICAL" in result.output
    assert "STRING_DICT" in result.output
    assert 'set "type": "ALPHANUM"' in result.output


def test_insight_validate_omitted_measure_type_on_string_column(patch_client):
    _mk_chart(
        patch_client,
        {
            "type": "grouped_columns",
            "genericDimension0": [_status_dim()],
            "genericMeasures": [{"column": "model_id", "function": "COUNT"}],
        },
        _TYPED_SCHEMA,
    )
    result = runner.invoke(app, ["insight", "validate", "insight1", "-P", "PROJ1"])
    assert result.exit_code == 1
    assert "omitted" in result.output


def test_insight_validate_pseudo_type_count_with_column(patch_client):
    # "type": "COUNT" is only valid on the column-less count-of-records
    # measure; with a column DSS reads it as NUMERICAL and render fails
    _mk_chart(
        patch_client,
        {
            "type": "grouped_columns",
            "genericDimension0": [_status_dim()],
            "genericMeasures": [
                {"column": "model_id", "function": "COUNT", "type": "COUNT"}
            ],
        },
        _TYPED_SCHEMA,
    )
    result = runner.invoke(app, ["insight", "validate", "insight1", "-P", "PROJ1"])
    assert result.exit_code == 1
    assert "unknown type 'COUNT'" in result.output


def test_insight_validate_count_of_records_passes(patch_client):
    _mk_chart(
        patch_client,
        {
            "type": "grouped_columns",
            "genericDimension0": [_status_dim()],
            "genericMeasures": [
                {"function": "COUNT", "type": "COUNT", "isA": "measure"}
            ],
        },
        _TYPED_SCHEMA,
    )
    result = runner.invoke(app, ["insight", "validate", "insight1", "-P", "PROJ1"])
    assert result.exit_code == 0
    assert "passes pre-flight" in result.output


def test_insight_validate_count_alphanum_on_string_passes(patch_client):
    _mk_chart(
        patch_client,
        {
            "type": "grouped_columns",
            "genericDimension0": [_status_dim()],
            "genericMeasures": [
                {"column": "model_id", "function": "COUNT", "type": "ALPHANUM"}
            ],
        },
        _TYPED_SCHEMA,
    )
    result = runner.invoke(app, ["insight", "validate", "insight1", "-P", "PROJ1"])
    assert result.exit_code == 0
    assert "passes pre-flight" in result.output


def test_insight_validate_sum_on_string_column(patch_client):
    # numeric-only aggregations fail on string columns regardless of declared
    # type ("Cannot sum non numeric values") — the set-definition escape hatch
    # around add-measure's own guard
    _mk_chart(
        patch_client,
        {
            "type": "grouped_columns",
            "genericDimension0": [_status_dim()],
            "genericMeasures": [
                {"column": "model_id", "function": "SUM", "type": "ALPHANUM"}
            ],
        },
        _TYPED_SCHEMA,
    )
    result = runner.invoke(app, ["insight", "validate", "insight1", "-P", "PROJ1"])
    assert result.exit_code == 1
    assert "SUM(model_id)" in result.output
    assert "not numeric" in result.output


def test_insight_validate_dimension_numerical_on_string_column(patch_client):
    # dimensions go through the same engine check ("In dimension: ...")
    _mk_chart(
        patch_client,
        {
            "type": "grouped_columns",
            "genericDimension0": [{"column": "model_id", "type": "NUMERICAL"}],
            "genericMeasures": [
                {"function": "COUNT", "type": "COUNT", "isA": "measure"}
            ],
        },
        _TYPED_SCHEMA,
    )
    result = runner.invoke(app, ["insight", "validate", "insight1", "-P", "PROJ1"])
    assert result.exit_code == 1
    assert "genericDimension0" in result.output


def test_insight_validate_treat_as_alphanum_passes(patch_client):
    # TREAT_AS_ALPHANUM converts the binding to ALPHANUM client-side before
    # the request — no render failure, so no lint error
    _mk_chart(
        patch_client,
        {
            "type": "grouped_columns",
            "genericDimension0": [
                {
                    "column": "model_id",
                    "type": "NUMERICAL",
                    "numParams": {"mode": "TREAT_AS_ALPHANUM"},
                }
            ],
            "genericMeasures": [
                {"function": "COUNT", "type": "COUNT", "isA": "measure"}
            ],
        },
        _TYPED_SCHEMA,
    )
    result = runner.invoke(app, ["insight", "validate", "insight1", "-P", "PROJ1"])
    assert result.exit_code == 0


def _scatter_axes():
    return {
        "uaXDimension": [{"column": "materiality_score", "type": "NUMERICAL"}],
        "uaYDimension": [{"column": "materiality_score", "type": "NUMERICAL"}],
    }


def test_insight_validate_ua_treat_as_alphanum_passes(patch_client):
    # ua slots carry their "treat as text" switch as a boolean on the binding,
    # not in numParams — the request goes out as ALPHANUM
    _mk_chart(
        patch_client,
        {
            "type": "scatter",
            "uaXDimension": [
                {
                    "column": "model_id",
                    "type": "NUMERICAL",
                    "treatAsAlphanum": True,
                }
            ],
            "uaYDimension": _scatter_axes()["uaYDimension"],
        },
        _TYPED_SCHEMA,
    )
    result = runner.invoke(app, ["insight", "validate", "insight1", "-P", "PROJ1"])
    assert result.exit_code == 0


def test_insight_validate_ua_numparams_treat_does_not_exempt(patch_client):
    # numParams.mode is ignored on ua slots — only the treatAsAlphanum boolean
    # converts the request to ALPHANUM, so this still fails at render
    _mk_chart(
        patch_client,
        {
            "type": "scatter",
            "uaXDimension": [
                {
                    "column": "model_id",
                    "type": "NUMERICAL",
                    "numParams": {"mode": "TREAT_AS_ALPHANUM"},
                }
            ],
            "uaYDimension": _scatter_axes()["uaYDimension"],
        },
        _TYPED_SCHEMA,
    )
    result = runner.invoke(app, ["insight", "validate", "insight1", "-P", "PROJ1"])
    assert result.exit_code == 1
    assert "uaXDimension" in result.output


def test_insight_validate_ua_shape_any_type_passes(patch_client):
    # uaShape is forced ALPHANUM before the request — never type-checked
    _mk_chart(
        patch_client,
        {
            "type": "scatter",
            **_scatter_axes(),
            "uaShape": [{"column": "model_id", "type": "NUMERICAL"}],
        },
        _TYPED_SCHEMA,
    )
    result = runner.invoke(app, ["insight", "validate", "insight1", "-P", "PROJ1"])
    assert result.exit_code == 0


def test_insight_validate_ua_tooltip_numerical_on_string(patch_client):
    # tooltip columns ride in the same request — a bad one breaks the chart
    _mk_chart(
        patch_client,
        {
            "type": "scatter",
            **_scatter_axes(),
            "uaTooltip": [{"column": "model_id", "type": "NUMERICAL"}],
        },
        _TYPED_SCHEMA,
    )
    result = runner.invoke(app, ["insight", "validate", "insight1", "-P", "PROJ1"])
    assert result.exit_code == 1
    assert "uaTooltip" in result.output


def test_insight_validate_boxplot_value_string_fails(patch_client):
    # ALPHANUM passes the engine type check but the boxplot computation
    # itself needs doubles — HTTP 500 at render
    _mk_chart(
        patch_client,
        {
            "type": "boxplots",
            "boxplotValue": [{"column": "model_id", "type": "ALPHANUM"}],
        },
        _TYPED_SCHEMA,
    )
    result = runner.invoke(app, ["insight", "validate", "insight1", "-P", "PROJ1"])
    assert result.exit_code == 1
    assert "boxplots need a numeric" in result.output


def test_insight_validate_boxplot_value_numerical_on_string(patch_client):
    # same failure class whatever the declared type — the fix is a different
    # column, not a different type string
    _mk_chart(
        patch_client,
        {
            "type": "boxplots",
            "boxplotValue": [{"column": "model_id", "type": "NUMERICAL"}],
        },
        _TYPED_SCHEMA,
    )
    result = runner.invoke(app, ["insight", "validate", "insight1", "-P", "PROJ1"])
    assert result.exit_code == 1
    assert "boxplots need a numeric" in result.output


def test_insight_validate_boxplot_breakdown_numerical_on_string(patch_client):
    _mk_chart(
        patch_client,
        {
            "type": "boxplots",
            "boxplotValue": [{"column": "materiality_score", "type": "NUMERICAL"}],
            "boxplotBreakdownDim": [{"column": "model_id", "type": "NUMERICAL"}],
        },
        _TYPED_SCHEMA,
    )
    result = runner.invoke(app, ["insight", "validate", "insight1", "-P", "PROJ1"])
    assert result.exit_code == 1
    assert "boxplotBreakdownDim" in result.output


def test_insight_validate_count_sentinel_not_flagged(patch_client):
    # "__COUNT__" is the GUI palette's count-of-records pseudo-column — not a
    # real column, never type-checked, must not be reported as missing
    _mk_chart(
        patch_client,
        {
            "type": "grouped_columns",
            "genericDimension0": [_status_dim()],
            "genericMeasures": [{"column": "__COUNT__", "function": "COUNT"}],
        },
        _TYPED_SCHEMA,
    )
    result = runner.invoke(app, ["insight", "validate", "insight1", "-P", "PROJ1"])
    assert result.exit_code == 0


def test_insight_validate_bad_column_in_ua_slot(patch_client):
    # column refs in ua* slots are checked too (old validate only saw generic*)
    _mk_chart(
        patch_client,
        {
            "type": "scatter",
            "uaXDimension": [{"column": "untis"}],
            "uaYDimension": [{"column": "revenue"}],
        },
        ["units", "revenue"],
    )
    result = runner.invoke(app, ["insight", "validate", "insight1", "-P", "PROJ1"])
    assert result.exit_code == 1
    assert "untis" in result.output
    assert "units" in result.output  # fuzzy suggestion


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
    [dim] = raw["params"]["def"]["genericDimension0"]
    # Full GUI shape — bare {column} dims crash the chart editor (numParams/sort
    # TypeErrors); no "type" here because the mock has no dataset binding.
    assert dim["column"] == "order_date"
    assert dim["isA"] == "dimension"
    assert dim["sort"] == {
        "type": "NATURAL",
        "sortAscending": True,
        "label": "Natural ordering",
    }
    assert dim["numParams"]["mode"] == "FIXED_NB"
    assert dim["filters"] == []
    settings.save.assert_called_once()


def test_insight_add_dimension_slot1(patch_client):
    raw, _settings = _chart_insight_mock(patch_client)
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
    [dim] = raw["params"]["def"]["genericDimension1"]
    assert dim["column"] == "region"
    assert dim["isA"] == "dimension"


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
        {"column": "revenue", "function": "SUM", "isA": "measure", "displayed": True}
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
        {
            "column": "customer_id",
            "function": "COUNTD",
            "isA": "measure",
            "displayed": True,
        }
    ]
    settings.save.assert_called_once()


def test_insight_add_measure_count_of_records(patch_client):
    """--agg COUNT with no --column emits the column-less 'Count of records'
    measure — the one shape the pivot engine never type-checks."""
    raw, settings = _chart_insight_mock(patch_client)
    result = runner.invoke(
        app,
        ["insight", "add-measure", "insight1", "--agg", "COUNT", "-P", "PROJ1"],
    )
    assert result.exit_code == 0
    assert raw["params"]["def"]["genericMeasures"] == [
        {"function": "COUNT", "type": "COUNT", "isA": "measure", "displayed": True}
    ]
    assert "count of records" in result.output
    settings.save.assert_called_once()


def test_insight_add_measure_no_column_requires_count(patch_client):
    _chart_insight_mock(patch_client)
    result = runner.invoke(
        app,
        ["insight", "add-measure", "insight1", "--agg", "SUM", "-P", "PROJ1"],
    )
    assert result.exit_code != 0
    assert "COUNT" in result.output


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
        app, ["insight", "clear-columns", "insight1", "--project", "PROJ1", "--yes"]
    )
    assert result.exit_code == 0
    assert raw["params"]["def"]["genericDimension0"] == []
    assert raw["params"]["def"]["genericDimension1"] == []
    assert raw["params"]["def"]["genericMeasures"] == []
    settings.save.assert_called_once()


def test_insight_clear_columns_blocks_without_yes(patch_client):
    raw, settings = _chart_insight_mock(patch_client)
    raw["params"]["def"]["genericDimension0"] = [{"column": "date"}]

    result = runner.invoke(
        app, ["insight", "clear-columns", "insight1", "--project", "PROJ1"]
    )
    assert result.exit_code == 77
    assert raw["params"]["def"]["genericDimension0"] == [{"column": "date"}]
    settings.save.assert_not_called()


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
    raw, _settings = _bound_chart_with_schema(patch_client)
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
        {
            "column": "revenue",
            "function": "SUM",
            "type": "NUMERICAL",
            "isA": "measure",
            "displayed": True,
        }
    ]


def test_insight_add_measure_countd_on_string_types_alphanum(patch_client):
    """COUNTD on a string column must carry type ALPHANUM — an omitted type is
    treated as NUMERICAL and fails at render ("found STRING_DICT")."""
    raw, _settings = _bound_chart_with_schema(patch_client)
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
        {
            "column": "declaration_id",
            "function": "COUNTD",
            "type": "ALPHANUM",
            "isA": "measure",
            "displayed": True,
        }
    ]


def test_insight_add_measure_blocks_numeric_agg_on_string(patch_client):
    _raw, settings = _bound_chart_with_schema(patch_client)
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
    _raw, settings = _bound_chart_with_schema(patch_client)
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
    raw, _settings = _bound_chart_with_schema(patch_client)
    result = runner.invoke(
        app,
        ["insight", "add-dimension", "insight1", "-c", "order_date", "-P", "PROJ1"],
    )
    assert result.exit_code == 0
    [dim] = raw["params"]["def"]["genericDimension0"]
    assert dim["column"] == "order_date"
    assert dim["type"] == "DATE"
    assert dim["isA"] == "dimension"


# --- new helper flags: --breakdown / --date-mode / --axis / --as / set-colors ---


def test_add_dimension_breakdown_goes_to_dim1(patch_client):
    raw, _settings = _bound_chart_with_schema(patch_client)
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
