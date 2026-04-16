# Dashboard & Chart Patterns

Creating dashboards, configuring charts, and common pitfalls. For full chart JSON anatomy, see the `dataiku` skill's `references/dashboard-charts.md`.

## Workflow: Three Steps

1. **Create chart insight** bound to a dataset
2. **Configure the chart** via `set-definition` (dimensions, measures, chart type)
3. **Create dashboard** with tiles referencing the insight

```bash
# Step 1: Create insight with dataset binding
dku insight create "Sales Trend" --type chart --dataset sales_monthly -P PROJ

# Step 2: Configure chart (see dataiku skill's references/dashboard-charts.md for full JSON anatomy)
dku insight set-definition INSIGHT_ID -d @chart.json -P PROJ

# Step 3: Validate column references
dku insight validate INSIGHT_ID -P PROJ

# Step 4: Create dashboard and add tiles
dku dashboard create "Sales Dashboard" -P PROJ
dku dashboard set-definition DASH_ID -d @dashboard.json -P PROJ
```

## Chart Types

| Type | Description |
|------|-------------|
| `lines` | Line chart |
| `multi_columns_lines` | Bar/column chart (multi-series) |
| `stacked_bars` | Stacked bar chart |
| `grouped_columns` | Grouped columns |
| `stacked_area` | Stacked area |
| `pie` | Pie / donut |
| `scatter` | Scatter plot |
| `pivot_table` | Pivot table |

## Key JSON Fields

| Field | Path | Purpose |
|-------|------|---------|
| Dataset binding | `params.datasetSmartName` | Which dataset the chart reads |
| Chart type | `params.def.type` | Chart visualization type |
| X-axis | `params.def.genericDimension0` | Category/time dimensions |
| Color breakdown | `params.def.genericDimension1` | Series grouping |
| Y-axis values | `params.def.genericMeasures` | Aggregated values |
| Tile position | `pages[i].grid.tiles[j].box` | `{top, left, width, height}` on 36-col grid |

## Verify After Every `set-definition`

DSS normalizes dashboard and insight payloads on save — unsupported or mis-shaped
fields can be silently dropped. Always re-read and diff:

```bash
dku dashboard set-definition DASH_ID -d @dashboard.json -P PROJ && \
  dku dashboard get-definition DASH_ID -P PROJ -o json > dashboard.after.json && \
  diff <(jq -S . dashboard.json) <(jq -S . dashboard.after.json) || true
```

Known normalization on DSS 14.4+:
- `TEXT` tile `tileParams.htmlContent` can be stripped. Prefer a chart insight with
  a large title instead of a scripted header.
- `dataset_table.shakerScript.columnOrder` expects objects, not strings — clone a
  live default via `dku insight get-definition` before narrowing.

## Common Mistakes

| Mistake | Fix |
|---------|-----|
| Tiles at `pages[i].tiles` | Must be `pages[i].grid.tiles` |
| Missing `params.datasetSmartName` | Use `--dataset` on `insight create` |
| Wrong column names (chart renders blank) | Run `dku insight validate ID -P PROJ` |
| Missing `engineType: "LINO"` | Always include in chart params |
| Filter page dataset "missing" | Check `pages[i].filtersParams.datasetSmartName`, not only the filter insight definition |
| `set-definition` succeeds but the field is gone | Re-read and diff — see "Verify After Every `set-definition`" above |
| Can't find a dashboard page from a browser URL | URL `/dashboards/<id>_<slug>/view/<pageId>` maps to `dashboard.id` + `pages[].id` |
