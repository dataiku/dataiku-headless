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

# =====================================================================
# CONFIG — the only section to edit. Everything below the marker is a
# fixed rendering engine and must be delivered byte-for-byte unchanged.
# =====================================================================
CONFIG = {
    # Header
    "title": "__TITLE__",
    "subtitle": "__SUBTITLE__",
    # Number rendering
    "locale": "en-US",  # BCP 47 locale for thousands separators
    "currency": "$",  # prefix used by the "money" format; "" for none
    # Small facts pinned in the header, e.g. source workbook name
    "badges": [
        # {"label": "Source", "value": "workbook.xlsx"},
    ],
    # Headline numbers. 3 or 4 entries. agg: sum|mean|min|max|first|last|count
    # format: money|number|number2|percent|text   (percent expects a 0-1 fraction)
    # filter (optional): {"column": <col>, "equals": <value>}
    "kpis": [
        # {"label": "Total revenue", "dataset": "d", "column": "c", "agg": "sum",
        #  "format": "money", "sub": "all years", "accent": True},
    ],
    # One entry per terminal dataset, in source-workbook sheet order.
    # column_formats overrides per-column rendering (same format keys as KPIs).
    # total_row appends a row summing every numeric column.
    "sheets": [
        # {"dataset": "d", "label": "Sheet name", "description": "One row per ...",
        #  "column_formats": {"amount": "money"}, "total_row": False},
    ],
    # Optional charts. type: line|area|bar|stacked_bar|horizontal_bar|donut|scatter|combo
    # x: label column. y: value column, or list of value columns (one series each).
    # series (stacked_bar, scatter): category column pivoted into one series each.
    # combo: y renders as bars, y2 as a line on a right axis formatted by format2.
    # donut: one slice per x value summing y, largest first, excess pooled as Other.
    # dash (line|area|bar|stacked_bar|combo): {"column": <col>, "when": <value>}
    #   draws matching rows dashed and fades their bars — actuals versus forecast.
    # wide: full-width card. format: value-axis/tooltip format.
    "charts": [
        # {"title": "Revenue by year", "subtitle": "", "type": "bar",
        #  "dataset": "d", "x": "year", "y": "revenue", "format": "money", "wide": True},
    ],
}
# ============== fixed engine below — do not edit ====================

import io
import zipfile

import dataiku
import numpy as np
import pandas as pd
from flask import Response, jsonify, request

MAX_ROWS = 5000
MAX_SERIES = 12


def _df(name):
    return dataiku.Dataset(name).get_dataframe()


def _cell(v):
    if v is None:
        return None
    if isinstance(v, (np.floating, float)):
        return None if pd.isna(v) else float(v)
    if isinstance(v, (np.integer, int)) and not isinstance(v, bool):
        return int(v)
    if isinstance(v, pd.Timestamp):
        return v.isoformat()[:10]
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    return str(v)


def _num(v):
    v = _cell(v)
    return v if isinstance(v, (int, float)) else None


def _apply_filter(df, spec):
    flt = spec.get("filter")
    if flt:
        df = df[df[flt["column"]] == flt["equals"]]
    return df


def _kpi_value(spec):
    df = _apply_filter(_df(spec["dataset"]), spec)
    agg = spec.get("agg", "sum")
    if agg == "count":
        return int(len(df))
    s = df[spec["column"]].dropna()
    if not len(s):
        return None
    if agg == "first":
        return _cell(s.iloc[0])
    if agg == "last":
        return _cell(s.iloc[-1])
    return _num(getattr(s, agg)())


def _sheet_payload(idx, spec):
    out = {
        "id": "s%d" % idx,
        "label": spec.get("label", spec["dataset"]),
        "description": spec.get("description", ""),
        "formats": spec.get("column_formats", {}),
        "total_row": bool(spec.get("total_row")),
        "columns": [],
        "rows": [],
        "row_count": 0,
        "truncated": False,
        "error": None,
    }
    try:
        df = _df(spec["dataset"])
        out["columns"] = [str(c) for c in df.columns]
        out["row_count"] = int(len(df))
        out["truncated"] = len(df) > MAX_ROWS
        out["rows"] = [
            [_cell(v) for v in row] for row in df.head(MAX_ROWS).itertuples(index=False)
        ]
    except Exception as e:
        out["error"] = "%s: %s" % (type(e).__name__, e)
    return out


