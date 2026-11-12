---
name: scenarios
description: Inspect existing Dataiku scenarios, run them manually when requested, and review their history. Use when reviewing automation, executing an existing scenario, creating a Python-script scenario or editing its script, or planning other scenario changes through Cobuild.
---

# Scenarios

Use this guide to understand existing project automation and plan grounded scenario work through Cobuild.

## Scenario Concepts

A scenario is a Dataiku automation object. It combines ordered steps, automatic triggers, and completion reporters.

A scenario has one of two types. A **step-based** (`step_based`) scenario runs an ordered list of steps. A **Python-script** (`custom_python`) scenario runs one Python script that drives the run through the `dataiku.scenario` API; it has triggers and reporters but no steps.

- **Steps** perform work such as building data, training models, moving or exporting data, running custom work, or sending notifications.
- **Triggers** start a scenario when a schedule or configured project event occurs.
- **Reporters** notify people when a run completes.

The `active` setting controls whether automatic triggers can start runs; it does not remove the scenario. Run history records outcomes and timing, providing evidence about reliability and recurring failures.

Scenarios can have broad operational impact. Creation, edits, activation, and deletion route through Cobuild. `run_scenario` is the fixed direct exception for executing an existing scenario. Cobuild creates only step-based scenarios and cannot edit a scenario's script, so `create_python_scenario` and `set_python_scenario_script` are the fixed direct exceptions for Python-script scenarios.

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
7. To create a Python-script scenario or change its script, follow [Python-Script Scenarios](#python-script-scenarios).
8. Route all other scenario creation, edits, activation, and deletion through `./cobuild.md`.

## Python-Script Scenarios

`create_python_scenario` and `set_python_scenario_script` require `design`; they are unavailable on Automation.

Create a Python-script scenario only when the user explicitly asks for one or for scripted automation. Otherwise describe a step-based scenario to Cobuild.

1. Use `list_scenarios` to choose a name no scenario uses. `create_python_scenario` refuses a name already in use and returns that scenario's id.
2. Write the complete script. Use the `dataiku.scenario` API for builds and other work, and limit side effects to what the user asked for.
3. Call `create_python_scenario`. It creates the scenario inactive and without triggers, saves the script, and confirms it by reading it back. Keep the returned `scenario_id`, which Dataiku derives from the name.
4. If the status is `python_scenario_script_unconfirmed`, the scenario exists but may still hold Dataiku's sample script. Do not run it. Call `set_python_scenario_script` with the returned `scenario_id` and the same script; do not create the scenario again.
5. To change an existing script, read it with `get_scenario_settings`, which returns the `script` of a Python-script scenario. Then call `set_python_scenario_script` with the complete new script. It replaces the whole script and keeps the name, triggers, reporters, activation, and other settings.
6. Confirm the saved script with `get_scenario_settings`. Run the scenario only when the user asks, with `run_scenario`, and check the outcome with `get_scenario_run_history`.
7. Route trigger, reporter, and activation changes through `./cobuild.md`, as for any scenario. These tools do not change a scenario's Python code environment; a created scenario uses the inherited default.

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
- `create_python_scenario`
- `set_python_scenario_script`
- `list_messaging_channels`

## Safety Rules

- Inspect a scenario's steps before requesting a manual run or a behavior change.
- Do not request a new run while the scenario may already be running.
- If the trigger call itself raises, inspect run history before retrying; the trigger may already have reached Dataiku.
- A `scenario_poll_failed` response means the trigger was accepted but polling failed. Use its `trigger_fire_id` (and `run_id` when present) to find the run in history; never re-trigger.
- A bounded wait returning `scenario_run_still_running` is not failure. Keep polling the same run.
- Treat scenarios with expensive builds, training, exports, or notifications as consequential automation.
- Preserve existing triggers, reporters, and delayed-trigger behavior unless the user requests a change.
- A Python-script scenario runs arbitrary Python as the scenario's run-as user. Running it can build, change, or delete data and call external services. Inspect the script before every run.
- Dataiku requires permission to write code and a license that allows Python scenarios. A refused save is reported unchanged; do not work around it.
- Saving a script also saves the scenario definition read just before. An edit someone else makes in between is lost, so avoid it while another person edits that scenario.
- Keep this skill focused on inspection, concepts, and Cobuild grounding. Do not document direct scenario mutation workflows beyond Python-script creation and script replacement.
