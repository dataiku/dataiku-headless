"""Chart-type knowledge: the slots each chart type reads, what's required to
render, geo needs, and one-line guidance. Single source of truth shared by
``dku insight validate`` and the skill reference (one fact, one home).

Derived from live behavior on DSS 14.x: a chart whose required slot is empty
fails at *render* time (ArrayIndexOutOfBoundsException / "an error occurred"),
not at save time — and a wrong ``type`` string is silently nulled. ``validate``
exists to catch all of that before a human ever loads the dashboard.
"""

from __future__ import annotations

import difflib

# Storage types → chart column type. Chart dimension/measure objects carry a
# `type` field that must agree with the bound column's storage: the pivot
# engine hard-fails at render time when a NUMERICAL/DATE-typed binding points
# at a column that is not numeric/date in memory ("Column X was expected to be
# NUMERICAL but is not (found STRING_DICT)"). An omitted or unrecognized type
# string (e.g. "COUNT" on a column-bound measure) is read as NUMERICAL
# server-side, so it fails the same way on string columns.
NUMERIC_STORAGE_TYPES = {"tinyint", "smallint", "int", "bigint", "float", "double"}
# DSS stores dates under several storage types — all map to the chart DATE type.
DATE_STORAGE_TYPES = {"date", "dateonly", "datetime", "datetimenotz", "datetimetz"}
# The chart column `type` strings the pivot engine recognizes.
CHART_COLUMN_TYPES = {"ALPHANUM", "NUMERICAL", "DATE", "GEOPOINT", "GEOMETRY", "CUSTOM"}
# Aggregations the engine can only compute on numeric values — they fail at
# render time on string columns ("Cannot sum non numeric values") even when
# the declared `type` passes the type check.
NUMERIC_ONLY_FUNCTIONS = {
    "SUM",
    "AVG",
    "MIN",
    "MAX",
    "MEDIAN",
    "PERCENTILE",
    "STDEV",
    "STDEV_POPULATION",
    "VARIANCE",
    "VARIANCE_POPULATION",
}
# The GUI palette's "Count of records" pseudo-column; a measure bound to it
# (or to no column at all) counts rows and is never type-checked.
COUNT_OF_RECORDS_SENTINEL = "__COUNT__"


def chart_column_type(storage: str | None) -> str:
    """Map a column's storage type to its chart column type."""
    s = (storage or "").lower()
    if s in NUMERIC_STORAGE_TYPES:
        return "NUMERICAL"
    if s in DATE_STORAGE_TYPES:
        return "DATE"
    return "ALPHANUM"


# Every def slot that can carry a {"column": ...} reference. Column names are
# NOT checked server-side — a typo saves fine and renders blank — so validate
# checks all of them, not just genericDimension*/genericMeasures.
COLUMN_SLOTS: tuple[str, ...] = (
    "genericDimension0",
    "genericDimension1",
    "genericMeasures",
    "xDimension",
    "yDimension",
    "colorMeasure",
    "sizeMeasure",
    "uaXDimension",
    "uaYDimension",
    "uaSize",
    "uaColor",
    "uaShape",
    "uaTooltip",
    "boxplotBreakdownDim",
    "boxplotValue",
    "geometry",
)

# Type strings this DSS build accepts via set-definition (exit 0) but then
# silently nulls — the chart persists with no type and renders blank. validate
# flags them and names the working alternative.
NULLED_TYPES: dict[str, str] = {
    "bubble": 'use "scatter" with a populated uaSize (bubble = sized scatter)',
    "waterfall": "no working type string on this DSS build — use grouped_columns",
}

