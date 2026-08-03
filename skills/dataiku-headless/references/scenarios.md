---
name: scenarios
description: Inspect existing Dataiku scenarios, run them manually when requested, and review their history. Use when reviewing automation, executing an existing scenario, or planning scenario changes through Cobuild.
---

# Scenarios

Use this guide to understand existing project automation and plan grounded scenario work through Cobuild.

## Scenario Concepts

A scenario is a Dataiku automation object. It combines ordered steps, automatic triggers, and completion reporters.

- **Steps** perform work such as building data, training models, moving or exporting data, running custom work, or sending notifications.
- **Triggers** start a scenario when a schedule or configured project event occurs.
- **Reporters** notify people when a run completes.

The `active` setting controls whether automatic triggers can start runs; it does not remove the scenario. Run history records outcomes and timing, providing evidence about reliability and recurring failures.

Scenarios can have broad operational impact. Creation, edits, activation, and deletion route through Cobuild. `run_scenario` is the fixed direct exception for executing an existing scenario.

| Component | Concept |
| --- | --- |
| Steps | Ordered work performed by a run, such as builds, model work, data movement, exports, code, or notifications. |
| Triggers | Schedules or configured events, including data changes and scenario completion, that can start a run automatically. |
| Reporters | Completion notifications sent through a configured channel to selected recipients. |
| Delayed triggers | Defines what happens when a trigger occurs while a prior run is still active. |
| Run history | Records success, warning, failure, or aborted outcomes and helps identify recurring failures or slow runs. |

When describing automation to Cobuild, state the intended trigger, work sequence, notification audience, and failure behavior.

## Workflow

1. Use `list_scenarios` to discover scenarios and identify active or running automation.
2. Use `get_scenario_settings` to inspect a selected scenario's steps, triggers, reporters, and execution behavior.
3. Use `get_scenario_run_history` to investigate reliability, recent outcomes, and recurring failures.
4. When the user explicitly requests a manual run and no run is active, use `run_scenario`.
5. Use `list_messaging_channels` only when reporter configuration is relevant.
6. Inspect the project objects a scenario operates on when a requested change affects them.
7. Route scenario creation, edits, activation, and deletion through `./cobuild.md`.

## Scenario Run Identification

Keep the ids returned by `run_scenario` so later turns can follow the same execution instead of guessing or re-triggering.

- `run_id` identifies the scenario run itself.
- `trigger_fire_id` identifies the trigger request. It is especially useful when Dataiku has accepted the trigger but has not materialized the run yet.
- `get_scenario_run_history` includes `trigger_fire_id` on each row, so you can use that id later to find the run the trigger produced.

## Supporting Context

- Dataset and Flow build steps: `./datasets.md` and `./recipes.md`
- ML training or deployment steps: `./machine-learning.md`
- Managed-folder or export steps: `./managed_folders.md`
- WebApp steps: `./webapps.md`
- Active or uncertain job execution: `./jobs.md`

## Preferred Tools

- `list_scenarios`
- `get_scenario_settings`
- `get_scenario_run_history`
- `run_scenario`
- `list_messaging_channels`

## Safety Rules

- Inspect a scenario's steps before requesting a manual run or a behavior change.
- Do not request a new run while the scenario may already be running.
- If the trigger call itself raises, inspect run history before retrying; the trigger may already have reached Dataiku.
- A `scenario_poll_failed` response means the trigger was accepted but polling failed. Use its `trigger_fire_id` (and `run_id` when present) to find the run in history; never re-trigger.
- A bounded wait returning `scenario_run_still_running` is not failure. Keep polling the same run.
- Treat scenarios with expensive builds, training, exports, or notifications as consequential automation.
- Preserve existing triggers, reporters, and delayed-trigger behavior unless the user requests a change.
- Keep this skill focused on inspection, concepts, and Cobuild grounding. Do not document direct scenario mutation workflows here.
