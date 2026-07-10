---
name: scenarios
description: Inspect Dataiku scenarios and their run history. Use when an agent must understand existing automation before asking Cobuild to create or modify project assets.
---

# Scenario Inspection

Use this skill to inspect existing scenarios and their recent runs.

## Workflow

1. Use `list_scenarios` to discover existing scenarios.
2. Use `get_scenario_settings` to inspect one scenario's steps, triggers, and reporters.
3. Use `get_scenario_run_history` to inspect reliability and recent outcomes.
4. Use `list_messaging_channels` to discover valid reporter-channel ids when automation context matters.
5. Route scenario creation, editing, running, or deletion through `./dataiku-skills/cobuild/SKILL.md`.

## Preferred Tools

- `list_scenarios`
- `get_scenario_settings`
- `get_scenario_run_history`
- `list_messaging_channels`

## Safety Rules

- Never invent scenario ids or messaging channel ids.
- Keep this skill focused on inspection and Cobuild grounding.
