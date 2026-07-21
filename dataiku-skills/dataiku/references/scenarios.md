---
name: scenarios
description: Understand and inspect Dataiku scenarios and their run history, then use grounded context for Cobuild automation work. Use when reviewing existing automation or planning a scenario.
---

# Scenarios

Use this skill to understand existing project automation and plan grounded scenario work through Cobuild.

## Scenario Concepts

A scenario is a Dataiku automation object. It combines ordered steps, automatic triggers, and completion reporters.

- **Steps** perform work such as building data, training models, moving or exporting data, running custom work, or sending notifications.
- **Triggers** start a scenario when a schedule or configured project event occurs.
- **Reporters** notify people when a run completes.

The `active` setting controls whether automatic triggers can start runs; it does not remove the scenario. Run history records outcomes and timing, providing evidence about reliability and recurring failures.

Scenarios can have broad operational impact. Creation, edits, activation, manual runs, and deletion route through Cobuild.

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
4. Use `list_messaging_channels` only when reporter configuration is relevant.
5. Inspect the project objects a scenario operates on when a requested change affects them.
6. Route scenario creation, edits, activation, runs, and deletion through `./dataiku-skills/cobuild/SKILL.md`.

## Supporting Context

- Dataset and Flow build steps: `../datasets/SKILL.md` and `../recipes/SKILL.md`
- ML training or deployment steps: `../machine-learning/SKILL.md`
- Managed-folder or export steps: `../managed_folders/SKILL.md`
- WebApp steps: `../webapps/SKILL.md`
- Active or uncertain job execution: `../jobs/SKILL.md`

## Preferred Tools

- `list_scenarios`
- `get_scenario_settings`
- `get_scenario_run_history`
- `list_messaging_channels`

## Safety Rules

- Discover scenario and messaging-channel identifiers through tools; do not invent them.
- Inspect a scenario's steps before requesting a manual run or a behavior change.
- Do not request a new run while the scenario may already be running.
- Treat scenarios with expensive builds, training, exports, or notifications as consequential automation.
- Preserve existing triggers, reporters, and delayed-trigger behavior unless the user requests a change.
- Keep this skill focused on inspection, concepts, and Cobuild grounding. Do not document direct scenario mutation workflows here.
