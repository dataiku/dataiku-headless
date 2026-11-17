---
name: macros
description: Discover installed macros, inspect their parameters, and manage macro runs and results.
---

# Macros

Macros are predefined actions for maintenance and diagnostic tasks, specific
connectivity tasks for import of data, and generation of reports about your data
or Dataiku. They can be built into Dataiku or supplied by plugins, including
custom plugins. Use this guide to discover and run existing macros and inspect
their results.

Macro tools are available on Design and Automation instances, subject to Dataiku
permissions and installed plugin availability.

## Workflow

Use `list_macros(project_key)` to discover installed macros, then
`get_macro_definition(project_key, macro_id)` to inspect a macro’s description,
parameter schemas and defaults, permissions, and result type. Admin parameter
schemas are visible only to administrators.

Read the definition before running a macro. Macros can modify or delete data,
including resources outside the target project. Check that its effects match the
user's request; do not use macros to bypass Cobuild for project construction.

Use `run_macro(project_key, macro_id, params=..., admin_params=...)` to start a run.
It returns immediately with a `run_id`; admin parameters require administrator
rights. Keep the project, macro, run ID, and selected instance together for follow-up:

- `get_macro_status(project_key, macro_id, run_id)` polls without fetching the result.
- `get_macro_result(project_key, macro_id, run_id)` returns the result once finished,
  or the current state while running or after failure. **Fetching a result removes
  the run from Dataiku, even if retrieval reports an execution error.** Save the
  returned result or error details; do not fetch again or restart the macro automatically.
  JSON results are parsed, text is UTF-8, and binary output is base64, as indicated
  by the encoding field.
- `abort_macro_run(project_key, macro_id, run_id)` requests cancellation. Check status afterward;
  cancellation does not undo earlier effects.

## Results and recovery

If starting fails without a run ID, inspect the macro in the UI before retrying to avoid duplicate execution. A missing
run may have been consumed already. Status includes progress and failure details
in resultError or storedError; the documented macro API has no separate log endpoint.
Check the macro's result as well as its status: `state.error_reported` only
indicates an error reported by Dataiku's status endpoint. A completed macro can
return a failure such as `ok: false` without reporting an execution error.
Verify the intended effects after completion.

[Macros overview](https://doc.dataiku.com/dss/latest/operations/macros.html)
