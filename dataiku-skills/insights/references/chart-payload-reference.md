# Chart Payload Reference

Use this reference for `chart` insight creation and full-settings edits (`create_insight`, `get_insight_settings`, `set_insight_settings`).

## Settings Shape

In chart insights:

- the top-level insight envelope carries metadata such as `type`, `name`, `listed`, and optional `dashboardCreationId`
- `params.datasetSmartName` binds the chart to its source dataset
- `params.engineType` controls the chart execution engine
- `params.refreshableSelection` carries DSS sampling and refresh state
- `params.def` carries the full chart definition

Common top-level keys:

- `type`
- `name`
- `listed`
- `dashboardCreationId`
- `params`

## Top-Level Matrix

| Param | Required | Domain | Notes |
| --- | --- | --- | --- |
| `type` | yes | `string` | Use `chart`. |
| `name` | yes | `string` | Insight display name. |
| `listed` | no | `boolean` | Public/private insight flag. |
| `dashboardCreationId` | no | `string` | Free-form provenance tag. |
| `params` | yes | `object` | Chart runtime and definition container. |

## `params` Matrix

| Param | Required | Domain | Notes |
| --- | --- | --- | --- |
| `engineType` | yes | `enum` | Common values include `LINO`, `SQL`, and `SPARKSQL`. Preserve the live value unless intentionally changing engine. |
| `datasetSmartName` | yes for usable net-new charts | `string<dataset_name>` | Required for scripted charts to bind cleanly to the source dataset in DSS. |
| `refreshableSelection` | yes for usable net-new charts | `object` | Required in live working charts. Missing this can produce broken insights that save but fail in the DSS UI. |
| `def` | yes | `object` | Full chart definition. |

## Engine Selection

- For SQL-backed datasets, prefer `engineType: "SQL"` when the chart type supports in-database execution.
- For Spark-compatible datasets and connections, prefer `engineType: "SPARKSQL"` when a Spark cluster is available and the chart type supports Spark SQL execution.
- If the chart type does not support the in-database engine, use `engineType: "LINO"` instead.
- Do not assume every chart type supports `SQL` or `SPARKSQL`; use the live type notes below when present.
- In this repo's live DSS testing, these types must use `engineType: "LINO"`:
  - `scatter`
  - `scatter_multiple_pairs`
  - `boxplots`
  - `scatter_map`
  - `geom_map`
  - `grid_map`
  - `density_2d`
  - `grouped_xy`
  - `binned_xy`

## `refreshableSelection` Shape

This block is required for usable net-new charts in the DSS examples reviewed here.

Common `refreshableSelection` keys:

- `selection`
- `autoRefreshSample`
- optional `_refreshTrigger`

## `refreshableSelection` Matrix

| Param | Required | Domain | Notes |
| --- | --- | --- | --- |
| `selection` | yes | `object` | Dataset-selection block used by DSS chart refresh. |
| `autoRefreshSample` | yes | `boolean` | Typically `false` in the charts inspected here. |
| `_refreshTrigger` | no | `integer` | DSS-generated timestamp-like value. Preserve on edit. |

Canonical reusable block:

```json
{
  "refreshableSelection": {
    "selection": {
      "useMemTable": false,
      "filter": {"distinct": false, "enabled": false},
      "partitionSelectionMethod": "ALL",
      "latestPartitionsN": 1,
      "ordering": {"enabled": false, "rules": []},
      "samplingMethod": "FULL",
      "maxRecords": -1,
      "targetRatio": 0.02,
      "ascending": true,
      "withinFirstN": -1,
      "maxReadUncompressedBytes": -1
    },
    "autoRefreshSample": false
  }
}
```

### `refreshableSelection.selection` Matrix

