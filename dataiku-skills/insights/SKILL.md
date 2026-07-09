---
name: insights
description: Create, inspect, update, and delete Dataiku insights, especially chart insights. Use when an agent must build or maintain insight payloads, inspect insight definitions, or create reusable insights that dashboards reference.
---

# Insight Operations

Use Dataiku MCP tools to manage DSS insights safely, especially `type: "chart"` insights.

In practice, insights are mainly reusable building blocks for dashboards, rather than standalone end-user artifacts.

## Required Reading Before Mutation

Before any create or update:
1. Read the reference file for the specific insight type you are editing:
   - `chart`: [chart payload reference](references/chart-payload-reference.md)
   - `dataset_table`: [dataset table insight reference](references/dataset-table-insight-reference.md)
   - `saved-model_report`: [saved model report insight reference](references/saved-model-report-insight-reference.md)
   - `model-evaluation_report`: [model evaluation report insight reference](references/model-evaluation-report-insight-reference.md)
   - `data-quality`: [data quality insight reference](references/data-quality-insight-reference.md)
   - `scenario_last_runs`: [scenario last runs insight reference](references/scenario-last-runs-insight-reference.md)
   - `scenario_run_button`: [scenario run button insight reference](references/scenario-run-button-insight-reference.md)
   - `web_app`: [web app insight reference](references/web-app-insight-reference.md)
2. If the insight will be pinned on a dashboard, also coordinate with the `dashboards` skill so the tile references the correct `insightId`.

Do not guess insight type strings, chart type strings, variants, or object-binding fields from memory.

## Follow This Execution Pattern

1. Discover current insights with `list_insights`. Never invent insight IDs.
2. Read the current object with `get_insight_settings` before any edit.
3. For creates, call `create_insight` with the raw insight object, without the outer `{"insightPrototype": ...}` wrapper.
4. Announce the intended action in one sentence before any mutation.
5. For edits, start from the live full settings dict and persist with `set_insight_settings`.
6. Validate after every mutation with `list_insights` or `get_insight_settings`.

## Preferred Tools

| Goal | Tool |
| --- | --- |
| Discover insights | `list_insights` |
| Read an insight | `get_insight_settings` |
| Create an insight | `create_insight` |
| Replace insight settings | `set_insight_settings` |
| Delete an insight | `delete_insight` |

## Key Behaviors

- `create_insight` adds the required DSS wrapper automatically. Pass the raw insight definition only.
- `set_insight_settings` is a full replace and uses DSS insight update semantics under the hood.
- `dashboardCreationId` can be used as a free-form provenance tag for scripted insight creation.
- Many non-chart insight types are thin bindings to another DSS object. In those cases, the insight payload is usually small and the dashboard tile carries most of the display-specific options.

## Chart Guidance

**IMPORTANT** Chart insights created using these MCP tools will appear in the project's Insights tab and can be used in dashbaords, but will not appear in the dataset's Charts tab, as this is not exposed by the public API.

- Inspect chart source datasets with `get_dataset_info` and `get_dataset_sample` before building a chart when field readiness is uncertain. Pay attention to DSS column types, not just what values look like in raw rows.
- Use insight `type: "chart"` for charts.
- Set the source dataset at `params.datasetSmartName`.
- Set the chart engine at `params.engineType`.
- Put the full chart definition at `params.def`.
- Use the chart payload reference for chart types, slot shapes, variants, and field-readiness rules.
- Prefer in-database engines when they fit the dataset and chart type: `SQL` for SQL-backed datasets, `SPARKSQL` for Spark-compatible datasets when a Spark cluster is available, otherwise `LINO`. Use the chart payload reference for the live-tested LINO-only chart families.

## Other Insight Guidance

- Keep dashboard layout and tile rendering concerns in the `dashboards` skill. Tile `displayMode`, sizing, and page filters are dashboard concerns, not insight-envelope concerns.
- For non-chart insights, focus on the object-binding fields inside `params`.
- When creating or editing reusable non-chart insights, preserve unknown keys on readback edits just like chart insights.
- Use the per-type reference file for the non-chart insight binding you are working with.

## Safety Rules

- Never invent insight IDs, dataset names, chart type strings, or variant strings.
- Never invent smart IDs for saved models, model evaluations, scenarios, webapps, or other referenced DSS objects.
- If a field only looks chartable because of raw string formatting, stop and recommend a prepare step rather than forcing a chart payload that assumes the wrong DSS type.
- Delete insights only with explicit user confirmation.