def _chart_payload(spec):
    out = {
        "title": spec.get("title", ""),
        "subtitle": spec.get("subtitle", ""),
        "type": spec.get("type", "bar"),
        "format": spec.get("format", "number"),
        "wide": bool(spec.get("wide")),
        "labels": [],
        "series": [],
        "error": None,
    }
    try:
        df = _apply_filter(_df(spec["dataset"]), spec)
        x, y = spec["x"], spec["y"]
        if out["type"] == "stacked_bar" and spec.get("series"):
            p = df.pivot_table(index=x, columns=spec["series"], values=y, aggfunc="sum")
            p = p.reindex(df[x].drop_duplicates().tolist())
            totals = p.sum().sort_values(ascending=False)
            keep = list(totals.index[:MAX_SERIES])
            out["labels"] = [str(_cell(v)) for v in p.index]
            out["series"] = [
                {"label": str(c), "data": [_num(v) for v in p[c]]} for c in keep
            ]
            rest = [c for c in p.columns if c not in keep]
            if rest:
                out["series"].append(
                    {"label": "Other", "data": [_num(v) for v in p[rest].sum(axis=1)]}
                )
        elif out["type"] == "horizontal_bar":
            g = df.groupby(x, sort=False)[y].sum().sort_values(ascending=False)
            out["labels"] = [str(_cell(v)) for v in g.index]
            out["series"] = [{"label": str(y), "data": [_num(v) for v in g]}]
        elif out["type"] == "donut":
            g = df.groupby(x, sort=False)[y].sum().sort_values(ascending=False)
            keep, rest = g.iloc[:MAX_SERIES], g.iloc[MAX_SERIES:]
            out["labels"] = [str(_cell(v)) for v in keep.index]
            data = [_num(v) for v in keep]
            if len(rest):
                out["labels"].append("Other")
                data.append(_num(rest.sum()))
            out["series"] = [{"label": str(y), "data": data}]
        elif out["type"] == "scatter":
            groups = (
                [(str(k), g) for k, g in df.groupby(spec["series"], sort=False)]
                if spec.get("series")
                else [(str(y), df)]
            )
            out["series"] = [
                {
                    "label": k,
                    "points": [
                        {"x": _num(a), "y": _num(b)} for a, b in zip(g[x], g[y])
                    ],
                }
                for k, g in groups
            ]
        else:
            out["labels"] = [str(_cell(v)) for v in df[x]]
            cols = y if isinstance(y, list) else [y]
            out["series"] = [
                {"label": str(c), "data": [_num(v) for v in df[c]]} for c in cols
            ]
            if out["type"] == "combo" and spec.get("y2"):
                out["y2"] = {
                    "label": str(spec["y2"]),
                    "data": [_num(v) for v in df[spec["y2"]]],
                    "format": spec.get("format2", "number"),
                }
        dash = spec.get("dash")
        if dash and out["type"] in ("line", "area", "bar", "stacked_bar", "combo"):
            flags = {}
            for xv, dv in zip(df[x], df[dash["column"]]):
                flags.setdefault(str(_cell(xv)), dv == dash["when"])
            out["dash_flags"] = [bool(flags.get(v)) for v in out["labels"]]
            out["dash_label"] = str(dash["when"])
    except Exception as e:
        out["error"] = "%s: %s" % (type(e).__name__, e)
    return out


