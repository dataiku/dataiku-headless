---
name: insights
description: Understand and inspect Dataiku insights and their referenced objects. Use when an agent must inspect existing insights or gather grounded context before asking Cobuild to create or modify insight assets.
---

# Insights

Use this guide to understand and inspect existing Dataiku insights and gather grounded context for Cobuild.

## Insight Concepts

Insights are reusable project resources that present or expose information from another Dataiku object. They are commonly used as dashboard building blocks, but dashboards own tile layout, sizing, page filters, and other display context.

An insight binds to a source object or provides dashboard content:

| Type | Binds to | What it shows |
| --- | --- | --- |
| `chart` | a dataset | A chart definition, including encoding, engine, and sampling. |
| `dataset_table` | a dataset | A reusable table exploration view with persisted state. |
| `data-quality` | a Dataiku object | That object's current Data Quality status. |
| `model-evaluation_report` | a model evaluation store entry | A chosen evaluation-report section. |
| `saved-model_report` | a saved model | A chosen model-report section. |
| `scenario_last_runs` | a scenario | Recent run outcomes, simplified or ranged. |
| `scenario_run_button` | a scenario | A dashboard-embedded control that triggers the scenario. |
| `web_app` | a WebApp | The WebApp rendered inline. |

An insight tile can reference an insight by `insightId`, but the dashboard skill owns the tile and page configuration.

## Workflow

1. Use `list_insights` to discover insights in a project.
2. Use `get_insight_settings` to inspect a selected insight and identify its source-object binding.
3. Inspect the referenced source object through its relevant reference guide before preparing a Cobuild request:
   - datasets for `chart` and `dataset_table`;
   - Data Quality for `data-quality`;
   - machine learning or evaluation stores for model reports;
   - scenarios for scenario insights;
   - WebApps for `web_app`.
4. When an insight will be used on a dashboard, use `./dashboards.md` to inspect the dashboard and its existing insight references. For greenfield work, define the required source object, insight, and dashboard relationship in the Cobuild request.
5. Route insight creation, updates, and deletion through `./cobuild.md`.

## Preferred Tools

- `list_insights`
- `get_insight_settings`

## Safety Rules

- Inspect chart-source dataset schema and profile context before requesting a chart change when field readiness is unclear.
