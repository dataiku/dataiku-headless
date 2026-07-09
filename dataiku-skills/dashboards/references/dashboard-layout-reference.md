# Dashboard Layout Reference

Condensed from the local Dataiku dashboards API export.

## Resource Model

- Dashboards are separate resources from insights.
- A dashboard owns pages, layout, page filters, and tiles.
- Tiles can reference insights by `insightId`.

## Dashboard Shape

Important top-level fields:

```json
{
  "name": "Weekly Revenue Review",
  "listed": true,
  "theme": {},
  "columnNumber": 36,
  "tileSpacing": 8,
  "showGrid": false,
  "autoStackUp": false,
  "showNavigationArrows": false,
  "reloadWhenEventReceived": false,
  "circularNavigation": false,
  "pageSectionSettings": {},
  "pages": []
}
```

Common page fields:

```json
{
  "id": "page-0",
  "title": "Revenue by Week",
  "displayedTitle": "Revenue by Week",
  "show": true,
  "showTitle": true,
  "titleAlign": "CENTER",
  "titleFontColor": "#444444",
  "titleFontSize": 28,
  "backgroundColor": "#FFFFFF",
  "enableCrossFilters": true,
  "showFilterPanel": true,
  "filtersParams": {
    "panelPosition": "TOP",
    "datasetSmartName": "orders",
    "engineType": "SQL",
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
      "autoRefreshSample": false,
      "_refreshTrigger": 1781031281700
    }
  },
  "filters": [
    {
      "filterType": "ALPHANUM_FACET",
      "filterSelectionType": "MULTI_SELECT",
      "facetSorting": "COUNT_DESC",
      "id": "1781031288162_88",
      "column": "customer_segment",
      "label": "customer_segment",
      "columnType": "ALPHANUM",
      "isA": "filter",
      "excludedValues": {},
      "isAGlobalFilter": true,
      "useMinimalUi": false,
      "isDrill": false,
      "excludeOtherValues": false,
      "allValuesInSample": false,
      "active": true,
      "includeEmptyValues": true
    }
  ],
  "grid": {
    "tiles": []
  }
}
```

## Tile Shape

Insight tile example:

```json
{
  "tileType": "INSIGHT",
  "insightId": "abc123",
  "insightType": "chart",
  "box": {"top": 0, "left": 0, "width": 24, "height": 12},
  "displayMode": "INSIGHT",
  "autoLoad": true,
  "locked": false,
  "isDisplacing": false,
  "clickAction": "DO_NOTHING",
  "tileParams": {
    "showXAxis": true,
    "showYAxis": true,
    "showLegend": true,
    "showTooltips": true,
    "inheritLegendPlacement": true,
    "legendPlacement": "OUTER_RIGHT",
    "useInsightTheme": false
  },
  "titleOptions": {
    "showTitle": "YES",
    "title": "Weekly revenue by segment",
    "fontSize": 14
  },
  "borderOptions": {"color": "#CCCCCC", "radius": 0, "size": 1},
  "useDashboardSpacing": true,
  "tileSpacing": 8,
  "padding": 0,
  "resizeImageMode": "FIT_SIZE"
}
```

Title tile example:

```json
{
  "tileType": "TITLE",
  "box": {"top": 0, "left": 0, "width": 36, "height": 2},
  "locked": true,
  "isDisplacing": true,
  "displayMode": "INSIGHT",
  "titleOptions": {"showTitle": "NO", "fontSize": 13}
}
```

Important tile fields:

- `tileType`: `INSIGHT`, `TEXT`, `IMAGE`, `IFRAME`, `GROUP`, `TITLE`
- `box.top`, `box.left`, `box.width`, `box.height`
- `clickAction`: `DO_NOTHING`, `OPEN_INSIGHT`, `OPEN_OTHER_INSIGHT`
- `displayMode`: `INSIGHT`, `INSIGHT_DESC`, `IMAGE_AND_INSIGHT_DESC`, `IMAGE`
- `tileParams`: per-tile chart display overrides such as axis, legend, tooltip, breadcrumb, animation, and theme inheritance
- `locked`
- `isDisplacing`
- `useDashboardSpacing`
- `tileSpacing`
- `padding`
- `backgroundColor`
- `backgroundOpacity`
- `borderOptions`
- `titleOptions`
- `resizeImageMode`

Tile-payload preservation note:

- Some non-chart insight tiles persist type-specific `tileParams` that are richer than they first appear.
- Saved-model report tiles can use many `displayMode` variants, but they still carry the same top-level `advancedOptions` shape.
- When cloning or editing those tiles, preserve the full `tileParams.advancedOptions` block unless you are intentionally changing a known subfield.

Important page fields:

- `displayedTitle`
- `show`
- `titleAlign`
- `titleFontColor`
- `titleFontSize`
- `backgroundColor`

Important dashboard fields:

- `theme`
- `pageSectionSettings`
- `reloadWhenEventReceived`

## Layout Notes

- Coordinates are grid units, not pixels.
- Default dashboard width is 36 columns.
- `GROUP` tiles require a nested `grid`.
- `TITLE` tiles are common as page headers and are often persisted with `locked: true` and `isDisplacing: true`.
- Page-level filters live on `pages[i].filters` and `pages[i].filtersParams`.
- `filtersParams` can be partial. Live dashboards may persist only `panelPosition` until dataset-bound page filters are actually configured.
- Once a real filter is configured in the UI, DSS may persist a richer shape than the minimal public example: `filters[i]` can include `id`, `label`, `isA`, `filterSelectionType`, `facetSorting`, and other UI flags, while `filtersParams` can include `datasetSmartName`, `engineType`, and `refreshableSelection`.
- That richer persisted shape is not SQL-only. On a non-SQL dataset, DSS can still persist the same full filter metadata and `refreshableSelection`, but with `filtersParams.engineType: "LINO"`.
- Page-level filters work best when the dataset named in `filtersParams.datasetSmartName` matches the datasets used by the target tiles and those filter fields are already cleanly typed upstream.
- When in doubt, copy the full filter object and `refreshableSelection` block from a working dashboard page that targets the same dataset family and engine, then change only the dataset and column-specific values.
