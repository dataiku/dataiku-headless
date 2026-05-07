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
| `stacked_bars` | Stacked bar chart (HORIZONTAL bars) | Part-to-whole over categories |
| `stacked_columns` | Stacked column chart (VERTICAL stacks — distinct from `stacked_bars`) | Part-to-whole on a categorical x-axis |
| `grouped_columns` | Side-by-side grouped columns | Category comparison |
| `stacked_area` | Stacked area chart | Cumulative trends |
| `pie` | Pie / donut chart | Proportions |
| `scatter` | Scatter plot | Correlation |
| `boxplots` | Box plots | Distribution |
| `treemap` | Treemap | Hierarchical proportions |
| `pivot_table` | Pivot table | Tabular aggregation |
| `binned_xy` | 2D binned heatmap | Density |
| `bubble` | Bubble chart | 3-variable scatter |
| `kpi` | Single-number KPI tile (`def.genericMeasures[0]` is the value, no dimensions) | Most-popular dashboard tile — "current revenue", "active users" |
| `gauge` | Radial gauge with `def.gaugeOptions` | Bounded metric vs target |
| `geom_map` | Choropleth on a geometry column with `def.geoLayers[]` | Region-shaded maps |
| `scatter_map` | Point map (`def.uaXDimension`/`uaYDimension` for lat/lon, `def.mapOptions`) | Geo points / clusters |
| `radar` | Radar chart with `def.radarOptions` | Multi-dimensional comparison |
| `sankey` | Sankey diagram with `def.sankeyOptions` | Flow / transition between states |
| `waterfall` | Waterfall chart with `def.waterfallOptions` | Cumulative variance over steps |
| `density_2d` | 2D density estimate | Distribution heatmap |
| `numerical_heatmap` | Numeric heatmap | Correlation / matrix view |
| `lift_curve` | ML lift curve | Model evaluation tile |

DSS accepts these `def.type` values via `dku insight set-definition`. The `dku insight create -t` whitelist intentionally lists the most common types — others work via `set-definition` even if not advertised by `--help`.

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

**`insightType` values:** `chart`, `dataset_table`, `report`, `scenario_last_runs`, `metrics`, `eda` (Statistics worksheet), `web_app` (embedded webapp), `jupyter` (notebook output), `saved-model_report`, `managed-folder_content`, `scenario_run_button` (one-click trigger), `filters` (interactive dashboard filters), `discussions`. The CLI's `dku insight create -t` whitelist matches this set.

**`clickAction` values:** `DO_NOTHING` (default), `OPEN_INSIGHT` (drill into source chart), `OPEN_DASHBOARD` (jump to another dashboard — needs paired `clickActionDashboardId`), `OPEN_DATASET`, `OPEN_FOLDER`, `OPEN_SCENARIO`, `RUN_SCENARIO`. Configures click-through navigation on a tile.

**Per-insight tile-level overrides via `tileParams`** (when `tileType: INSIGHT` wraps a chart insight):
- `showXAxis`, `showXAxisTitle`, `showYAxis`, `showYAxisTitle`, `showLegend`, `showBrush`, `showBreadcrumb`, `inheritLegendPlacement`, `legendPlacement` (`"OUTER_RIGHT"` / `"OUTER_BOTTOM"` / `"INNER_TOP_RIGHT"` / …), `showTooltips`, `autoPlayAnimation`, `useInsightTheme` — override the source chart-insight's display config without forking the insight (e.g. hide a legend that's redundant inside a GROUP tile).
- For `web_app` insights: `loadTimeoutInSeconds` (per-tile webapp load timeout).

**Per-`dataset_table` insight tile params:**
- `viewKind` (`"EXPLORE"` / …), `showName`, `showDescription`, `showCustomFields`, `showStorageType`, `showMeaning`, `showProgressBar` — toggle which dataset metadata appears in the tile header.

**Per-`scenario_run_button` insight tile params:**
- `buttonText` (default: scenario name), `showLastRun` (bool, default true — shows "last run X minutes ago" footer). Permission: tile users need `RUN_SCENARIOS` on the project — without it the button renders disabled with no error.

### GROUP Tile (recursive container)

Groups multiple tiles under a titled border (the visual equivalent of `<fieldset>` in HTML). Common in Solutions for clustering 3-5 KPIs under a shared header.

```json
{
  "tileType": "GROUP",
  "box": {"top": 0, "left": 0, "width": 18, "height": 12},
  "clickAction": "DO_NOTHING",
  "displayMode": "INSIGHT",
  "backgroundOpacity": 1.0,
  "backgroundColor": "#ffffff",
  "autoLoad": true,
  "locked": false,
  "isDisplacing": false,
  "borderOptions": {"color": "#D9D9D9", "radius": 4, "size": 1},
  "titleOptions": {
    "showTitle": "YES",
    "title": "By number of jobs",
    "displayedTitle": "By number of jobs",
    "fontColor": "#333",
    "fontSize": 14
  },
  "grid": {
    "tiles": [
      { "tileType": "INSIGHT", "insightId": "...", "box": {"top": 0, "left": 0, "width": 9, "height": 6}, ... },
      { "tileType": "INSIGHT", "insightId": "...", "box": {"top": 0, "left": 9, "width": 9, "height": 6}, ... }
    ]
  }
}
```

