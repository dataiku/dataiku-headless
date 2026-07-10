---
name: dashboards
description: Inspect Dataiku dashboards and use the results as context for Cobuild. Use when an agent must list dashboards or inspect dashboard settings before asking Cobuild to create or modify dashboard assets.
---

# Dashboard Inspection

Use this skill to inspect existing dashboards.

## Workflow

1. Use `list_dashboards` to discover dashboards.
2. Use `get_dashboard_settings` to inspect a specific dashboard before asking Cobuild to change it.
3. Route dashboard creation, edits, and deletion through `./dataiku-skills/cobuild/SKILL.md`.

## Preferred Tools

- `list_dashboards`
- `get_dashboard_settings`

## Resource Model

Dashboards are separate resources from insights. A dashboard owns pages, layout, page filters, and tiles. Tiles reference insights by `insightId` (tile types: `INSIGHT`, `TEXT`, `IMAGE`, `IFRAME`, `GROUP`, `TITLE`); a page can carry its own filters bound to a dataset.

## Safety Rules

- Never invent dashboard ids.
- Inspect first, then use Cobuild for any write path.
