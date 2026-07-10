---
name: webapps
description: Inspect Dataiku WebApps and their runtime state. Use when an agent must understand existing WebApps before asking Cobuild to create or modify project assets.
---

# WebApp Inspection

Use this skill to inspect existing WebApps and their backend state.

## Workflow

1. Use `list_webapps` to discover WebApps in a project.
2. Use `get_webapp_settings` to inspect a specific WebApp.
3. Use `get_webapp_state` when backend status matters.
4. Route WebApp creation, settings updates, backend restarts, and backend stops through `./dataiku-skills/cobuild/SKILL.md`.

## Preferred Tools

- `list_webapps`
- `get_webapp_settings`
- `get_webapp_state`

## Safety Rules

- Never invent WebApp ids.
- Keep this skill focused on inspection and Cobuild grounding.