| Param | Required | Domain | Allowed values | Notes |
| --- | --- | --- | --- | --- |
| `useMemTable` | yes | `boolean` | `true` \| `false` | Typically `false`. |
| `filter` | yes | `object` | DSS filter block | Live charts commonly used `{"distinct": false, "enabled": false}`. |
| `partitionSelectionMethod` | yes | `enum` | `ALL` | `ALL` is the common value in non-partitioned examples. |
| `latestPartitionsN` | yes | `integer` | positive integer | Commonly `1`. Preserve unless partition logic changes. |
| `ordering` | yes | `object` | DSS ordering block | Live charts commonly used `{"enabled": false, "rules": []}`. |
| `samplingMethod` | yes | `enum` | `FULL` | `FULL` is the common value in working charts. |
| `maxRecords` | yes | `integer` | `-1` or positive integer | Commonly `-1` with `FULL`. |
| `targetRatio` | yes | `number` | decimal ratio | Commonly `0.02`. |
| `ascending` | yes | `boolean` | `true` \| `false` | Typically `true`. |
| `withinFirstN` | yes | `integer` | `-1` or positive integer | Commonly `-1`. |
| `maxReadUncompressedBytes` | yes | `integer` | `-1` or positive integer | Commonly `-1`. |

## `def` Matrix

These fields appeared broadly across working charts. Preserve unknown DSS-managed keys on edit.

| Param | Required | Domain | Notes |
| --- | --- | --- | --- |
| `id` | no on create, yes on edit | `string` | DSS-generated chart-definition id. Preserve on edit. |
| `type` | yes | `string` | Real chart type string. |
| `variant` | yes | `string` | Commonly `normal`, but type-specific variants exist. |
| `name` | yes | `string` | Chart title. |
| `userEditedName` | yes | `boolean` | Whether the title was user-edited. |
| `displayWithEChartsByDefault` | no | `boolean` | Present on many working manual charts. Preserve if present. |
| `filters` | yes | `list<object>` | Use empty list when no filters are defined. |
| slot arrays | conditional | `list<object>` | Type-specific arrays such as `genericDimension0`, `genericMeasures`, `uaXDimension`, `geometry`, `geoLayers`, `boxplotBreakdownDim`, `boxplotValue`. |
| formatting/options blocks | no | `object` | DSS often persists axis, color, tooltip, zoom, theme, legend, and thumbnail blocks. Preserve on edit. |

## Field Readiness Notes

- Chart payloads rely on DSS column typing, not just the visual shape of raw values.
- A `string` column containing date text should not be treated like a date dimension until converted upstream.
- Mixed-format date strings such as `"2024-08-07"`, `"05-03-2023"`, and `"not_a_date"` are not chart-ready.
- Unix timestamps stored as `string` values are not chart-ready dates until parsed to DSS `date` or `dateonly`.
- JSON-looking strings and array-looking strings remain plain strings unless parsed upstream.
- High-cardinality identifiers and free text such as emails, IPs, query strings, user agents, and long text are usually poor direct chart dimensions.
- For map charts, prefer a true `geopoint` column over raw `"lat,lon"` strings or split lat/lon fields.
- Normalize blanks and sentinel categories such as `UNKNOWN` before relying on grouped legends, stacks, or splits.

## Chart Types Seen In Live Payloads

Use real persisted type names when possible. Working examples included:

- `stacked_columns`
- `grouped_columns`
- `stacked_bars`
- `lines`
- `stacked_area`
- `pie`
- `scatter`
- `scatter_multiple_pairs`
- `scatter_map`
- `geom_map`
- `grid_map`
- `grouped_xy`
- `binned_xy`
- `density_2d`
- `sankey`
- `kpi`
- `boxplots`

## Chart Family Matrices

### Time/Category/Measure Charts

Types in this family:

- `stacked_columns`
- `grouped_columns`
- `stacked_bars`
- `lines`
- `stacked_area`

| Param | Required | Domain | Notes |
| --- | --- | --- | --- |
| `genericDimension0` | yes | `list<object>` | Primary dimension, often date or category. |
| `genericDimension1` | no | `list<object>` | Secondary split dimension. |
| `genericMeasures` | yes | `list<object>` | Aggregate measures. |

Date-dimension entries commonly include:

