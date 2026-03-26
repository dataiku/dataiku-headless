# Dashboard & Chart JSON Reference

Complete guide to creating DSS dashboards and chart insights via the CLI. All JSON structures are derived from working production dashboards.

---

## Quick Start

```bash
# 1. Create chart insight bound to a dataset
dku insight create "Sales Trend" --type chart --dataset sales_monthly -P PROJ

# 2. Configure chart via set-definition (see Chart Definition below)
dku insight set-definition INSIGHT_ID -d @chart.json -P PROJ

# 3. Create dashboard
dku dashboard create "Sales Dashboard" -P PROJ

# 4. Configure dashboard pages & tiles
dku dashboard set-definition DASH_ID -d @dashboard.json -P PROJ

# 5. Validate column references
dku insight validate INSIGHT_ID -P PROJ
```

---

## Chart Types

| Type | Description | Typical Use |
|------|-------------|-------------|
| `lines` | Line chart (single series) | Time series trends |
| `multi_columns_lines` | Multi-series bars + optional lines | Comparison across categories |
| `stacked_bars` | Stacked bar chart | Part-to-whole over categories |
| `grouped_columns` | Side-by-side grouped columns | Category comparison |
| `stacked_area` | Stacked area chart | Cumulative trends |
| `pie` | Pie / donut chart | Proportions |
| `scatter` | Scatter plot | Correlation |
| `boxplots` | Box plots | Distribution |
| `treemap` | Treemap | Hierarchical proportions |
| `pivot_table` | Pivot table | Tabular aggregation |
| `binned_xy` | 2D binned heatmap | Density |
| `bubble` | Bubble chart | 3-variable scatter |

---

## Chart Insight Definition

The full insight JSON structure for a chart:

```json
{
  "id": "INSIGHT_ID",
  "projectKey": "PROJECT_KEY",
  "type": "chart",
  "name": "My Chart",
  "listed": true,
  "owner": "dataiku",
  "params": {
    "engineType": "LINO",
    "datasetSmartName": "my_dataset",
    "def": { /* chart definition — see below */ },
    "refreshableSelection": {
      "selection": {
        "useMemTable": false,
        "filter": {"distinct": false, "enabled": false},
        "partitionSelectionMethod": "ALL",
        "latestPartitionsN": 1,
        "ordering": {"enabled": false, "rules": []},
        "samplingMethod": "FULL",
        "maxRecords": 10000,
        "targetRatio": 0.02,
        "ascending": true,
        "withinFirstN": -1,
        "maxReadUncompressedBytes": -1
      },
      "autoRefreshSample": false,
      "_refreshTrigger": 0
    },
    "customMeasures": [],
    "reusableDimensions": [],
    "hierarchies": []
  },
  "tags": [],
  "customFields": {},
  "checklists": {"checklists": []}
}
```

**Key fields:**
- `params.datasetSmartName` — the dataset this chart reads from (REQUIRED)
- `params.engineType` — always `"LINO"` for standard charts
- `params.def` — the chart definition (type, dimensions, measures)

---

## Chart Definition (`params.def`)

```json
{
  "type": "lines",
  "variant": "normal",
  "name": "My Chart",
  "userEditedName": true,
  "genericDimension0": [ /* x-axis / category dimensions */ ],
  "genericDimension1": [ /* color / series breakdown dimensions */ ],
  "genericMeasures": [ /* y-axis values */ ],
  "facetDimension": [],
  "animationDimension": [],
  "filters": [],
  "xAxisFormatting": {
    "displayAxis": true, "showAxisTitle": true,
    "ticksConfig": {"mode": "INTERVAL"},
    "customExtent": {"editMode": "AUTO", "manualExtent": [null, null]},
    "isLogScale": false, "includeZero": true
  },
  "yAxesFormatting": [{
    "displayAxis": true, "showAxisTitle": true,
    "ticksConfig": {"mode": "INTERVAL"},
    "customExtent": {"editMode": "AUTO", "manualExtent": [null, null]},
    "isLogScale": false, "includeZero": true
  }],
  "showLegend": true,
  "colorOptions": {
    "ccScaleMode": "NORMAL",
    "paletteType": "CATEGORY",
    "singleColor": "#659a88",
    "transparency": 0.75,
    "colorPalette": "default",
    "customColors": {}
  },
  "showInChartValues": false,
  "showInChartLabels": false
}
```

**Empty arrays you should include** (chart engine may require them):
`xDimension`, `yDimension`, `uaXDimension`, `uaYDimension`, `uaSize`, `uaColor`, `uaShape`, `uaTooltip`, `groupDimension`, `xMeasure`, `yMeasure`, `colorMeasure`, `sizeMeasure`, `geometry`, `geoLayers`, `tooltipMeasures`, `boxplotBreakdownDim`, `boxplotValue`, `uaDimensionPair: [{"uaXDimension": [], "uaYDimension": []}]`.

---

## Dimension Object

Used in `genericDimension0` (x-axis) and `genericDimension1` (color breakdown):

