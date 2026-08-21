# Plugins

Use these tools for instance-level plugin discovery, installation, updates, settings,
code environments, and usage analysis. Plugin changes are a
documented direct-write exception because they are instance-wide and Cobuild cannot
perform them.

## Inspect first

1. Call `list_plugins` to discover installed IDs and development status.
2. Call `get_plugin` before changing an installed plugin.
3. Call `list_plugin_usages` before deletion, especially before force deletion. Read
   `usage_count` for this plugin; `instance_missing_types` describes unresolvable
   component types across the whole instance, not usages of this plugin, so treat it
   as a signal that the analysis may be incomplete.
4. Call `list_code_envs` before assigning an existing code environment.

Installing regular plugins requires instance administrator privileges. Development
plugin operations may instead accept the Develop plugins permission. Let Dataiku
enforce the configured user's effective permissions for the requested operation.

## Install and update

Choose the tool that exactly matches the source and intent:

- Store: `install_plugin_from_store` or `update_plugin_from_store`.
- User-supplied local directory or ZIP: `install_plugin_from_local_path` or
  `update_plugin_from_local_path`.

Do not substitute install for update or update for install. Local directories must
contain `plugin.json`; local ZIPs may contain it at the root or inside one
unambiguous wrapper directory. The update tool verifies that the archive's plugin ID
matches the requested installed plugin. Local directories and ZIPs reject unsafe paths,
duplicate members, symbolic links, and any hidden path component. Package a clean
directory or ZIP without `.git`, `.env`, `.aws`, or other hidden paths.

There is no Git install or update tool. Installing a plugin from Git needs Git
authentication configured on the Dataiku instance, which cannot be arranged from here;
do it in the Dataiku UI, or clone the repository locally and use the local-path tools.

Store and code-environment operations return a future ID by default. Follow it
with `get_future_status(fetch_result=true)` and do not start a duplicate operation
while it is running. Set `wait_for_completion=true` when the expected duration is
appropriate for one tool call; those paths re-read the resulting plugin state before
returning. When Dataiku finishes an operation before it answers there is no future to
follow, so the tool reports `*_completed` with the plugin state even though
`wait_for_completion` was false. Dataiku can also complete a future whose result
reports failure rather than returning an HTTP error; the tool raises in that case, so
a `*_completed` status means the operation actually succeeded.

After local installation or update, the tool immediately re-reads the plugin. DSS may
require a backend restart before newly installed or updated component types appear in
the UI catalog.

## Settings and code environments

- `get_plugin` returns configured key names but never plugin configuration values.
  Plugin-level configuration commonly contains credentials, and parameter names are
  not a reliable secrecy boundary.
- `update_plugin_settings` merges the supplied structured config keys, saves, and
  verifies them with a fresh read. It does not replace unrelated keys or echo saved
  values.
- `create_plugin_code_env` creates the environment but Dataiku does not bind it to the
  plugin. The response reports `created_code_env_name` alongside
  `bound_code_env_name`, which stays null until you bind it.
- `set_plugin_code_env` assigns an existing environment and verifies the saved
  binding.
- `update_plugin_code_env` rebuilds the currently bound environment and fails if no
  environment is bound.

Always call `set_plugin_code_env` with the created name straight after
`create_plugin_code_env`. Until the plugin is bound, the duplicate guard has nothing to
read, so a second `create_plugin_code_env` call silently creates another environment
with a numbered suffix; `force=true` only overrides the guard once a binding exists.
Deleting a plugin removes the environment bound to it but leaves any unbound duplicate
behind, so an accidental extra environment has to be deleted by hand.

## Components

There is no component-discovery tool. `list_plugin_usages` returns `element_type` for
components already in use, which is the authoritative type string from Dataiku; use it
when you need a component's type. The public API cannot enumerate components from
installed non-development plugins at all, and for development plugins the file tree
does not map reliably onto usable type strings, so do not infer type strings from
directory names.

## Delete

Use `delete_plugin` only after inspecting usages. Normal deletion lets Dataiku refuse
an in-use plugin. Dataiku also refuses `force=false` when any component type is
unresolvable anywhere on the instance, even for a plugin with zero usages, so a
refusal is not by itself evidence that the plugin is in use. The refusal message says
which of the two applies. `force=true` overrides both; confirm with the user before
using it on a plugin whose reported `usage_count` is above zero. User confirmation is
handled by the calling agent harness. The tool waits for deletion and verifies that
the plugin no longer appears in the installed list.
