---
name: scenarios
description: Create, inspect, edit, and trigger Dataiku scenarios through MCP tools. Use when an agent must list scenarios, create a new scenario, read or update steps and triggers, run scenarios manually, or review run history.
---

# Scenario Operations

Use Dataiku MCP tools to inspect and trigger scenarios safely.

## What Are Scenarios?

Scenarios are Dataiku's automation layer. A scenario contains:
- **Steps**: actions to perform sequentially — build datasets, train models, run SQL, export data, send notifications, execute custom Python, etc.
- **Triggers**: conditions that fire the scenario automatically — time schedules, dataset changes, SQL query changes, or completion of another scenario.
- **Reporters**: notifications sent when a run completes (email with optional attachments).

## Follow This Execution Pattern

1. Call `list_scenarios` to discover available scenarios. Note which are `active` (auto-triggers enabled) and which are currently `running`.
2. Before running or editing a scenario, call `get_scenario_settings` to understand its steps, triggers, and reporters.
3. Announce the intended action in one sentence. If the scenario has expensive steps (recursive builds, ML training, large exports), confirm with the user before proceeding.
4. To create a new scenario, call `create_scenario` with `type` of `step_based` (default) or `custom_python`. To add steps and triggers after creation — or to edit an existing scenario — call `get_scenario_settings`, modify the returned dict, then call `set_scenario_settings` with the full modified dict. **Load `./step-reference/REFERENCE.md` before constructing any step, trigger, or reporter payloads.**
5. Call `run_scenario` with `wait_for_completion=true` for scenarios expected to finish within a few minutes. Use `false` for long-running scenarios and check results with `get_scenario_run_history`.
6. After a run, interpret the outcome:
   - `SUCCESS`: all steps completed normally.
   - `WARNING`: steps completed but some reported non-fatal issues.
   - `FAILED`: one or more steps failed — surface the failing step from the run history if possible.
   - `ABORTED`: run was manually stopped.
7. Use `get_scenario_run_history` to assess reliability: how often does this scenario fail, and on which step?

## Scenario Settings Structure

`get_scenario_settings` returns a full dict. Key top-level fields:

| Field | Description |
| --- | --- |
| `id` | Scenario ID — use this in all tool calls |
| `name` | Display name |
| `type` | `"step_based"` or `"custom_python"` |
| `active` | Whether auto-triggers are enabled |
| `runAsUser` | Optional: login of the user the scenario runs as |
| `params.steps` | Ordered list of step dicts (step_based only) |
| `triggers` | List of trigger dicts |
| `reporters` | List of reporter (notification) dicts |
| `delayedTriggersBehavior` | Controls squashing/suppressing triggers while running |

> **Python scenario note**: For `custom_python` scenarios, `get_scenario_settings` returns the settings dict but NOT the Python script body. Script editing is not supported via these tools; use the DSS UI.

## Reading `get_scenario_settings` Output

Retain the full settings object — it's needed for any subsequent `set_scenario_settings` call. When reporting to the user, extract and surface these facts rather than dumping the raw payload:

| What to report | Where to find it |
|----------------|-----------------|
| Active (auto-triggers on?) | `active` |
| Trigger count and types | `triggers[*].type` — e.g., `"temporal"`, `"dataset_modified"`, `"sql_query"`, `"scenario_run"` |
| Each trigger active? | `triggers[*].active` |
| Step count | `len(params.steps)` |
| Ordered step types | `params.steps[*].type` in order |
| Reporter count and channels | `reporters[*].type` and `reporters[*].params.channelId` |

## Step and Trigger Reference

For full payload shapes for all step types, trigger types, and reporter configuration, load:

**`./step-reference/REFERENCE.md`**

Load this file whenever you need to construct or edit steps, triggers, or reporters. Do not guess payload shapes from memory — always consult the reference.

## Preferred Tools

- Discover: `list_scenarios`
- Create: `create_scenario`
- Inspect: `get_scenario_settings`
- Edit: `set_scenario_settings`
- Run: `run_scenario`
- Audit: `get_scenario_run_history`
- Delete: `delete_scenario`
- List messaging channels: `list_messaging_channels`

## Safety Rules

- Always call `get_scenario_settings` before `run_scenario` — understand what steps will execute.
- Never run a scenario that is already `running` — check `list_scenarios` first.
- Never call `delete_scenario` on a scenario that is currently `running` — check `list_scenarios` first and confirm with the user before deleting any scenario.
- Scenarios can trigger recursive dataset builds or ML training jobs. Confirm with the user before running if the scenario has heavy or expensive steps.
- `run_scenario` with `wait_for_completion=false` fires and forgets — default to `true` unless the user explicitly accepts async behavior.
- Never invent scenario IDs, dataset names, managed folder IDs, model IDs, connection names, SMTP channel IDs, webapp IDs, or dashboard IDs — always discover them first.
- `set_scenario_settings` is a full replace — always round-trip through `get_scenario_settings` first; never construct a settings dict from scratch unless creating a new scenario.
- Before creating a reporter: call `list_messaging_channels` for valid channel IDs, then ask the user which channel. Non-null `default_sender` -> use it (sender fixed). Null `default_sender` -> ask the user for a `sender` address. Always ask for a `recipient`. Require sender + recipient populated; if the user leaves any required field blank, omit the reporter entirely. All required fields present -> set `active: true` (reporter runs only when `active: true`).
