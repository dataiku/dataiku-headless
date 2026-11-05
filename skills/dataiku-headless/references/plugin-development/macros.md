# Macro Plugin Components

Start with [Plugin development](../plugin-development.md). Use a macro for an
operation or report that a user runs. Make its effects clear in the label and settings.

Use `python-runnables/<component-id>/runnable.json` and `runnable.py`, following
[the macro reference](https://doc.dataiku.com/dss/latest/plugins/reference/macros.html).
Derive from `dataiku.runnables.Runnable`. The constructor receives `project_key`,
`config`, and `plugin_config`; put the operation in `run(progress_callback)`.

- Set `permissions` for required project access and `requiresGlobalAdmin` only when
  necessary. Choose `impersonate` deliberately for the instance's user-isolation setup.
- Use `macroRoles` to add the macro to an object's menu and fill in its settings.
- Match the return value to `resultType`: return a string for HTML or URL, or a
  `dataiku.runnables.ResultTable` for RESULT_TABLE. Escape values inserted into HTML
  and scope styles to the result.
- For long work, use `get_progress_target()` and `progress_callback`. Report what
  completed before a failure so callers know whether it is safe to retry.

Test how results serialize, progress reporting, and failures partway through. Run
the installed macro in the UI with the intended user permissions and check its effects;
Headless has no macro execution tool.
