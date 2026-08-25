---
name: plugins
description: Discover installed Dataiku plugins and install or update plugins from the Plugin Store. Use to check whether a plugin and version is present before relying on its recipes or components, and to follow a Store install or update to completion.
---

# Plugins

Instance-level plugin operations that Cobuild cannot perform.

1. Call `list_plugins` to inspect installed IDs and versions.
2. Use `install_plugin_from_store` only when the plugin is absent.
3. Use `update_plugin_from_store` only when the plugin is already installed.

## Following a Store operation

Both writes start a Dataiku future and return a `future_id` by default. Follow it with
`get_future_status(future_id, fetch_result=true)` and do not start the same operation
again while it is running. If Dataiku answers with an inline completed result, the tool
returns the resulting plugin state immediately.

Set `wait_for_completion=true` to wait inline, bounded by `timeout_seconds` (default 50,
max 3600). Store installs pull code environments and can take minutes, so treat the
statuses the way `../jobs.md` treats job supervision:

- `*_still_running` — the timeout elapsed, **not** a failure. Follow the `future_id`.
- `*_poll_failed` — the operation started but polling broke. Keep the `future_id`,
  inspect it, then confirm with `list_plugins`. Do not start a replacement.
- `*_completed` without a `plugin` field — Dataiku reported success but the plugin is
  not listed yet and may need an instance restart. Confirm with `list_plugins`.

Installing regular plugins requires instance administrator privileges. Let Dataiku
enforce the configured user's effective permissions.

Local archives, settings, usage analysis, deletion, and plugin code environments are
outside this tool surface.