# Per chart type:
#   req  — slot groups; EACH group needs >=1 non-empty slot to render.
#   geo  — binds a geometry/geopoint column (needs GeoPoint meaning on the dataset).
#   use  — one-line "reach for this when…" (progressive-disclosure guidance).
# Column-color charts (binned_xy/heatmap/treemap/maps) take the value in
# colorMeasure, NOT genericMeasures — the #1 mis-binding the stress test found.
CHART_SPEC: dict[str, dict] = {
    "lines": {
        "req": [["genericMeasures"]],
        "geo": False,
        "use": "single-series trend over an ordered or date axis",
    },
    "multi_columns_lines": {
        "req": [["genericMeasures"]],
        "geo": False,
        "use": "a measure across a category, split by a 2nd dim (bars/lines)",
    },
    "grouped_columns": {
        "req": [["genericDimension0"], ["genericMeasures"]],
        "geo": False,
        "use": "side-by-side category comparison; dual-axis via displayAxis",
    },
    "stacked_columns": {
        "req": [["genericDimension0"], ["genericMeasures"]],
        "geo": False,
        "use": "vertical part-to-whole across a category",
    },
    "stacked_bars": {
        "req": [["genericDimension0"], ["genericMeasures"]],
        "geo": False,
        "use": "horizontal part-to-whole across a category",
    },
    "stacked_area": {
        "req": [["genericMeasures"]],
        "geo": False,
        "use": "cumulative trend by series over a date axis",
    },
    "pie": {
        "req": [["genericDimension0"], ["genericMeasures"]],
        "geo": False,
        "use": "proportions of one measure across a few categories",
    },
    "kpi": {
        "req": [["genericMeasures"]],
        "geo": False,
        "use": "single headline number; no dimensions",
    },
    "pivot_table": {
        "req": [["genericMeasures"], ["genericDimension0", "genericDimension1"]],
        "geo": False,
        "use": "tabular cross-aggregation (rows x columns x measure)",
    },
    "scatter": {
        "req": [["uaXDimension"], ["uaYDimension"]],
        "geo": False,
        "use": "correlation of two numeric cols; +uaSize=bubble, +uaColor=split",
    },
    "boxplots": {
        "req": [["boxplotValue"]],
        "geo": False,
        "use": "distribution of a numeric column, optionally by a category",
    },
    "treemap": {
        "req": [["yDimension"], ["genericMeasures", "colorMeasure"]],
        "geo": False,
        "use": "nested proportions; size=genericMeasures, color=colorMeasure",
    },
    "gauge": {
        "req": [["genericMeasures"]],
        "geo": False,
        "use": "one measure vs a range; omit gaugeOptions:{min,max} (rejected)",
    },
    "radar": {
        "req": [["genericDimension0"], ["genericMeasures"]],
        "geo": False,
        "use": "compare several measures across one category (spokes)",
    },
    "sankey": {
        "req": [["genericDimension0"], ["genericMeasures"]],
        "geo": False,
        "use": "flow source->target — but see caveat; prefer stacked_bars",
        "caveat": "does NOT render on this DSS build — AIOOBE regardless of dim "
        "layout (dim0-only and dim0/dim1 split both fail; 0 examples in 328 "
        "projects). Use stacked_bars (source split by target) instead.",
    },
    "binned_xy": {
        "req": [["xDimension"], ["yDimension"]],
        "geo": False,
        "use": "2D density of two NUMERIC cols (binned x/y); color=colorMeasure",
    },
    "numerical_heatmap": {
        "req": [["xDimension"], ["yDimension"], ["colorMeasure"]],
        "geo": False,
        "use": "numeric x numeric heatmap; binned x/yDimension, color=colorMeasure",
        "caveat": "fails to load on categorical axes — for a category x category "
        "heatmap use binned_xy with both axes numParams.mode TREAT_AS_ALPHANUM.",
    },
    "scatter_map": {
        "req": [["geometry", "uaXDimension"]],
        "geo": True,
        "use": "raw points on a map; GeoPoint in geometry (or lon/lat in uaX/uaY)",
    },
    "admin_map": {
        "req": [["geometry"], ["colorMeasure"]],
        "geo": True,
        "use": "choropleth: GeoPoint aggregated to an admin level; color=colorMeasure",
    },
    "geom_map": {
        "req": [["geometry", "geoLayers"]],
        "geo": True,
        "use": "render a geometry column on a map (type GEOPOINT/GEOMETRY)",
    },
    "grid_map": {
        "req": [["geometry"]],
        "geo": True,
        "use": "square-grid heat density of a GeoPoint column",
    },
    "density_heat_map": {
        "req": [["geometry"]],
        "geo": True,
        "use": "smooth heat density of a GeoPoint column",
    },
}

# DSS meanings that mark a column as map-renderable geodata.
GEO_MEANINGS = {"GeoPoint", "Geometry", "GeoPolygon", "GeoShape"}


def known_type(t: str | None) -> bool:
    return t in CHART_SPEC


def columns_referenced(cdef: dict) -> list[str]:
    """Every column referenced across ALL binding slots (deduped, ordered)."""
    seen: dict[str, None] = {}
    for slot in COLUMN_SLOTS:
        for item in cdef.get(slot) or []:
            if isinstance(item, dict) and item.get("column"):
                if item["column"] == COUNT_OF_RECORDS_SENTINEL:
                    continue
                seen.setdefault(item["column"], None)
    return list(seen)