- `column`
- `type`
- `dateParams`
- `sort`
- `isA`
- numeric/text formatting flags

### Pie / Donut

Type: `pie`

| Param | Required | Domain | Notes |
| --- | --- | --- | --- |
| `genericDimension0` | yes | `list<object>` | Category dimension. |
| `genericMeasures` | yes | `list<object>` | Measure used for slice size. |
| `variant` | yes | `string` | Use `donut` for donut charts. |

### Scatter

Type: `scatter`

| Param | Required | Domain | Notes |
| --- | --- | --- | --- |
| `uaXDimension` | yes | `list<object>` | X raw/unaggregated dimension. |
| `uaYDimension` | yes | `list<object>` | Y raw/unaggregated dimension. |
| `uaSize` | no | `list<object>` | Bubble size. |
| `uaColor` | no | `list<object>` | Color split or color value. |
| `uaShape` | no | `list<object>` | Point shape. |
| `uaTooltip` | no | `list<object>` | Extra tooltip fields. |

### Scatter Multiple Pairs

Type: `scatter_multiple_pairs`

Live examples:

- `vDUuMLE` (`Multi-pair scatter on chart_ready_data`)
- `ZXmJEOP` (`Copy of Copy of Score vs Age Bubbles on chart_ready_data`)

| Param | Required | Domain | Notes |
| --- | --- | --- | --- |
| `uaDimensionPair` | yes | `list<object>` | One entry per X/Y pair. |
| `uaDimensionPair[].id` | yes | `string` | Pair identifier persisted in DSS, for example `X:age/Y:score_1`. |
| `uaDimensionPair[].uaXDimension` | yes | `list<object>` | Raw X column for that pair. |
| `uaDimensionPair[].uaYDimension` | yes | `list<object>` | Raw Y column for that pair. |
| `uaTooltip` | no | `list<object>` | Extra tooltip fields. |
| `uaColor` | no | `list<object>` | Optional color field. |
| `uaShape` | no | `list<object>` | Optional shape field. |

Type note:

- This is a separate top-level chart type, not plain `scatter` with only `scatterMPOptions`.

### Grouped XY / Bubbles

Type: `grouped_xy`

Live example:

- `Score vs Age Bubbles on chart_ready_data`

| Param | Required | Domain | Notes |
| --- | --- | --- | --- |
| `groupDimension` | yes | `list<object>` | Grouping dimension for one bubble per group. |
| `xMeasure` | yes | `list<object>` | Aggregated X measure. |
| `yMeasure` | yes | `list<object>` | Aggregated Y measure. |
| `colorMeasure` | no | `list<object>` | Optional color encoding. |
| `sizeMeasure` | no | `list<object>` | Optional bubble size measure. |

Type note:

- Grouped bubbles are not plain `scatter` with a sub-parameter in the live payloads inspected here. They are a separate top-level `def.type: "grouped_xy"`.

### KPI

Type: `kpi`

| Param | Required | Domain | Notes |
| --- | --- | --- | --- |
| `genericMeasures` | yes | `list<object>` | One or more KPI measures. |

### Sankey

Type: `sankey`

Live payloads stored flow dimensions in `yDimension`, not in `genericDimension0` / `genericDimension1`.

| Param | Required | Domain | Notes |
| --- | --- | --- | --- |
| `yDimension` | yes | `list<object>` | Ordered node dimensions in the flow. |
| `genericMeasures` | yes | `list<object>` | Weight measure. |

### Geo Point Map

Types in this family:

- `scatter_map`
- `geom_map`
- `grid_map`

| Param | Required | Domain | Notes |
| --- | --- | --- | --- |
| `geometry` | conditional | `list<object>` | Top-level geometry array used by `scatter_map`. |
| `geoLayers` | conditional | `list<object>` | `geom_map` stored layer-specific geometry and color in `geoLayers[0]`. |
| `colorMeasure` | conditional | `list<object>` | `grid_map` examples used measure-driven coloring. |
| `uaColor` | no | `list<object>` | Color encoding for point maps. |
| `uaSize` | no | `list<object>` | Size encoding for point maps. |
| `uaTooltip` | no | `list<object>` | Tooltip fields for point maps. |

