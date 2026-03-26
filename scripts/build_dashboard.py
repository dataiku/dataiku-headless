#!/usr/bin/env python3
"""Build the WM_NEW_BUSINESS dashboard via dku CLI.

Creates 7 insights (charts + table) and a 3-page dashboard,
all configured via dku insight/dashboard set-definition.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

PROJECT = "WM_NEW_BUSINESS"


def dku(*args: str, input_data: str | None = None) -> str:
    """Run a dku CLI command, return stdout."""
    cmd = ["dku", *args, "-P", PROJECT]
    result = subprocess.run(cmd, capture_output=True, text=True, input=input_data)
    if result.returncode != 0:
        print(f"  WARN: {' '.join(cmd)}", file=sys.stderr)
        print(f"  {result.stderr.strip()}", file=sys.stderr)
    return result.stdout.strip()


def dku_json(*args: str) -> dict | list:
    """Run dku command and parse JSON output."""
    out = dku(*args, "-o", "json")
    return json.loads(out) if out else {}


def create_insight(name: str, insight_type: str = "chart") -> str:
    """Create insight, return its ID."""
    out = dku("insight", "create", name, "--type", insight_type)
    # Parse "Created insight 'X' (id=ABC)"
    if "id=" in out:
        return out.split("id=")[1].rstrip(")")
    # Fallback: list and find by name
    insights = dku_json("insight", "list")
    for i in insights:
        if i["name"] == name:
            return i["id"]
    raise RuntimeError(f"Failed to create insight '{name}': {out}")


def set_insight_definition(insight_id: str, definition: dict) -> None:
    """Set the full insight definition via CLI."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(definition, f)
        f.flush()
        dku("insight", "set-definition", insight_id, "-d", f"@{f.name}")
    Path(f.name).unlink()


