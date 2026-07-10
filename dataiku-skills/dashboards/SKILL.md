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

## Safety Rules

- Never invent dashboard ids.
- Inspect first, then use Cobuild for any write path.
