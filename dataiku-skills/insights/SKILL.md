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

## Safety Rules

- Never invent insight ids.
- Use dataset inspection first when chart-source context is unclear.
