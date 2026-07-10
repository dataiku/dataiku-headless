---
name: insights
description: Inspect Dataiku insights and use the results as context for Cobuild. Use when an agent must list insights or inspect insight settings before asking Cobuild to create or modify insight assets.
---

# Insight Inspection

Use this skill to inspect existing insights.

## Workflow

1. Use `list_insights` to discover insights in a project.
2. Use `get_insight_settings` to inspect a specific insight.
3. Route insight creation, updates, and deletion through `./dataiku-skills/cobuild/SKILL.md`.

## Preferred Tools

- `list_insights`
- `get_insight_settings`

## Insight Types

| Type | Binds to | What it shows |
| --- | --- | --- |
| `chart` | a dataset | A chart definition (encoding, engine, sampling). |
| `dataset_table` | a dataset | A reusable table exploration view with persisted state. |
| `data-quality` | a DSS object | That object's current Data Quality status. |
| `model-evaluation_report` | a model evaluation store entry | A chosen evaluation-report section. |
| `saved-model_report` | a saved model | A chosen model-report section. |
| `scenario_last_runs` | a scenario | Recent run outcomes, simplified or ranged. |
| `scenario_run_button` | a scenario | A dashboard-embedded control that triggers the scenario. |
| `web_app` | a webapp | The webapp rendered inline. |

## Safety Rules

- Never invent insight ids.
- Use dataset inspection first when chart-source context is unclear.
