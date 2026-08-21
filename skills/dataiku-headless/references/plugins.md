# Plugins

Use these tools to discover installed plugins and install or update plugins from the
Dataiku Plugin Store. These are instance-level operations that Cobuild cannot perform.

1. Call `list_plugins` to inspect installed IDs and versions.
2. Use `install_plugin_from_store` only when the plugin is absent.
3. Use `update_plugin_from_store` only when the plugin is already installed.

Store operations return a future ID by default. Follow it with
`get_future_status(fetch_result=true)` and do not start the same operation again while
it is running. Set `wait_for_completion=true` when waiting in one tool call is useful.
If Dataiku answers with an inline completed result, the tool returns the resulting
plugin state immediately.

Installing regular plugins requires instance administrator privileges. Let Dataiku
enforce the configured user's effective permissions.

Local archives, settings, usage analysis, deletion, and plugin code environments are
outside this tool surface.
