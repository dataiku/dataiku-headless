"""Unit tests for the chart-type spec + pre-flight linter (dku_cli.charts)."""

from __future__ import annotations

from dku_cli.charts import (
    CHART_SPEC,
    NULLED_TYPES,
    columns_referenced,
    known_type,
    lint_chart_def,
)

SCHEMA = {
    "units": {"type": "bigint", "meaning": None},
    "revenue": {"type": "double", "meaning": None},
    "region": {"type": "string", "meaning": None},
    "geopoint": {"type": "string", "meaning": "GeoPoint"},
}


def _errs(issues):
    return [i for i in issues if i["level"] == "error"]


def test_columns_referenced_scans_all_slots():
    cdef = {
        "genericMeasures": [{"column": "revenue"}],
        "uaXDimension": [{"column": "units"}],
        "geometry": [{"column": "geopoint"}],
    }
    assert set(columns_referenced(cdef)) == {"revenue", "units", "geopoint"}


def test_valid_lines_passes():
    cdef = {"type": "lines", "genericMeasures": [{"column": "revenue"}]}
    assert _errs(lint_chart_def(cdef, SCHEMA)) == []


def test_empty_required_slot_flagged():
    cdef = {
        "type": "binned_xy",
        "xDimension": [],
        "yDimension": [{"column": "revenue"}],
    }
    errs = _errs(lint_chart_def(cdef, SCHEMA))
    assert any("xDimension" in e["msg"] for e in errs)


def test_nulled_type_flagged_with_workaround():
    cdef = {"type": "bubble", "uaXDimension": [{"column": "units"}]}
    errs = _errs(lint_chart_def(cdef, SCHEMA))
    assert any("nulled" in e["msg"] and "scatter" in e["fix"] for e in errs)


def test_missing_type_flagged():
    errs = _errs(lint_chart_def({"genericMeasures": [{"column": "revenue"}]}, SCHEMA))
    assert any("no 'type'" in e["msg"] for e in errs)


def test_nulled_on_save_signature_suggests_scatter():
    # DSS strips type:"bubble" on save -> re-read def has no type but ua* slots
    # remain. validate should name the silent-null + suggest scatter+uaSize.
    cdef = {"uaXDimension": [{"column": "units"}], "uaSize": [{"column": "revenue"}]}
    errs = _errs(lint_chart_def(cdef, SCHEMA))
    assert any("silently nulled" in e["msg"] for e in errs)
    assert any("scatter" in e["fix"] for e in errs)


def test_geo_without_meaning_flagged():
    cdef = {
        "type": "admin_map",
        "geometry": [{"column": "region"}],  # region has no geo meaning
        "colorMeasure": [{"column": "revenue"}],
    }
    errs = _errs(lint_chart_def(cdef, SCHEMA))
    assert any("geo meaning" in e["msg"] for e in errs)


def test_geo_with_geopoint_meaning_passes():
    cdef = {
        "type": "admin_map",
        "geometry": [{"column": "geopoint"}],
        "colorMeasure": [{"column": "revenue"}],
    }
    assert _errs(lint_chart_def(cdef, SCHEMA)) == []


def test_scatter_map_accepts_lonlat_without_meaning():
    cdef = {
        "type": "scatter_map",
        "uaXDimension": [{"column": "units"}],
        "uaYDimension": [{"column": "revenue"}],
    }
    assert _errs(lint_chart_def(cdef, SCHEMA)) == []


def test_bad_column_in_any_slot_flagged():
    cdef = {
        "type": "scatter",
        "uaXDimension": [{"column": "untis"}],
        "uaYDimension": [{"column": "revenue"}],
    }
    errs = _errs(lint_chart_def(cdef, SCHEMA))
    assert any("untis" in e["msg"] for e in errs)


def test_unreadable_schema_skips_column_checks():
    # empty schema map -> column checks skipped, but required-slot checks remain
    cdef = {"type": "lines", "genericMeasures": [{"column": "anything"}]}
    assert _errs(lint_chart_def(cdef, {})) == []


def test_finicky_type_emits_caveat_but_no_error():
    # a structurally-valid sankey still warns (render-finicky), exit-OK
    cdef = {
        "type": "sankey",
        "genericDimension0": [{"column": "region"}],
        "genericDimension1": [{"column": "units"}],
        "genericMeasures": [{"column": "revenue"}],
    }
    issues = lint_chart_def(cdef, SCHEMA)
    assert _errs(issues) == []
    assert any(i["level"] == "warn" and "finicky" in i["msg"] for i in issues)


def test_every_spec_type_has_required_and_use():
    for t, spec in CHART_SPEC.items():
        assert spec["req"] is not None, t
        assert spec["use"], t
        assert isinstance(spec["geo"], bool), t


def test_known_type_and_nulled_disjoint():
    assert not (set(CHART_SPEC) & set(NULLED_TYPES))
    assert known_type("lines") and not known_type("bubble")