### Binned XY Surface / Grid

Type: `binned_xy`

Live variants:

- `binned_xy_rect`
- `binned_xy_hex`

Live examples:

- `Score and Events by lat/lon rectangles on chart_ready_data`
- `Score and Events by lat/lon hexagons on chart_ready_data`

| Param | Required | Domain | Notes |
| --- | --- | --- | --- |
| `xDimension` | yes | `list<object>` | Numeric binned X dimension. |
| `yDimension` | yes | `list<object>` | Numeric binned Y dimension. |
| `colorMeasure` | yes | `list<object>` | Measure used for fill or intensity. |
| `sizeMeasure` | no | `list<object>` | Optional secondary measure, used in the live examples. |
| `variant` | yes | `string` | Common values here are `binned_xy_rect` and `binned_xy_hex`. |

Type note:

- These are not `grid_map`; they are a separate top-level `def.type: "binned_xy"` with a shape `variant`.

### 2D Distribution

Type: `density_2d`

| Param | Required | Domain | Notes |
| --- | --- | --- | --- |
| `xDimension` | yes | `list<object>` | Numeric binned X dimension. |
| `yDimension` | yes | `list<object>` | Numeric binned Y dimension. |

### Boxplot

Type: `boxplots`

| Param | Required | Domain | Notes |
| --- | --- | --- | --- |
| `boxplotBreakdownDim` | yes | `list<object>` | Category split dimension. |
| `boxplotValue` | yes | `list<object>` | Numeric raw value column. |

## Canonical Payload Examples

These examples are intentionally minimal but aligned to working persisted chart families seen in DSS.

Unless otherwise noted, reuse the canonical `refreshableSelection` block shown above.

### Scatter on raw numeric columns

```json
{
  "type": "chart",
  "name": "score vs age on chart_ready_data",
  "listed": false,
  "params": {
    "engineType": "LINO",
    "datasetSmartName": "chart_ready_data",
    "refreshableSelection": "...canonical block above...",
    "def": {
      "type": "scatter",
      "variant": "normal",
      "name": "score vs age",
      "userEditedName": false,
      "uaXDimension": [
        {"column": "score", "type": "NUMERICAL"}
      ],
      "uaYDimension": [
        {"column": "age", "type": "NUMERICAL"}
      ],
      "uaColor": [
        {"column": "event_count", "type": "NUMERICAL"}
      ],
      "filters": []
    }
  }
}
```

### Lines chart on a true date column

```json
{
  "type": "chart",
  "name": "Avg of score by last_login on chart_ready_data",
  "listed": false,
  "params": {
    "engineType": "SQL",
    "datasetSmartName": "chart_ready_data",
    "refreshableSelection": "...canonical block above...",
    "def": {
      "type": "lines",
      "variant": "normal",
      "name": "Avg of score by last_login",
      "userEditedName": false,
      "genericDimension0": [
        {
          "column": "last_login",
          "type": "DATE",
          "dateParams": {"mode": "MONTH"}
        }
      ],
      "genericMeasures": [
        {"column": "score", "function": "AVG", "type": "NUMERICAL", "displayed": true}
      ],
      "filters": []
    }
  }
}
```

### KPI with multiple measures

```json
{
  "type": "chart",
  "name": "KPIs on chart_ready_data",
  "listed": false,
  "params": {
    "engineType": "SQL",
    "datasetSmartName": "chart_ready_data",
    "refreshableSelection": "...canonical block above...",
    "def": {
      "type": "kpi",
      "variant": "normal",
      "name": "KPIs",
      "userEditedName": true,
      "genericMeasures": [
        {"column": "score", "function": "AVG", "type": "NUMERICAL", "displayed": true},
        {"column": "event_count", "function": "MAX", "type": "NUMERICAL", "displayed": true}
      ],
      "filters": []
    }
  }
}
```

### Scatter map from a true geopoint column