def _issue(level: str, msg: str, fix: str) -> dict:
    return {"level": level, "msg": msg, "fix": fix}


def _type_issues(ctype: str, spec: dict | None) -> list[dict]:
    out: list[dict] = []
    if ctype in NULLED_TYPES:
        out.append(
            _issue(
                "error",
                f"type '{ctype}' is silently nulled by this DSS build",
                NULLED_TYPES[ctype],
            )
        )
    if spec is None:
        out.append(
            _issue(
                "warn",
                f"type '{ctype}' is not in the verified set",
                "verify in the UI, or pick a type from CHART_SPEC",
            )
        )
    elif spec.get("caveat"):
        out.append(
            _issue(
                "warn",
                f"'{ctype}' is render-finicky — confirm in the UI",
                spec["caveat"],
            )
        )
    return out


def _required_slot_issues(ctype: str, spec: dict | None, cdef: dict) -> list[dict]:
    out: list[dict] = []
    for group in (spec or {}).get("req", []):
        if not any(cdef.get(slot) for slot in group):
            slots = " or ".join(group)
            out.append(
                _issue(
                    "error",
                    f"'{ctype}' needs a non-empty {slots} — else blank / AIOOBE",
                    f"add the column(s) to {group[0]} in params.def",
                )
            )
    return out


def _column_issues(cdef: dict, columns_by_name: dict[str, dict]) -> list[dict]:
    out: list[dict] = []
    for col in columns_referenced(cdef):
        if col not in columns_by_name:
            near = difflib.get_close_matches(
                col, list(columns_by_name), n=3, cutoff=0.6
            )
            hint = f" Did you mean: {', '.join(near)}?" if near else ""
            out.append(
                _issue(
                    "error",
                    f"column '{col}' is not in the bound dataset.{hint}",
                    "fix the column name in params.def",
                )
            )
    return out


# Unaggregated slots (scatter/scatter_map). Their "treat as text" switch is the
# `treatAsAlphanum` boolean on the binding — numParams/dateParams are ignored
# there, and vice versa for the aggregated slots.
UA_SLOTS = {"uaXDimension", "uaYDimension", "uaSize", "uaColor", "uaShape", "uaTooltip"}


def _treated_as_alphanum(slot: str, obj: dict) -> bool:
    if slot in UA_SLOTS:
        return bool(obj.get("treatAsAlphanum"))
    return "TREAT_AS_ALPHANUM" in (
        (obj.get("numParams") or {}).get("mode"),
        (obj.get("dateParams") or {}).get("mode"),
    )


def _type_mismatch_issue(slot: str, obj: dict, col: str, declared) -> dict:
    if declared is None:
        cause = "omitted `type` (DSS reads it as NUMERICAL)"
    elif declared in CHART_COLUMN_TYPES:
        cause = f"type '{declared}'"
    else:
        cause = f"unknown type '{declared}' (DSS reads it as NUMERICAL)"
    fix = f'set "type": "ALPHANUM" on the \'{col}\' binding'
    if obj.get("function") in ("COUNT", "COUNTD"):
        fix += (
            '; for a plain row count use {"function": "COUNT", '
            '"type": "COUNT"} with no "column"'
        )
    return _issue(
        "error",
        f"{slot}: {cause} on non-numeric column '{col}' — render fails "
        f"('Column {col} was expected to be NUMERICAL but is not "
        "(found STRING_DICT)')",
        fix,
    )


def _object_type_issue(
    slot: str, obj: dict, columns_by_name: dict[str, dict]
) -> dict | None:
    col = obj.get("column")
    if not col or col == COUNT_OF_RECORDS_SENTINEL:
        return None  # count-of-records — never type-checked
    info = columns_by_name.get(col)
    if info is None:
        return None  # unknown column — already flagged by _column_issues
    declared = obj.get("type")
    fn = obj.get("function")
    if declared == "CUSTOM" or fn == "CUSTOM":
        return None
    col_type = chart_column_type(info.get("type"))
    if slot == "boxplotValue" and col_type == "ALPHANUM":
        # Any declared type is broken here: NUMERICAL/DATE fail the engine type
        # check (400), and ALPHANUM passes it only to crash the boxplot
        # computation (HTTP 500 'An internal error occurred').
        return _issue(
            "error",
            f"boxplotValue: '{col}' is {col_type} — boxplots need a numeric "
            "column; render fails whatever the declared type",
            "bind a numeric column in boxplotValue, or count categories with "
            "grouped_columns instead",
        )
    if slot == "uaShape":
        return None  # shape is forced ALPHANUM at render time — any type works
    if fn in NUMERIC_ONLY_FUNCTIONS and col_type != "NUMERICAL":
        return _issue(
            "error",
            f"{slot}: {fn}({col}) — '{col}' is {col_type}, not numeric; "
            "render fails ('Cannot sum non numeric values')",
            "aggregate a numeric column, or count instead: "
            f'{{"column": "{col}", "function": "COUNT", "type": "{col_type}"}}',
        )
    effective = declared if declared in CHART_COLUMN_TYPES else "NUMERICAL"
    if (
        effective in ("NUMERICAL", "DATE")
        and col_type == "ALPHANUM"
        and not _treated_as_alphanum(slot, obj)
    ):
        return _type_mismatch_issue(slot, obj, col, declared)
    return None


