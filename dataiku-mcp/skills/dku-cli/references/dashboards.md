# Reference: Dashboards & Charts

Durable JSON payload shapes for chart insights and dashboards. Get exact CLI flags
from `--help`; run `dku insight validate` before trusting a render — it checks both
column references and the render-blocking sampling block.

API/CLI-created charts are project **insights**: they appear in the project's
Insights tab and on dashboards, **never** in the dataset's Charts tab (the
dataset definition carries no charts; that tab is not reachable via the public
API). Point users to Insights or pin the insight to a dashboard.

---

## Chart insight payload

Set via `dku insight set-definition INSIGHT_ID -d @chart.json`.

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
      "selection": {"samplingMethod": "FULL", "maxRecords": 10000, "partitionSelectionMethod": "ALL", "filter": {"enabled": false}},
      "autoRefreshSample": false
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

- `params.datasetSmartName` — bound dataset (REQUIRED).
- `params.engineType` — always `"LINO"` for standard charts.
- `params.def` — the chart definition (type, dimensions, measures).
- `params.refreshableSelection` — REQUIRED. Omit it and chart render fails HTTP 500
  `NullPointerException: spec.sampleSettings is null` (DSS 14.6). `dku insight create -t chart`
  and `dku insight set-definition` both inject the canonical default when it is missing,
  and `dku insight validate` fails any chart without it. Self-heal an older broken
  insight (e.g. created by a raw API call): `dku insight get ID -o json > def.json`
  then `dku insight set-definition ID -d @def.json` — the re-save injects the block.
- Dimension/measure `type` is REQUIRED — an omitted `type` defaults to `NUMERICAL` and render
  fails `expected NUMERICAL but is STRING_DICT` on string columns. On STRING_DICT id columns
  prefer `--agg COUNT` over `COUNT_DISTINCT`.

---

## Chart types (`def.type`)

| Type | Use | Notes |
|------|-----|-------|
| `lines` | Time-series trend | Single series |
| `multi_columns_lines` | Multi-series bars + optional lines | Category comparison |
| `stacked_bars` | Stacked horizontal bars | Part-to-whole |
| `stacked_columns` | Stacked vertical columns | Distinct from `stacked_bars` |
| `grouped_columns` | Side-by-side columns | Category comparison |
| `stacked_area` | Stacked area | Cumulative trend |
| `pie` | Pie / donut | Proportions |
| `scatter` | Scatter plot | Correlation; uses `uaXDimension`/`uaYDimension`/`uaColor` (NOT genericMeasures) |
| `boxplots` | Box plots | Distribution; uses `boxplotBreakdownDim`/`boxplotValue` |
| `treemap` | Treemap | Hierarchical proportions; uses `yDimension` (group) + `genericMeasures` (size) + `colorMeasure` (NOT genericDimension0) |
| `pivot_table` | Pivot table | Tabular aggregation |
| `bubble` / `binned_xy` | Bubble / 2D bin heatmap | 3-variable scatter / density |
| `kpi` | Single-number tile | `def.genericMeasures[0]` is the value; no dimensions |
| `gauge` | Radial gauge | `def.gaugeOptions`; bounded metric vs target |
| `geom_map` / `scatter_map` | Choropleth / point map | `def.geoLayers[]` / `uaXDimension`+`uaYDimension`+`mapOptions` |
| `radar` / `sankey` / `waterfall` | Radar / Sankey / Waterfall | `def.radarOptions` / `sankeyOptions` / `waterfallOptions` |
| `density_2d` / `numerical_heatmap` | Density / numeric heatmap | Distribution / correlation matrix |
| `lift_curve` | ML lift curve | Model evaluation |

All values work via `set-definition` even if the `dku insight create -t` whitelist
does not advertise them.

---

## Chart definition (`params.def`)

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
  "xAxisFormatting": {"displayAxis": true, "showAxisTitle": true, "ticksConfig": {"mode": "INTERVAL"}, "isLogScale": false, "includeZero": true},
  "yAxesFormatting": [{"displayAxis": true, "showAxisTitle": true, "ticksConfig": {"mode": "INTERVAL"}, "isLogScale": false, "includeZero": true}],
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

- `genericDimension0` = x-axis/category dims; `genericDimension1` = color/series breakdown; `genericMeasures` = y-axis values.