def set_dashboard_definition(dashboard_id: str, definition: dict) -> None:
    """Set the full dashboard definition via CLI."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(definition, f)
        f.flush()
        dku("dashboard", "set-definition", dashboard_id, "-d", f"@{f.name}")
    Path(f.name).unlink()


# --- Chart building helpers ---

def make_dimension(column: str, col_type: str = "ALPHANUM", date_mode: str = "MONTH",
                   max_values: int = 100, sort_type: str = "NATURAL", sort_asc: bool = True) -> dict:
    """Build a chart dimension."""
    d = {
        "numParams": {"mode": "FIXED_NB", "emptyBinsMode": "ZEROS", "binSize": 1.0, "nbBins": 10},
        "maxValues": max_values,
        "generateOthersCategory": False,
        "forceLastPositionOthers": False,
        "oneTickPerBin": "NO",
        "filters": [],
        "isA": "dimension",
        "sort": {"label": "Natural ordering", "sortAscending": sort_asc, "type": sort_type},
        "useParenthesesForNegativeValues": False,
        "shouldFormatInPercentage": False,
        "useLastValueAsTotal": False,
        "column": column,
        "type": col_type,
    }
    if col_type == "DATE":
        d["dateParams"] = {"mode": date_mode, "maxBinNumberForAutomaticMode": 0}
    return d


def make_measure(column: str, function: str = "SUM", display_type: str = "column",
                 display_axis: str = "axis1", multiplier: str = "Auto") -> dict:
    """Build a chart measure."""
    return {
        "column": column,
        "function": function,
        "type": "NUMERICAL",
        "displayed": True,
        "isA": "measure",
        "displayAxis": display_axis,
        "displayType": display_type,
        "isUnaggregated": False,
        "uaComputeMode": "STACK",
        "computeMode": "NORMAL",
        "computeModeDim": 0,
        "multiplier": multiplier,
        "useParenthesesForNegativeValues": False,
        "shouldFormatInPercentage": False,
        "percentile": 0.0,
        "isCustomPercentile": False,
        "kpiTextAlign": "CENTER",
        "responsiveTextAreaFill": 0,
        "valueTextFormatting": {"fontSize": 11, "fontColor": "#333", "hasBackground": False},
        "labelTextFormatting": {"fontSize": 15, "fontColor": "#333", "hasBackground": False},
        "colorRules": [],
    }


def make_chart_def(chart_type: str, name: str, dim0: list, measures: list,
                   dim1: list | None = None, variant: str = "normal",
                   filters: list | None = None) -> dict:
    """Build a full chart def object."""
    return {
        "type": chart_type,
        "variant": variant,
        "name": name,
        "userEditedName": True,
        "genericDimension0": dim0,
        "genericDimension1": dim1 or [],
        "facetDimension": [],
        "animationDimension": [],
        "genericMeasures": measures,
        "xDimension": [],
        "yDimension": [],
        "uaXDimension": [],
        "uaYDimension": [],
        "uaDimensionPair": [{"uaXDimension": [], "uaYDimension": []}],
        "uaSize": [],
        "uaColor": [],
        "uaShape": [],
        "uaTooltip": [],
        "groupDimension": [],
        "xMeasure": [],
        "yMeasure": [],
        "colorMeasure": [],
        "sizeMeasure": [],
        "geometry": [],
        "geoLayers": [],
        "tooltipMeasures": [],
        "boxplotBreakdownDim": [],
        "boxplotValue": [],
        "filters": filters or [],
        "xAxisFormatting": {
            "displayAxis": True, "showAxisTitle": True,
            "ticksConfig": {"mode": "INTERVAL"},
            "customExtent": {"editMode": "AUTO", "manualExtent": [None, None]},
            "isLogScale": False, "includeZero": True,
        },
        "yAxesFormatting": [{
            "displayAxis": True, "showAxisTitle": True,
            "ticksConfig": {"mode": "INTERVAL"},
            "customExtent": {"editMode": "AUTO", "manualExtent": [None, None]},
            "isLogScale": False, "includeZero": True,
        }],
        "showLegend": True,
        "colorOptions": {
            "ccScaleMode": "NORMAL",
            "paletteType": "CATEGORY",
            "singleColor": "#659a88",
            "transparency": 0.75,
            "colorPalette": "default",
            "customColors": {},
        },
        "showInChartValues": False,
        "showInChartLabels": False,
    }


def make_chart_insight_def(insight_id: str, name: str, dataset: str, chart_def: dict) -> dict:
    """Build the full insight definition for a chart."""
    return {
        "id": insight_id,
        "projectKey": PROJECT,
        "type": "chart",
        "name": name,
        "listed": True,
        "owner": "dataiku",
        "params": {
            "engineType": "LINO",
            "datasetSmartName": dataset,
            "def": chart_def,
            "refreshableSelection": {
                "selection": {
                    "useMemTable": False,
                    "filter": {"distinct": False, "enabled": False},
                    "partitionSelectionMethod": "ALL",
                    "latestPartitionsN": 1,
                    "ordering": {"enabled": False, "rules": []},
                    "samplingMethod": "FULL",
                    "maxRecords": 10000,
                    "targetRatio": 0.02,
                    "ascending": True,
                    "withinFirstN": -1,
                    "maxReadUncompressedBytes": -1,
                },
                "autoRefreshSample": False,
                "_refreshTrigger": 0,
            },
            "customMeasures": [],
            "reusableDimensions": [],
            "hierarchies": [],
        },
        "tags": [],
        "customFields": {},
        "checklists": {"checklists": []},
    }


def make_table_insight_def(insight_id: str, name: str, dataset: str) -> dict:
    """Build insight definition for a dataset table."""
    return {
        "id": insight_id,
        "projectKey": PROJECT,
        "type": "dataset_table",
        "name": name,
        "listed": True,
        "owner": "dataiku",
        "params": {
            "datasetSmartName": dataset,
            "shakerScript": {
                "steps": [],
                "maxProcessedMemTableBytes": -1,
                "columnsSelection": {
                    "mode": "SELECTED",
                    "selectedColumnNames": [
                        "month", "record_no", "platform", "channel", "product",
                        "solution", "act_or_plan", "forecast_value",
                    ],
                },
                "columnOrder": [],
                "columnWidthsByName": {},
                "coloring": {"scheme": "MEANING_AND_STATUS", "individualColumns": [], "valueColoringMode": "HASH"},
                "sorting": [{"column": "month", "ascending": True}],
                "flagNumericValues": True,
                "analysisColumnData": {},
                "explorationSampling": {
                    "selection": {
                        "maxRecordsForDisplay": -1, "maxStoredBytes": -1, "timeout": -1,
                        "filter": {"distinct": False, "enabled": False},
                        "partitionSelectionMethod": "ALL", "latestPartitionsN": 1,
                        "ordering": {"enabled": False, "rules": []},
                        "samplingMethod": "HEAD_SEQUENTIAL", "maxRecords": 10000,
                        "targetRatio": 0.02, "ascending": True,
                    },
                    "autoRefreshSample": False,
                },
                "vizSampling": {
                    "selection": {
                        "useMemTable": False,
                        "filter": {"distinct": False, "enabled": False},
                        "partitionSelectionMethod": "ALL", "latestPartitionsN": 1,
                        "ordering": {"enabled": False, "rules": []},
                        "samplingMethod": "FULL", "maxRecords": -1,
                        "targetRatio": 0.02, "ascending": True,
                    },
                    "autoRefreshSample": False,
                },
                "previewMode": "ALL_ROWS",
            },
        },
        "tags": [],
        "customFields": {},
        "checklists": {"checklists": []},
    }


def make_tile(insight_id: str, insight_type: str, top: int, left: int,
              width: int, height: int, show_title: str = "YES", title: str = "") -> dict:
    """Build a dashboard tile."""
    return {
        "tileType": "INSIGHT",
        "box": {"top": top, "left": left, "width": width, "height": height},
        "clickAction": "DO_NOTHING",
        "tileParams": {"loadTimeoutInSeconds": 0},
        "backgroundOpacity": 1.0,
        "backgroundColor": "#ffffff",
        "autoLoad": True,
        "locked": False,
        "isDisplacing": False,
        "borderOptions": {"color": "#D9D9D9", "radius": 4, "size": 1},
        "titleOptions": {
            "showTitle": show_title,
            "title": title,
            "displayedTitle": title,
            "fontColor": "#333",
            "fontSize": 14,
        },
        "insightId": insight_id,
        "insightType": insight_type,
        "displayMode": "INSIGHT",
        "useDashboardSpacing": True,
        "tileSpacing": 8,
        "padding": 4,
        "resizeImageMode": "FIT_SIZE",
    }


def make_text_tile(text: str, top: int, left: int, width: int, height: int) -> dict:
    """Build a text/HTML tile."""
    return {
        "tileType": "TEXT",
        "box": {"top": top, "left": left, "width": width, "height": height},
        "clickAction": "DO_NOTHING",
        "tileParams": {
            "htmlContent": text,
        },
        "backgroundOpacity": 1.0,
        "backgroundColor": "#06312E",
        "autoLoad": True,
        "locked": False,
        "isDisplacing": False,
        "borderOptions": {"color": "#06312E", "radius": 4, "size": 0},
        "titleOptions": {"showTitle": "NO", "fontColor": "#fff", "fontSize": 14},
        "useDashboardSpacing": True,
        "tileSpacing": 8,
        "padding": 16,
        "resizeImageMode": "FIT_SIZE",
    }


# ============================================================
# MAIN
# ============================================================

def main():
    print("=== Building WM_NEW_BUSINESS Dashboard ===\n")

    # --- Step 1: Create insights ---
    insights = {}

    # 1. Monthly New Business Trend (line chart on forecast_monthly)
    print("Creating insight: Monthly New Business Trend...")
    iid = create_insight("Monthly New Business Trend", "chart")
    insights["trend"] = iid
    chart_def = make_chart_def(
        "lines", "Monthly New Business Trend",
        dim0=[make_dimension("month", "ALPHANUM", max_values=100,
                             sort_type="NATURAL", sort_asc=True)],
        measures=[make_measure("forecast_value_sum", "SUM", display_type="line")],
    )
    defn = make_chart_insight_def(iid, "Monthly New Business Trend", "forecast_monthly", chart_def)
    set_insight_definition(iid, defn)
    print(f"  -> {iid}")

    # 2. Fiscal Year Comparison (bar chart on forecast_detail, grouped by year)
    print("Creating insight: Fiscal Year Totals...")
    iid = create_insight("Fiscal Year Totals", "chart")
    insights["fy"] = iid
    chart_def = make_chart_def(
        "multi_columns_lines", "Fiscal Year Totals",
        dim0=[make_dimension("year", "ALPHANUM", max_values=10,
                             sort_type="NATURAL", sort_asc=True)],
        measures=[make_measure("forecast_value", "SUM", display_type="column")],
    )
    defn = make_chart_insight_def(iid, "Fiscal Year Totals", "forecast_detail", chart_def)
    set_insight_definition(iid, defn)
    print(f"  -> {iid}")

    # 3. By Platform (stacked bar on forecast_detail)
    print("Creating insight: Forecast by Platform...")
    iid = create_insight("Forecast by Platform", "chart")
    insights["platform"] = iid
    chart_def = make_chart_def(
        "stacked_bars", "Forecast by Platform",
        dim0=[make_dimension("month", "ALPHANUM", max_values=100, sort_type="NATURAL")],
        dim1=[make_dimension("platform", "ALPHANUM", max_values=10)],
        measures=[make_measure("forecast_value", "SUM", display_type="column")],
        variant="normal",
    )
    defn = make_chart_insight_def(iid, "Forecast by Platform", "forecast_detail", chart_def)
    set_insight_definition(iid, defn)
    print(f"  -> {iid}")

    # 4. By Product (stacked bar on forecast_detail)
    print("Creating insight: Forecast by Product...")
    iid = create_insight("Forecast by Product", "chart")
    insights["product"] = iid
    chart_def = make_chart_def(
        "stacked_bars", "Forecast by Product",
        dim0=[make_dimension("month", "ALPHANUM", max_values=100, sort_type="NATURAL")],
        dim1=[make_dimension("product", "ALPHANUM", max_values=10)],
        measures=[make_measure("forecast_value", "SUM", display_type="column")],
        variant="normal",
    )
    defn = make_chart_insight_def(iid, "Forecast by Product", "forecast_detail", chart_def)
    set_insight_definition(iid, defn)
    print(f"  -> {iid}")

    # 5. Top Solutions (horizontal bar on forecast_detail)
    print("Creating insight: Top Solutions...")
    iid = create_insight("Top Solutions by Value", "chart")
    insights["solutions"] = iid
    chart_def = make_chart_def(
        "multi_columns_lines", "Top Solutions by Value",
        dim0=[make_dimension("solution", "ALPHANUM", max_values=20,
                             sort_type="AGGREGATION", sort_asc=False)],
        measures=[make_measure("forecast_value", "SUM", display_type="column")],
    )
    # Sort by measure descending
    chart_def["genericDimension0"][0]["sort"] = {
        "label": "Sum of forecast_value, descending",
        "measureIdx": 0,
        "type": "AGGREGATION",
        "sortAscending": False,
    }
    defn = make_chart_insight_def(iid, "Top Solutions by Value", "forecast_detail", chart_def)
    set_insight_definition(iid, defn)
    print(f"  -> {iid}")

    # 6. Actuals vs Forecast (grouped columns on forecast_detail by month, colored by act_or_plan)
    print("Creating insight: Actuals vs Forecast...")
    iid = create_insight("Actuals vs Forecast", "chart")
    insights["act_vs_plan"] = iid
    chart_def = make_chart_def(
        "grouped_columns", "Actuals vs Forecast",
        dim0=[make_dimension("month", "ALPHANUM", max_values=100, sort_type="NATURAL")],
        dim1=[make_dimension("act_or_plan", "ALPHANUM", max_values=5)],
        measures=[make_measure("forecast_value", "SUM", display_type="column")],
    )
    defn = make_chart_insight_def(iid, "Actuals vs Forecast", "forecast_detail", chart_def)
    set_insight_definition(iid, defn)
    print(f"  -> {iid}")

    # 7. Detail Table (dataset_table on forecast_detail)
    print("Creating insight: Forecast Detail Table...")
    iid = create_insight("Forecast Detail Table", "dataset_table")
    insights["table"] = iid
    defn = make_table_insight_def(iid, "Forecast Detail Table", "forecast_detail")
    set_insight_definition(iid, defn)
    print(f"  -> {iid}")

    print(f"\nCreated {len(insights)} insights: {insights}\n")

    # --- Step 2: Create dashboard ---
    print("Creating dashboard...")
    out = dku("dashboard", "create", "WM New Business Forecast")
    if "id=" in out:
        dash_id = out.split("id=")[1].rstrip(")")
    else:
        dashboards = dku_json("dashboard", "list")
        dash_id = dashboards[0]["id"] if dashboards else None
        if not dash_id:
            print("ERROR: Failed to create dashboard", file=sys.stderr)
            sys.exit(1)
    print(f"  Dashboard ID: {dash_id}")

    # --- Step 3: Configure dashboard pages ---
    header_html = """<div style="font-family: 'Spectral', Georgia, serif; color: #FFFEF9;">
