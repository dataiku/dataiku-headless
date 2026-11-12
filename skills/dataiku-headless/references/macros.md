---
name: macros
description: Discover installed macros, inspect their parameters, and manage macro runs and results.
---

# Macros

Macro tools are available on Design and Automation instances, subject to Dataiku
permissions and installed plugin availability.

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
- `get_macro_result(project_key, macro_id, run_id)` returns the result once finished, or the current
  state while running or when status reports a failure. Failures reported by status
  are returned without consuming the run. Some execution errors appear only during
  result retrieval; these errors include the SDK details, and the run may already
  have been removed. **Fetching the result removes the run from Dataiku.** Save
  the returned content; do not fetch it again. JSON results are parsed, text is
  UTF-8, and binary output is base64, as indicated by the encoding field.
- `abort_macro_run(project_key, macro_id, run_id)` requests cancellation. Check status afterward;
  cancellation does not undo earlier effects.

If starting fails without a run ID, inspect the macro in the UI before retrying to avoid duplicate execution. A missing
run may have been consumed already. Status includes progress and failure details
in resultError or storedError; the documented macro API has no separate log endpoint.
Verify the intended effects after completion.

[Macro API reference](https://developer.dataiku.com/latest/api-reference/python/macros.html)