**Empty-array scaffolding** the chart engine may require — include even when unused:
`xDimension`, `yDimension`, `uaXDimension`, `uaYDimension`, `uaSize`, `uaColor`,
`uaShape`, `uaTooltip`, `groupDimension`, `xMeasure`, `yMeasure`, `colorMeasure`,
`sizeMeasure`, `geometry`, `geoLayers`, `tooltipMeasures`, `boxplotBreakdownDim`,
`boxplotValue`, `uaDimensionPair: [{"uaXDimension": [], "uaYDimension": []}]`.

> **Advanced types read elsewhere (all live-verified).** `scatter`/`bubble`, `boxplots`,
> and `treemap` take their columns from the type-specific fields above — NOT
> `genericDimension0`/`genericMeasures` — so `add-dimension`/`add-measure` can't build them;
> set the fields via `set-definition`. A blank render with `ArrayIndexOutOfBoundsException:
> Index 0 out of bounds for length 0` means the required array is empty: `yDimension`
> (treemap) · `uaXDimension`/`uaYDimension` (scatter) · `boxplotValue` (boxplots).

### Dimension object (`genericDimension0` / `genericDimension1`)

```json
{
  "column": "month",
  "type": "ALPHANUM",
  "isA": "dimension",
  "maxValues": 100,
  "generateOthersCategory": false,
  "oneTickPerBin": "NO",
  "filters": [],
  "numParams": {"mode": "FIXED_NB", "emptyBinsMode": "ZEROS", "binSize": 1.0, "nbBins": 10},
  "sort": {"label": "Natural ordering", "sortAscending": true, "type": "NATURAL"}
}
```

- `type` ∈ `ALPHANUM` (categorical), `NUMERICAL`, `DATE`.
- `sort.type` ∈ `NATURAL` (alphabetical/chronological), `AGGREGATION` (add `"measureIdx": 0` to sort by first measure).
- **DATE dims** add `dateParams`:
  ```json
  "dateParams": {"mode": "MONTH", "maxBinNumberForAutomaticMode": 0}
  ```
  `mode` ∈ `YEAR`, `QUARTER`, `MONTH`, `WEEK`, `DAY`, `HOUR`.

### Measure object (`genericMeasures`)

```json
{
  "column": "revenue",
  "function": "SUM",
  "type": "NUMERICAL",
  "displayed": true,
  "isA": "measure",
  "displayAxis": "axis1",
  "displayType": "column",
  "computeMode": "NORMAL",
  "computeModeDim": 0,
  "uaComputeMode": "STACK",
  "colorRules": [],
  "valueTextFormatting": {"fontSize": 11, "fontColor": "#333", "hasBackground": false},
  "labelTextFormatting": {"fontSize": 15, "fontColor": "#333", "hasBackground": false}
}
```

Optional flags: `isUnaggregated`, `multiplier` (`"Auto"`), `percentile`,
`isCustomPercentile`, `useParenthesesForNegativeValues`, `shouldFormatInPercentage`,
`kpiTextAlign`, `responsiveTextAreaFill`.

- `function` ∈ `SUM`, `AVG`, `COUNT`, `MIN`, `MAX`, `COUNTD` (count distinct).
- `displayType` ∈ `column` (bar), `line`, `area`.
- `displayAxis` ∈ `axis1` (left), `axis2` (right).

---

## Dashboard payload

Set via `dku dashboard set-definition DASH_ID -d @dashboard.json`.
Structure: dashboard → `pages[]` → each page has a `grid` → `grid.tiles[]`.

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
      "backgroundColor": "#FEFEF9",
      "showFilterPanel": false,
      "filtersParams": {"panelPosition": "TOP", "datasetSmartName": "my_dataset"},
      "grid": {"tiles": [ /* tile objects */ ]}
    }
  ]
}
```

- **Tiles live at `pages[i].grid.tiles`, NOT `pages[i].tiles`** (silent: dashboard loads, tiles vanish).
- Filter-page dataset binding lives at `pages[i].filtersParams.datasetSmartName`.

### Grid / box

36-column grid. `box` = `{top, left, width, height}`:
`top` row (0-based), `left` column (0–35), `width` columns (max 36), `height` rows.

### INSIGHT tile

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
    "showTitle": "YES", "title": "My Chart", "displayedTitle": "My Chart",
    "fontColor": "#333", "fontSize": 14
  },
  "useDashboardSpacing": true,
  "tileSpacing": 8,
  "padding": 4,
  "resizeImageMode": "FIT_SIZE"
}
```