<h1 style="margin: 0 0 4px 0; font-size: 24px; font-weight: 700;">Wealth Manager — Monthly New Business Forecast</h1>
<p style="margin: 0; font-size: 13px; opacity: 0.85; font-family: 'Roboto', sans-serif;">
117 investment products &bull; 5-factor multiplicative model &bull; Visual recipes only (zero Python)
</p></div>"""

    breakdown_header = """<div style="font-family: 'Spectral', Georgia, serif; color: #FFFEF9;">
<h1 style="margin: 0 0 4px 0; font-size: 24px; font-weight: 700;">Breakdown Analysis</h1>
<p style="margin: 0; font-size: 13px; opacity: 0.85; font-family: 'Roboto', sans-serif;">
Platform, product, and solution breakdowns across all 48 months
</p></div>"""

    dashboard_def = {
        "projectKey": PROJECT,
        "id": dash_id,
        "name": "WM New Business Forecast",
        "owner": "dataiku",
        "pages": [
            # --- Page 1: Executive Overview ---
            {
                "id": "page_overview",
                "title": "Executive Overview",
                "displayedTitle": "Executive Overview",
                "show": True,
                "showTitle": False,
                "titleAlign": "CENTER",
                "titleFontColor": "#333",
                "titleFontSize": 28,
                "enableCrossFilters": True,
                "backgroundColor": "#FFFEF9",
                "showFilterPanel": False,
                "filtersParams": {"panelPosition": "TOP"},
                "grid": {
                    "tiles": [
                        # Header banner
                        make_text_tile(header_html, top=0, left=0, width=36, height=3),
                        # Monthly trend line chart (main visual)
                        make_tile(insights["trend"], "chart",
                                  top=3, left=0, width=24, height=14,
                                  show_title="YES", title="Monthly New Business (All Months)"),
                        # FY totals bar chart
                        make_tile(insights["fy"], "chart",
                                  top=3, left=24, width=12, height=14,
                                  show_title="YES", title="Fiscal Year Totals"),
                        # Actuals vs Forecast
                        make_tile(insights["act_vs_plan"], "chart",
                                  top=17, left=0, width=36, height=13,
                                  show_title="YES", title="Actuals vs Forecast — Monthly Breakdown"),
                    ],
                },
            },
            # --- Page 2: Breakdown Analysis ---
            {
                "id": "page_breakdown",
                "title": "Breakdown Analysis",
                "displayedTitle": "Breakdown Analysis",
                "show": True,
                "showTitle": False,
                "titleAlign": "CENTER",
                "titleFontColor": "#333",
                "titleFontSize": 28,
                "enableCrossFilters": True,
                "backgroundColor": "#FFFEF9",
                "showFilterPanel": False,
                "filtersParams": {"panelPosition": "TOP"},
                "grid": {
                    "tiles": [
                        # Header banner
                        make_text_tile(breakdown_header, top=0, left=0, width=36, height=3),
                        # By Platform
                        make_tile(insights["platform"], "chart",
                                  top=3, left=0, width=18, height=14,
                                  show_title="YES", title="By Platform"),
                        # By Product
                        make_tile(insights["product"], "chart",
                                  top=3, left=18, width=18, height=14,
                                  show_title="YES", title="By Product"),
                        # Top Solutions
                        make_tile(insights["solutions"], "chart",
                                  top=17, left=0, width=36, height=13,
                                  show_title="YES", title="Top Solutions by Total Forecast Value"),
                    ],
                },
            },
            # --- Page 3: Detail ---
            {
                "id": "page_detail",
                "title": "Forecast Detail",
                "displayedTitle": "Forecast Detail",
                "show": True,
                "showTitle": False,
                "titleAlign": "CENTER",
                "titleFontColor": "#333",
                "titleFontSize": 28,
                "enableCrossFilters": False,
                "backgroundColor": "#FFFEF9",
                "showFilterPanel": False,
                "filtersParams": {"panelPosition": "TOP"},
                "grid": {
                    "tiles": [
                        make_tile(insights["table"], "dataset_table",
                                  top=0, left=0, width=36, height=24,
                                  show_title="YES", title="Record-Level Forecast Detail"),
                    ],
                },
            },
        ],
    }

    set_dashboard_definition(dash_id, dashboard_def)
    print(f"\n=== Dashboard ready: {dash_id} ===")
    print(f"  3 pages: Executive Overview, Breakdown Analysis, Forecast Detail")
    print(f"  7 insights configured with chart definitions")
    print(f"  Open in DSS to view")


if __name__ == "__main__":
    main()
