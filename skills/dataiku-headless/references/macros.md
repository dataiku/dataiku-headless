---
name: macros
description: Discover installed macros, inspect their parameters, and manage macro runs and results.
---

# Macros

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
  state while running. **Fetching the result removes the run from Dataiku.** Save
  the returned content; do not fetch it again. JSON results are parsed, text is
  UTF-8, and binary output is base64, as indicated by the encoding field.
- `abort_macro_run(project_key, macro_id, run_id)` requests cancellation. Check status afterward;
  cancellation does not undo earlier effects.

If starting fails without a run ID, inspect the macro in the UI before retrying to avoid duplicate execution. A missing
run may have been consumed already. Error details stay in the Dataiku UI because
plugin errors can contain credentials. Verify the intended effects after completion.

[Macro API reference](https://developer.dataiku.com/latest/api-reference/python/macros.html)