**Important:** nested `box` coordinates are RELATIVE to the GROUP's own box (not the page's). The recursive `grid.tiles[]` can hold INSIGHT, TEXT, and further GROUP tiles.

### Text/Markdown Tile (canonical form — reliably persists)

The reliable form uses **markdown** in `tileParams.{text, displayedText, textAlign, verticalAlign}`. DSS persists this verbatim across saves and the markdown renders with header/bold/italic/list support.

```json
{
  "tileType": "TEXT",
  "box": {"top": 0, "left": 0, "width": 36, "height": 3},
  "clickAction": "DO_NOTHING",
  "tileParams": {
    "text": "# Dashboard Title\n\nLast refreshed **today**.",
    "displayedText": "# Dashboard Title\n\nLast refreshed **today**.",
    "textAlign": "LEFT",
    "verticalAlign": "TOP"
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

`textAlign ∈ {"LEFT", "CENTER", "RIGHT"}`, `verticalAlign ∈ {"TOP", "MIDDLE", "BOTTOM"}`. Always set both `text` and `displayedText` to the same content.

### Text/HTML Tile (alternate — may not persist)

> **DSS may normalize `tileParams.htmlContent` away on save.** Writing a `TEXT`
> tile via `dku dashboard set-definition` with HTML can persist the tile but drop `htmlContent`,
> keeping only structural fields. Prefer the markdown form above; use HTML only when
> you need raw embedding (custom CSS / scripts) and accept the persistence risk.

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

> **Do NOT hand-write the full `dataset_table` payload.** The nested `shakerScript`
> schema varies across DSS versions. In particular, `shakerScript.columnOrder` can
> expect an array of **objects**, not bare column-name strings — passing strings
> fails with `Expected BEGIN_OBJECT but was STRING at path $.shakerScript.columnOrder[0]`.
> Use the **clone-then-narrow** pattern instead: create the insight with `--dataset`,
> pull the live default via `get-definition`, and only touch the safe fields below.

```bash
# 1. Create the insight with default DSS-native scaffolding
dku insight create "Data Table" --type dataset_table --dataset my_dataset -P PROJ
# (capture INSIGHT_ID from the output)

# 2. Pull the live default payload DSS generated for this instance/version
dku insight get-definition INSIGHT_ID -P PROJ -o json > table.json

# 3. Narrow visible columns — ONLY touch columnsSelection (safe across versions)
jq '.params.shakerScript.columnsSelection = {
      "mode": "SELECTED",
      "selectedColumnNames": ["col1", "col2", "col3"]
    }' table.json > table-updated.json

# 4. Write back
dku insight set-definition INSIGHT_ID -d @table-updated.json -P PROJ

# 5. Verify — re-read and diff to confirm nothing was normalized away
dku insight get-definition INSIGHT_ID -P PROJ -o json > table.after.json
diff <(jq -S . table-updated.json) <(jq -S . table.after.json) || true
```

**Safe to edit in `params.shakerScript`** (stable across DSS versions):
- `columnsSelection` — `{mode: "SELECTED"|"ALL_EXCEPT"|"ALL", selectedColumnNames: [...]}`
- `sorting` — `[{column: "col1", ascending: true}]`
- `previewMode` — `"ALL_ROWS"` or `"FIRST_N_ROWS"`

**Leave alone unless you've read the exact object shape for your DSS version:**
- `columnOrder` — may expect objects, not strings
- `columnWidthsByName`
- `coloring.individualColumns`

If you need to reference the full structure for debugging, pull a live example from
the running DSS instance via `dku insight get-definition` rather than copying from docs.

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
| Hand-written `dataset_table.shakerScript.columnOrder = ["col1",...]` | `Expected BEGIN_OBJECT but was STRING at path $.shakerScript.columnOrder[0]` | Don't hand-write the shakerScript — clone the live default via `dku insight get-definition` first and only edit `columnsSelection` |
| `TEXT` tile `htmlContent` missing after `dashboard set-definition` | Tile renders empty / no header | DSS may normalize it away. Always re-read with `dku dashboard get-definition` and diff. If dropped, use a chart insight with large titleOptions instead of a scripted TEXT header |
| Filter page has no dataset even though UI shows one bound | `pages[].filtersParams.datasetSmartName` was checked as the filter insight | Filter dataset can live at `pages[i].filtersParams.datasetSmartName` — check both paths |

---

## Critical gotcha

### Chart column names are not validated server-side
Wrong column names save without error but render blank charts. Verify with `dku dataset schema DS -P PROJ` first. Dashboard tiles live at `pages[i].grid.tiles`, not `pages[i].tiles`.