```json
{
  "column": "month",
  "type": "ALPHANUM",
  "isA": "dimension",
  "maxValues": 100,
  "generateOthersCategory": false,
  "forceLastPositionOthers": false,
  "oneTickPerBin": "NO",
  "filters": [],
  "numParams": {"mode": "FIXED_NB", "emptyBinsMode": "ZEROS", "binSize": 1.0, "nbBins": 10},
  "sort": {"label": "Natural ordering", "sortAscending": true, "type": "NATURAL"},
  "useParenthesesForNegativeValues": false,
  "shouldFormatInPercentage": false,
  "useLastValueAsTotal": false
}
```

**Column types:** `ALPHANUM` (categorical), `NUMERICAL`, `DATE`.

**Sort types:**
- `NATURAL` — alphabetical/chronological
- `AGGREGATION` — sort by measure value (add `"measureIdx": 0` to sort by the first measure)

**Date dimensions** — add `dateParams` when `type` is `DATE`:
```json
"dateParams": {"mode": "MONTH", "maxBinNumberForAutomaticMode": 0}
```
Date modes: `YEAR`, `QUARTER`, `MONTH`, `WEEK`, `DAY`, `HOUR`.

---

## Measure Object

Used in `genericMeasures` (y-axis values):

```json
{
  "column": "revenue",
  "function": "SUM",
  "type": "NUMERICAL",
  "displayed": true,
  "isA": "measure",
  "displayAxis": "axis1",
  "displayType": "column",
  "isUnaggregated": false,
  "computeMode": "NORMAL",
  "computeModeDim": 0,
  "multiplier": "Auto",
  "useParenthesesForNegativeValues": false,
  "shouldFormatInPercentage": false,
  "percentile": 0.0,
  "isCustomPercentile": false,
  "uaComputeMode": "STACK",
  "kpiTextAlign": "CENTER",
  "responsiveTextAreaFill": 0,
  "colorRules": [],
  "valueTextFormatting": {"fontSize": 11, "fontColor": "#333", "hasBackground": false},
  "labelTextFormatting": {"fontSize": 15, "fontColor": "#333", "hasBackground": false}
}
```

**Aggregation functions:** `SUM`, `AVG`, `COUNT`, `MIN`, `MAX`, `COUNTD` (count distinct).

**Display types:** `column` (bar), `line`, `area`.

**Display axis:** `axis1` (left y-axis), `axis2` (right y-axis).

---

## Dashboard Structure

Dashboards contain **pages**, each page contains a **grid** with **tiles**.

```json
{
  "projectKey": "PROJ",
  "id": "DASHBOARD_ID",
  "name": "My Dashboard",
  "owner": "dataiku",
  "pages": [
    {
      "id": "page_1",
      "title": "Overview",
      "displayedTitle": "Overview",
      "show": true,
      "showTitle": false,
      "titleAlign": "CENTER",
      "titleFontColor": "#333",
      "titleFontSize": 28,
      "enableCrossFilters": true,
      "backgroundColor": "#FFFEF9",
      "showFilterPanel": false,
      "filtersParams": {"panelPosition": "TOP"},
      "grid": {
        "tiles": [ /* tile objects */ ]
      }
    }
  ]
}
```

**Important:** Tiles live at `pages[i].grid.tiles`, NOT `pages[i].tiles`.

---

## Tile Objects

### Insight Tile

Places a chart or table insight on the dashboard:

```json
{
  "tileType": "INSIGHT",
  "insightId": "INSIGHT_ID",
  "insightType": "chart",
  "displayMode": "INSIGHT",
  "box": {"top": 0, "left": 0, "width": 18, "height": 14},
  "clickAction": "DO_NOTHING",
  "tileParams": {"loadTimeoutInSeconds": 0},
  "backgroundOpacity": 1.0,
  "backgroundColor": "#ffffff",
  "autoLoad": true,
  "locked": false,
  "isDisplacing": false,
  "borderOptions": {"color": "#D9D9D9", "radius": 4, "size": 1},
  "titleOptions": {
    "showTitle": "YES",
    "title": "My Chart",
    "displayedTitle": "My Chart",
    "fontColor": "#333",
    "fontSize": 14
  },
  "useDashboardSpacing": true,
  "tileSpacing": 8,
  "padding": 4,
  "resizeImageMode": "FIT_SIZE"
}
```

**Grid system:** 36-column grid. `box` coordinates:
- `top` — row position (0-based)
- `left` — column position (0–35)
- `width` — tile width in columns (max 36)
- `height` — tile height in rows

**`insightType` values:** `chart`, `dataset_table`, `report`, `scenario_last_runs`, `metrics`.

### Text/HTML Tile