@app.route("/api/overview")
def overview():
    kpis = []
    for spec in CONFIG.get("kpis", []):
        item = {
            "label": spec.get("label", ""),
            "sub": spec.get("sub", ""),
            "format": spec.get("format", "number"),
            "accent": bool(spec.get("accent")),
            "value": None,
        }
        try:
            item["value"] = _kpi_value(spec)
        except Exception as e:
            item["sub"] = "unavailable (%s)" % type(e).__name__
        kpis.append(item)
    return jsonify(
        {
            "title": CONFIG.get("title", ""),
            "subtitle": CONFIG.get("subtitle", ""),
            "locale": CONFIG.get("locale", "en-US"),
            "currency": CONFIG.get("currency", ""),
            "badges": CONFIG.get("badges", []),
            "kpis": kpis,
            "sheets": [
                _sheet_payload(i, s) for i, s in enumerate(CONFIG.get("sheets", []))
            ],
            "charts": [_chart_payload(c) for c in CONFIG.get("charts", [])],
        }
    )


_CONTENT_TYPES = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
    '<Default Extension="xml" ContentType="application/xml"/>'
    '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
    '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
    '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
    "</Types>"
)
_ROOT_RELS = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
    "</Relationships>"
)
_WB_RELS = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
    '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
    "</Relationships>"
)
_WORKBOOK = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
    ' xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
    '<sheets><sheet name="%s" sheetId="1" r:id="rId1"/></sheets></workbook>'
)
_STYLES = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
    '<numFmts count="1"><numFmt numFmtId="164" formatCode="#,##0.##"/></numFmts>'
    '<fonts count="2"><font><sz val="11"/><name val="Calibri"/></font>'
    '<font><b/><sz val="11"/><name val="Calibri"/></font></fonts>'
    '<fills count="2"><fill><patternFill patternType="none"/></fill>'
    '<fill><patternFill patternType="gray125"/></fill></fills>'
    '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>'
    '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
    '<cellXfs count="4">'
    '<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
    '<xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/>'
    '<xf numFmtId="164" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>'
    '<xf numFmtId="164" fontId="1" fillId="0" borderId="0" xfId="0" applyNumberFormat="1" applyFont="1"/>'
    "</cellXfs>"
    '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>'
    "</styleSheet>"
)


def _colref(n):
    s = ""
    n += 1
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def _esc(v):
    return (
        str(v)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _is_num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _sheet_xml(rows):
    last = len(rows) - 1
    out = [
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'
    ]
    for ri, row in enumerate(rows):
        out.append('<row r="%d">' % (ri + 1))
        emphasis = ri == 0 or (ri == last and last > 0)
        for ci, val in enumerate(row):
            ref = "%s%d" % (_colref(ci), ri + 1)
            if _is_num(val):
                num = int(val) if float(val).is_integer() else val
                out.append(
                    '<c r="%s" s="%d"><v>%s</v></c>'
                    % (ref, 3 if ri == last else 2, num)
                )
            elif val in (None, ""):
                out.append('<c r="%s" s="%d"/>' % (ref, 1 if emphasis else 0))
            else:
                out.append(
                    '<c r="%s" s="%d" t="inlineStr"><is><t xml:space="preserve">%s</t></is></c>'
                    % (ref, 1 if emphasis else 0, _esc(val))
                )
        out.append("</row>")
    out.append("</sheetData></worksheet>")
    return "".join(out)


def _xlsx_bytes(sheet_name, rows):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", _CONTENT_TYPES)
        z.writestr("_rels/.rels", _ROOT_RELS)
        z.writestr("xl/workbook.xml", _WORKBOOK % _esc(sheet_name))
        z.writestr("xl/_rels/workbook.xml.rels", _WB_RELS)
        z.writestr("xl/styles.xml", _STYLES)
        z.writestr("xl/worksheets/sheet1.xml", _sheet_xml(rows))
    return buf.getvalue()


@app.route("/api/export_xlsx", methods=["POST"])
def export_xlsx():
    body = request.get_json(force=True) or {}
    rows = body.get("rows") or []
    sheet = (
        "".join(c for c in (body.get("sheet") or "Sheet1") if c not in set("[]:*?/\\"))[
            :31
        ]
        or "Sheet1"
    )
    return Response(
        _xlsx_bytes(sheet, rows),
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="export.xlsx"'},
    )