- `insightType` ∈ `chart`, `dataset_table`, `report`, `scenario_last_runs`, `metrics`,
  `eda` (Statistics worksheet), `web_app`, `jupyter`, `saved-model_report`,
  `managed-folder_content`, `scenario_run_button`, `filters`, `discussions`.
- `clickAction` ∈ `DO_NOTHING`, `OPEN_INSIGHT`, `OPEN_DASHBOARD` (pair with `clickActionDashboardId`),
  `OPEN_DATASET`, `OPEN_FOLDER`, `OPEN_SCENARIO`, `RUN_SCENARIO`.

Per-insight `tileParams` overrides (chart insights): `showXAxis`, `showXAxisTitle`,
`showYAxis`, `showYAxisTitle`, `showLegend`, `showBrush`, `showBreadcrumb`,
`inheritLegendPlacement`, `legendPlacement` (`OUTER_RIGHT`/`OUTER_BOTTOM`/`INNER_TOP_RIGHT`/…),
`showTooltips`, `autoPlayAnimation`, `useInsightTheme`. For `web_app`: `loadTimeoutInSeconds`.
For `dataset_table`: `viewKind`, `showName`, `showDescription`, `showCustomFields`,
`showStorageType`, `showMeaning`, `showProgressBar`. For `scenario_run_button`:
`buttonText`, `showLastRun` (users need `RUN_SCENARIOS` or the button renders disabled).

### GROUP tile (recursive container)

```json
{
  "tileType": "GROUP",
  "box": {"top": 0, "left": 0, "width": 18, "height": 12},
  "titleOptions": {"showTitle": "YES", "title": "By number of jobs", "displayedTitle": "By number of jobs", "fontColor": "#333", "fontSize": 14},
  "borderOptions": {"color": "#D9D9D9", "radius": 4, "size": 1},
  "grid": {"tiles": [
    {"tileType": "INSIGHT", "insightId": "...", "box": {"top": 0, "left": 0, "width": 9, "height": 6}},
    {"tileType": "INSIGHT", "insightId": "...", "box": {"top": 0, "left": 9, "width": 9, "height": 6}}
  ]}
}
```

Nested `box` is RELATIVE to the GROUP's own box. The recursive `grid.tiles[]` holds
INSIGHT, TEXT, and further GROUP tiles.

### TEXT tile

Canonical form uses **markdown** in `tileParams.{text, displayedText, textAlign, verticalAlign}`
— set `text` and `displayedText` to the same value; persists verbatim.

```json
{
  "tileType": "TEXT",
  "box": {"top": 0, "left": 0, "width": 36, "height": 3},
  "tileParams": {
    "text": "# Dashboard Title\n\nLast refreshed **today**.",
    "displayedText": "# Dashboard Title\n\nLast refreshed **today**.",
    "textAlign": "LEFT",
    "verticalAlign": "TOP"
  },
  "backgroundColor": "#06312E",
  "titleOptions": {"showTitle": "NO", "fontColor": "#fff", "fontSize": 14}
}
```

`textAlign` ∈ `LEFT`, `CENTER`, `RIGHT`; `verticalAlign` ∈ `TOP`, `MIDDLE`, `BOTTOM`.
The HTML form (`tileParams.htmlContent`) may be normalized away on save — prefer markdown.

### dataset_table tile

Do NOT hand-write the nested `shakerScript`. Clone-then-narrow: create with `--dataset`,
`get-definition` the live default, edit only safe fields, write back.

Safe to edit in `params.shakerScript`:
- `columnsSelection` — `{mode: "SELECTED"|"ALL_EXCEPT"|"ALL", selectedColumnNames: [...]}`
- `sorting` — `[{column: "col1", ascending: true}]`
- `previewMode` — `"ALL_ROWS"` or `"FIRST_N_ROWS"`

Leave alone: `columnOrder` (expects objects, not strings — bare strings fail with
`Expected BEGIN_OBJECT but was STRING`), `columnWidthsByName`, `coloring.individualColumns`.

---

## Dashboard authorizations (tiles BLANK for dashboard-only users)

Tiles render BLANK for dashboard-only (non-project) users until each tile's source object is
granted in the dashboard's **Authorizations**. There is NO CLI verb, and `dashboardAuthorizations`
does NOT persist via raw `get-settings`/`set-settings` round-trip (it's not on project settings) —
it must be granted in the DSS UI. So a dashboard that looks done from the builder's seat can be
blank for its audience. The agent should build the dashboard, then tell the user to grant
authorizations in the UI.
