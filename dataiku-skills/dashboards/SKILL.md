---
name: dashboards
description: Inspect and understand Dataiku dashboards. Use when an agent must list dashboards or inspect dashboard settings before asking Cobuild to view, create or modify dashboard assets.
---

# Dashboards

Use this skill to understand and inspect existing Dataiku dashboards and gather grounded context for Cobuild.

## Dashboard Concepts

Dashboards are presentation resources separate from insights. A dashboard owns pages, layout, page filters, and tiles; it does not own the underlying chart, report, or other insight content.

An insight tile references an existing insight by `insightId`. Other tile types provide dashboard content or structure: `TEXT`, `IMAGE`, `IFRAME`, `GROUP`, and `TITLE`. When a dashboard uses an insight tile, the insight must exist before the tile can reference it.

Page filters apply to a dashboard page, not to an individual tile. A page filter should use a dataset compatible with the insight tiles it filters; a mismatch can cause otherwise healthy tiles to display empty or misleading results.

## Workflow

1. Use `list_dashboards` to discover dashboards.
2. Use `get_dashboard_settings` to inspect a selected dashboard before asking Cobuild to change it.
3. When a dashboard uses existing insights, use `./dataiku-skills/insights/SKILL.md` to inspect those insights before preparing the Cobuild request. For greenfield work, define the required insights and dashboard relationship in the request.
4. Route dashboard and underlying-insight creation, edits, and deletion through `./dataiku-skills/cobuild/SKILL.md`.

## Preferred Tools

- `list_dashboards`
- `get_dashboard_settings`

## Safety Rules

- Discover dashboard and insight IDs via tools; do not invent identifiers.
- Keep this skill read-only. Route dashboard and underlying-insight creation, edits, and deletion through `./dataiku-skills/cobuild/SKILL.md`.
- Inspect page-filter datasets and their affected insights before requesting a filter change.