```json
{
  "type": "chart",
  "name": "Score Map Scatter on chart_ready_data",
  "listed": false,
  "params": {
    "engineType": "LINO",
    "datasetSmartName": "chart_ready_data",
    "refreshableSelection": "...canonical block above...",
    "def": {
      "type": "scatter_map",
      "variant": "normal",
      "name": "Score Map Scatter",
      "userEditedName": true,
      "geometry": [
        {"column": "geopoint", "type": "GEOPOINT"}
      ],
      "uaColor": [
        {"column": "score", "type": "NUMERICAL"}
      ],
      "uaSize": [
        {"column": "event_count", "type": "NUMERICAL"}
      ],
      "filters": []
    }
  }
}
```

### Geo point layer map

```json
{
  "type": "chart",
  "name": "Score Map on chart_ready_data",
  "listed": false,
  "params": {
    "engineType": "LINO",
    "datasetSmartName": "chart_ready_data",
    "refreshableSelection": "...canonical block above...",
    "def": {
      "type": "geom_map",
      "variant": "normal",
      "name": "Score Map",
      "userEditedName": true,
      "geoLayers": [
        {
          "geometry": [
            {"column": "geopoint", "type": "GEOPOINT"}
          ],
          "uaColor": [
            {"column": "score", "type": "NUMERICAL"}
          ]
        }
      ],
      "filters": []
    }
  }
}
```

### Sankey

```json
{
  "type": "chart",
  "name": "Country to Activity Status, weighted by Score on chart_ready_data",
  "listed": false,
  "params": {
    "engineType": "SQL",
    "datasetSmartName": "chart_ready_data",
    "refreshableSelection": "...canonical block above...",
    "def": {
      "type": "sankey",
      "variant": "normal",
      "name": "Country to Activity Status, weighted by Score",
      "userEditedName": true,
      "yDimension": [
        {"column": "country", "type": "ALPHANUM"},
        {"column": "is_active", "type": "ALPHANUM"}
      ],
      "genericMeasures": [
        {"column": "score", "function": "AVG", "type": "NUMERICAL", "displayed": true}
      ],
      "filters": []
    }
  }
}
```

### 2D distribution

```json
{
  "type": "chart",
  "name": "2D Distribution on chart_ready_data",
  "listed": false,
  "params": {
    "engineType": "LINO",
    "datasetSmartName": "chart_ready_data",
    "refreshableSelection": "...canonical block above...",
    "def": {
      "type": "density_2d",
      "variant": "normal",
      "name": "2D Distribution",
      "userEditedName": true,
      "xDimension": [
        {"column": "latitude", "type": "NUMERICAL"}
      ],
      "yDimension": [
        {"column": "longitude", "type": "NUMERICAL"}
      ],
      "filters": []
    }
  }
}
```

### Boxplot

```json
{
  "type": "chart",
  "name": "Boxplot - Scores by Country on chart_ready_data",
  "listed": false,
  "params": {
    "engineType": "LINO",
    "datasetSmartName": "chart_ready_data",
    "refreshableSelection": "...canonical block above...",
    "def": {
      "type": "boxplots",
      "variant": "normal",
      "name": "Boxplot - Scores by Country",
      "userEditedName": true,
      "boxplotBreakdownDim": [
        {"column": "country", "type": "ALPHANUM"}
      ],
      "boxplotValue": [
        {"column": "score", "type": "NUMERICAL"}
      ],
      "filters": []
    }
  }
}
```

## Recommended Update Pattern

1. Read the live chart first with `get_insight_settings` and start from that full object.
2. Preserve `params.refreshableSelection` when editing. Do not replace a working chart with a hand-minimized payload.
3. Preserve DSS-managed formatting and option blocks unless the user explicitly wants visual changes.
4. Prefer copying a live chart of the same family and changing only the dataset, slots, and user-facing names.
5. For net-new charts, prefer a known-good family template over inventing a minimal payload from memory.
6. If a field only looks chartable because of raw string formatting, stop and recommend upstream preparation first.
