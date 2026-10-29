---
name: plugins
description: Inspect, install, update, and remove Dataiku plugins and set up their managed code environments.
---

# Plugins

Use this guide when the user asks what plugins an instance has, wants one installed, updated, or
removed, or needs its initial code environment prepared. Plugin management is a direct-write exception: it is
instance-wide, not an in-project asset, and Cobuild cannot perform it.

Plugin operations need administrator permission, permission to develop plugins, or
administrator rights on the specific plugin. Dataiku enforces this.

## Plugin Concepts

A plugin installs components — recipes, connectors, agent tools, webapps, macros,
scenario steps — for the whole instance. Some plugins declare a managed code environment
whose packages come from the plugin rather than from you.

A plugin's `dev` flag marks a development plugin, edited in place on the instance rather
than installed from a released archive. Do not update or delete one unless the user asks
for that plugin by name; someone is working in it.

## Workflow

1. Call `list_plugins` first. Search matches the plugin id, its label, and its tags, so
   "the SharePoint plugin" or "Answers" resolve without knowing the id.
2. Use `search_mode="exact"` with `include_details=true` to inspect one plugin before
   changing it. Details cost one settings read per row, so pair them with `search`.
3. In stdio, use `install_plugin` for a new plugin or `update_plugin` for an existing
   one. Both tools are unavailable in Streamable HTTP because their sources can be
   local server paths. `delete_plugin` removes an installed plugin.
4. After installation, read `code_env.status`: `required` when a local archive has
   `code-env/python/desc.json` or `code-env/R/desc.json`, `not_required` when it has
   neither, and `unknown` for store installs. For `required` or `unknown`, call
   `ensure_plugin_code_env` as described under Code environments.
5. After any change, re-read the plugin and report `needs_restart` when it is true.

## Update sources

Use the installed id returned by `list_plugins`. A `source="store"` update requires
that the plugin came from the store. These tools do not browse the store catalog. For installation, get the exact store
id from the user or an authoritative plugin source; never guess it.

For `source="local_path"`, a ZIP may hold `plugin.json` at its root or inside one wrapper
directory — what a GitHub "Download ZIP" produces — and the wrapper is dropped before
upload. The archive's own manifest names the target, so you cannot update the wrong
plugin by mistake.

There is no Git update tool: that needs Git authentication configured on the
Dataiku instance, which cannot be arranged from here. Clone the repository locally and
use `source="local_path"`, or do it in the Dataiku UI.

## Long-running operations

Each install, update, or deletion response carries `status` — `started`, `still_running`, `completed`, or `refused` —
plus the `operation` it describes.

- `started` and `still_running` mean the work is in flight. Follow the returned
  `future_id` per `../jobs.md`, and **do not start a duplicate operation**.
- If `code_env_rebuild.status` is `not_started`, follow the update to successful
  completion, then ask the user to rebuild in the Dataiku UI. If the rebuild is already
  running, follow its own `future_id`.
- Do not repeat `update_plugin` solely to start or retry an environment rebuild.
- Dataiku reports a failed action as an ordinary successful response, so the absence of
  an error is not evidence of success. Update and delete check the reported
  outcome before returning `completed`; for code environments, read the nested build
  status.

## Code environments

- `ensure_plugin_code_env` creates the plugin's PLUGIN_MANAGED environment and binds it
  once the build finishes. Never substitute `create_code_env`. `not_required` means the
  plugin declares no environment; install scripts, system packages, and presets may
  still need the Dataiku UI.
- `python_interpreter`, `future_id`, and `code_env_name` are mutually exclusive.
  `python_interpreter` only applies to a new environment. An already-bound plugin is
  returned as is and refuses a different environment or interpreter.
- On `still_running`, resume with the same `plugin_id` and `future_id` on the same
  instance; never start another build. Dataiku forgets a build once its result is
  read, so a `future_id` only resumes a build that has not been reported finished.
- `recovery_required` means an unbound managed environment already exists and may
  still be building. Resume its future while it runs; otherwise check
  `code_env_names` with `list_code_envs` and pass one as `code_env_name`.
- `binding_changed` means someone else bound another environment during the build.
  That binding is kept; ask the user which environment the plugin should use.
- Top-level `completed` means the environment is bound, not that it works. Read
  `build.status` (`completed`, `failed`, or `unknown`) before treating the plugin as
  ready.
- `update_plugin(rebuild_code_env=true)` rebuilds an already-bound environment; it
  never creates or binds one. A rebuild keeps the interpreter and core-package set the
  environment was created with, so after correcting those in `desc.json`, ask the user
  to recreate the environment in the Dataiku UI.
- Inspect environments with `list_code_envs` per `./code-environments.md`. Their
  packages come from the plugin and are not editable via `update_code_env`.

## Deletion

- `delete_plugin` checks usages first and refuses with `deleted: false` when any exist.
  Do not conclude a plugin was removed until `deleted` is true. Its response is a
  compact sample: use `list_plugin_usages` until `next_offset` is null before deciding
  whether to remove the blockers or force deletion.
- Dataiku also refuses when it cannot currently resolve the plugin's components, the
  usual state for a plugin installed or updated since the last backend reload. That
  returns `status: "refused"` with Dataiku's own `reason`; reloading the backend and
  retrying is the clean fix. Its analysis reports unresolvable component types for the
  whole instance, so only entries attributable to this plugin come back, as
  `unresolvable_components`.
- `force=true` deletes despite usages and **breaks every blocker**, including blockers
  omitted from the initial refusal. Use it only on explicit instruction after showing the
  user every page from `list_plugin_usages`. Deleting a plugin also deletes its
  plugin-managed code environments.

## Out of scope

- **Plugin settings, presets, and parameter sets.** These commonly hold credentials, and
  parameter names are not a secrecy boundary either, so no tool reads or writes them, and
  `list_plugins` never returns plugin configuration. Configure presets in the Dataiku UI.
- Project-level plugin settings, plugin file editing, and plugin download. Development
  plugin authoring happens in the Dataiku UI or in a checkout.

## Preferred Tools

- `list_plugins`
- `list_plugin_usages`
- `install_plugin`
- `ensure_plugin_code_env`
- `update_plugin`
- `delete_plugin`
