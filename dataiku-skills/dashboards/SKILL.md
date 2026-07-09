---
name: dashboards
description: Create, inspect, update, and delete Dataiku dashboards. Use when an agent must edit dashboard pages, tiles, page filters, layout, or pin an existing insight as a tile.
---

# Dashboard Operations

Use Dataiku MCP tools to manage DSS dashboards safely.

A dashboard is a layout of insight tiles. Create or update the underlying insights first, then compose them into dashboard pages, filters, and tile layouts.

## Required Reading Before Mutation

Before any create or update:
1. Read [dashboard layout reference](references/dashboard-layout-reference.md).
2. If you need to create or edit the underlying insight, also use the `insights` skill first so you have the correct `insightId` before editing the tile.

Do not guess tile field names, grid coordinates, or page filter placement from memory.

## Follow This Execution Pattern

1. Discover current dashboards with `list_dashboards`. Never invent dashboard IDs.
2. Read the current dashboard with `get_dashboard_settings` before any edit.
3. For creates, call `create_dashboard`, then round-trip through `get_dashboard_settings` before any non-trivial layout edit.
4. Announce the intended action in one sentence before any mutation.
5. For edits, start from the live full settings dict and persist with `set_dashboard_settings`.
6. Validate after every mutation with `list_dashboards` or `get_dashboard_settings`.
7. When pinning an insight, validate that the persisted tile still points to the expected `insightId`.

## Preferred Tools

| Goal | Tool |
| --- | --- |
| Discover dashboards | `list_dashboards` |
| Read a dashboard | `get_dashboard_settings` |
| Create a dashboard | `create_dashboard` |
| Replace dashboard settings | `set_dashboard_settings` |
| Delete a dashboard | `delete_dashboard` |

## Key Behaviors

- `set_dashboard_settings` is a full replace. Always start from the live object returned by `get_dashboard_settings`.
- Tiles live at `dashboard.pages[i].grid.tiles`.
- Page-level filters live on the dashboard page, not on the tile.
- If a dashboard applies page-level filters, make sure the page filter dataset matches the dataset used by the filtered insight tiles.
- For real page filters, do not stop at `column` + `filterType`. Mirror the full persisted DSS shape from a working dashboard page, including filter metadata such as `id`, `label`, `isA`, `filterSelectionType`, and the `filtersParams.refreshableSelection` block when DSS uses one.
- Prefer the same engine and selection context the filtered insights use. SQL-backed chart insights may need `filtersParams.engineType: "SQL"` and a matching `refreshableSelection`, while non-SQL dashboards can persist the same richer filter shape with `engineType: "LINO"`.

## Tile Guidance

- Use the dashboard layout reference for tile shapes, grid fields, click actions, and page-filter placement rules.
- For non-chart insight tiles with richer `tileParams`, preserve the full persisted shape unless you have strong evidence a slimmer payload works. In particular, saved-model report tiles should keep the full `advancedOptions` block even when only one `displayMode` appears to use part of it.

## Safety Rules

- Never invent dashboard IDs or insight IDs.
- Create the underlying chart insight before creating or updating a tile that references it.
- Delete dashboards only with explicit user confirmation.
- Be cautious with page-level filters. A mismatched `filtersParams.datasetSmartName` or filters built against dirty source fields can make healthy chart tiles render empty or misleading.