```json
{
  "tileType": "TEXT",
  "box": {"top": 0, "left": 0, "width": 36, "height": 3},
  "clickAction": "DO_NOTHING",
  "tileParams": {
    "htmlContent": "<h1 style=\"color: #fff;\">Dashboard Title</h1>"
  },
  "backgroundOpacity": 1.0,
  "backgroundColor": "#06312E",
  "autoLoad": true,
  "locked": false,
  "isDisplacing": false,
  "borderOptions": {"color": "#06312E", "radius": 4, "size": 0},
  "titleOptions": {"showTitle": "NO", "fontColor": "#fff", "fontSize": 14},
  "useDashboardSpacing": true,
  "tileSpacing": 8,
  "padding": 16,
  "resizeImageMode": "FIT_SIZE"
}
```

---

## Dataset Table Insight

For showing raw data in a dashboard:

```json
{
  "id": "INSIGHT_ID",
  "projectKey": "PROJ",
  "type": "dataset_table",
  "name": "Data Table",
  "listed": true,
  "owner": "dataiku",
  "params": {
    "datasetSmartName": "my_dataset",
    "shakerScript": {
      "steps": [],
      "columnsSelection": {
        "mode": "SELECTED",
        "selectedColumnNames": ["col1", "col2", "col3"]
      },
      "columnOrder": [],
      "columnWidthsByName": {},
      "coloring": {"scheme": "MEANING_AND_STATUS", "individualColumns": [], "valueColoringMode": "HASH"},
      "sorting": [{"column": "col1", "ascending": true}],
      "previewMode": "ALL_ROWS"
    }
  }
}
```

---

## End-to-End Example

Create a line chart of monthly revenue on a dashboard:

```bash
# 1. Create the insight
dku insight create "Monthly Revenue" --type chart --dataset sales_monthly -P PROJ

# 2. Save the chart definition to a file
cat > chart.json << 'EOF'
{
  "id": "INSIGHT_ID_FROM_STEP_1",
  "projectKey": "PROJ",
  "type": "chart",
  "name": "Monthly Revenue",
  "listed": true,
  "params": {
    "engineType": "LINO",
    "datasetSmartName": "sales_monthly",
    "def": {
      "type": "lines",
      "variant": "normal",
      "name": "Monthly Revenue",
      "userEditedName": true,
      "genericDimension0": [{
        "column": "month", "type": "ALPHANUM", "isA": "dimension",
        "maxValues": 100, "filters": [],
        "sort": {"type": "NATURAL", "sortAscending": true},
        "numParams": {"mode": "FIXED_NB", "emptyBinsMode": "ZEROS"}
      }],
      "genericDimension1": [],
      "genericMeasures": [{
        "column": "revenue", "function": "SUM", "type": "NUMERICAL",
        "displayed": true, "isA": "measure",
        "displayAxis": "axis1", "displayType": "line",
        "computeMode": "NORMAL"
      }],
      "facetDimension": [], "animationDimension": [], "filters": [],
      "xDimension": [], "yDimension": [], "tooltipMeasures": [],
      "showLegend": true,
      "colorOptions": {"singleColor": "#2678b2", "transparency": 0.75}
    },
    "refreshableSelection": {
      "selection": {"samplingMethod": "FULL", "maxRecords": 10000},
      "autoRefreshSample": false
    }
  }
}
EOF

dku insight set-definition INSIGHT_ID -d @chart.json -P PROJ

# 3. Validate columns
dku insight validate INSIGHT_ID -P PROJ

# 4. Create dashboard with the chart
dku dashboard create "Revenue Dashboard" -P PROJ

cat > dashboard.json << 'EOF'
{
  "projectKey": "PROJ",
  "id": "DASHBOARD_ID",
  "name": "Revenue Dashboard",
  "pages": [{
    "id": "page1",
    "title": "Overview",
    "show": true,
    "enableCrossFilters": true,
    "backgroundColor": "#FFFEF9",
    "grid": {
      "tiles": [{
        "tileType": "INSIGHT",
        "insightId": "INSIGHT_ID",
        "insightType": "chart",
        "displayMode": "INSIGHT",
        "box": {"top": 0, "left": 0, "width": 36, "height": 18},
        "autoLoad": true,
        "titleOptions": {"showTitle": "YES", "title": "Monthly Revenue"}
      }]
    }
  }]
}
EOF

dku dashboard set-definition DASHBOARD_ID -d @dashboard.json -P PROJ
```

---

## Common Mistakes

| Mistake | Symptom | Fix |
|---------|---------|-----|
| Tiles at `pages[i].tiles` instead of `pages[i].grid.tiles` | Dashboard loads but tiles don't appear | Move tiles into `grid: {tiles: [...]}` |
| Missing `params.datasetSmartName` | Chart renders empty | Add dataset binding: `--dataset DS` on create or set via definition |
| Wrong column name in dimension/measure | Chart renders blank, no error from API | Use `dku insight validate` to check columns, or `dku dataset schema DS -P PROJ` |
| Missing `engineType: "LINO"` | Chart may fail to render | Always include `"engineType": "LINO"` in params |
| Using `type: "bar"` instead of `type: "multi_columns_lines"` | Invalid chart type | See chart type table above |