def _binding_type_issues(cdef: dict, columns_by_name: dict[str, dict]) -> list[dict]:
    """Render-time type coherence — the same engine check guards every chart
    backend (aggregated tensor, scatter, boxplots): a column-bound object whose
    effective type (omitted/unknown → NUMERICAL) is NUMERICAL or DATE fails on
    a column that is neither, and numeric-only aggregations fail on non-numeric
    columns regardless of declared type. Exceptions: uaShape is forced ALPHANUM
    at render, boxplotValue must be numeric outright, and geometry bindings are
    meaning-checked (_geo_issues), never type-checked."""
    out: list[dict] = []
    for slot in COLUMN_SLOTS:
        if slot == "geometry":
            continue
        for obj in cdef.get(slot) or []:
            if not isinstance(obj, dict):
                continue
            issue = _object_type_issue(slot, obj, columns_by_name)
            if issue:
                out.append(issue)
    return out


def _geo_issues(
    ctype: str, spec: dict | None, cdef: dict, columns_by_name: dict[str, dict]
) -> list[dict]:
    if not (spec and spec.get("geo")):
        return []
    geo_cols = [
        i.get("column") for i in (cdef.get("geometry") or []) if isinstance(i, dict)
    ]
    has_meaning = any(
        columns_by_name.get(c, {}).get("meaning") in GEO_MEANINGS for c in geo_cols
    )
    # scatter_map may instead use lon/lat in uaX/uaY
    has_lonlat = bool(cdef.get("uaXDimension") and cdef.get("uaYDimension"))
    if has_meaning or (ctype == "scatter_map" and has_lonlat):
        return []
    meanings = "/".join(sorted(GEO_MEANINGS))
    return [
        _issue(
            "error",
            f"'{ctype}' has no column with a geo meaning ({meanings}) in "
            "geometry — map builds empty ('dataset is empty')",
            "GeoPointCreator in Prepare, then 'dku dataset set-meaning "
            "DS COL=GeoPoint', and bind the column in params.def.geometry",
        )
    ]


def lint_chart_def(cdef: dict, columns_by_name: dict[str, dict]) -> list[dict]:
    """Pre-flight a chart def. Returns a list of issues; empty == will render.

    ``columns_by_name`` maps column name -> {"type": storage, "meaning": meaning}.
    An empty map means the schema was unreadable: column/geo checks are skipped,
    but required-slot and type checks still run.
    Each issue: {"level": "error"|"warn", "msg": str, "fix": str}.
    """
    ctype = cdef.get("type")
    if ctype is None:
        # DSS silently nulls bad type strings (bubble/waterfall) ON SAVE, so by
        # the time we re-read the persisted def the type is already gone — only
        # the ua*/measure slots survive. Name that case instead of a bare "no
        # type", since the agent almost certainly set one and DSS dropped it.
        if cdef.get("uaSize") or cdef.get("uaXDimension"):
            fix = "if you set type 'bubble', use 'scatter' with a populated uaSize"
        else:
            fix = "set params.def.type to a valid chart type"
        return [
            _issue(
                "error",
                "chart def has no 'type' — DSS may have silently nulled an "
                "unsupported type (e.g. bubble/waterfall) on save",
                fix,
            )
        ]
    spec = CHART_SPEC.get(ctype)
    issues = _type_issues(ctype, spec) + _required_slot_issues(ctype, spec, cdef)
    if not columns_by_name:
        return issues  # schema unreadable — skip column/geo checks
    return (
        issues
        + _column_issues(cdef, columns_by_name)
        + _binding_type_issues(cdef, columns_by_name)
        + _geo_issues(ctype, spec, cdef, columns_by_name)
    )
