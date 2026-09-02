---
name: plugins
description: Discover installed Dataiku plugins, install or update one from the plugin store or a local path, give it a code environment, and remove it.
---

# Plugins

Use this guide when the user asks what plugins an instance has, wants one installed or
updated, or wants one removed. Plugin management is a direct-write exception: it is
instance-wide, not an in-project asset, and Cobuild cannot perform it.

Plugin operations need administrator permission, permission to develop plugins, or
administrator rights on the specific plugin. Dataiku enforces this.

## Plugin Concepts

A plugin installs components — recipes, connectors, agent tools, webapps, macros,
scenario steps — for the whole instance. Its Python components run in a code environment
that the plugin declares and Dataiku builds, named `plugin_<plugin id>_managed`, whose
packages come from the plugin rather than from you.

A plugin's `dev` flag marks a development plugin, edited in place on the instance rather
than installed from a released archive. Do not update or delete one unless the user asks
for that plugin by name; someone is working in it.

## Workflow

1. Call `list_plugins` first. Search matches the plugin id, its label, and its tags, so
   "the SharePoint plugin" or "Answers" resolve without knowing the id.
2. Use `search_mode="exact"` with `include_details=true` to inspect one plugin before
   changing it. Details cost one settings read per row, so pair them with `search`.
3. Install with `install_plugin`, update with `update_plugin`; neither substitutes for
   the other.
4. If `code_env_name` is null and the plugin declares an environment, see
   *Code environments* below.
5. After any change, re-read the plugin and report `needs_restart` when it is true.

## Finding a store plugin id

Dataiku exposes **no API for browsing the plugin store**, so no tool lists what is
available and `install_plugin` cannot resolve a name for you. Get the exact id first:

- Store plugins are published as `github.com/dataiku/dss-plugin-<plugin id>`, so the
  repository slug after `dss-plugin-` is the id.
- If another instance already has it, `list_plugins` there returns the exact id.
- Otherwise ask the user. Do not guess an id and install on the chance it resolves.

An unknown id fails with Dataiku's own wording, "Plugin has since been removed from the
store," which does not distinguish a wrong id from a withdrawn plugin. Assume a wrong id.

For `source="local_path"`, a ZIP may hold `plugin.json` at its root or inside one wrapper
directory — what a GitHub "Download ZIP" produces — and the wrapper is dropped before
upload. The archive's own manifest names the target, so you cannot update the wrong
plugin by mistake.

There is no Git install or update tool: that needs Git authentication configured on the
Dataiku instance, which cannot be arranged from here. Clone the repository locally and
use `source="local_path"`, or do it in the Dataiku UI.

## Long-running operations

Every response carries `status` — `started`, `still_running`, `completed`, or `refused` —
plus the `operation` it describes.

- `started` and `still_running` mean the work is in flight. Follow the returned
  `future_id` per `../jobs.md`, and **do not start a duplicate operation**; a second
  code-environment creation is what produces `plugin_<id>_managed_1` duplicates.
- `create_plugin_code_env` is safe to re-run after a timeout: it binds an existing
  unbound environment for that plugin instead of creating another one. Because the
  earlier build result is unavailable, the recovered environment reports
  `build.status: "unknown"`; rebuild it before treating the plugin as ready.
- Dataiku reports a failed action as an ordinary successful response, so the absence of
  an error is not evidence of success. Install, update, and delete check the reported
  outcome before returning `completed`; for code environments, read the nested build
  status.

## Code environments

- **A created or rebuilt environment can exist and still have failed to build.** Read
  `build` on `create_plugin_code_env` and `code_env_rebuild` on `update_plugin`: either
  can report `status: "failed"` with the dependency error while the environment is bound.
  That is reported rather than raised, because the environment exists and creating
  another is not the fix. Do not call a plugin ready without checking that field.
- Rebuild after a dependency change with `update_plugin(rebuild_code_env=true)`.
- A plugin whose `code-env/python/desc.json` sets `installCorePackages: true` inherits
  Dataiku's core pins, which can fail to build on a recent interpreter. That flag is
  fixed on the environment at creation, so a rebuild cannot clear it: delete the
  environment with `delete_code_env`, fix the plugin, then create it again.
- Inspect the environment with `list_code_envs` per `./code-environments.md`. Its
  packages come from the plugin's specification and are not editable through
  `update_code_env`.

## Deletion

- `delete_plugin` checks usages first and refuses with `deleted: false` when any exist.
  Do not conclude a plugin was removed until `deleted` is true. `usages` is capped;
  `usage_count` is the true total.
- Dataiku also refuses when it cannot currently resolve the plugin's components, the
  usual state for a plugin installed or updated since the last backend reload. That
  returns `status: "refused"` with Dataiku's own `reason`; reloading the backend and
  retrying is the clean fix. Its analysis reports unresolvable component types for the
  whole instance, so only entries attributable to this plugin come back, as
  `unresolvable_components`.
- `force=true` deletes despite usages and **breaks every listed object**. Use it only on
  explicit instruction after showing the user the usage list. Deleting a plugin does not
  delete its code environment.

## Out of scope

- **Plugin settings, presets, and parameter sets.** These commonly hold credentials, and
  parameter names are not a secrecy boundary either, so no tool reads or writes them, and
  `list_plugins` never returns plugin configuration. Configure presets in the Dataiku UI.
- Project-level plugin settings, plugin file editing, and plugin download. Development
  plugin authoring happens in the Dataiku UI or in a checkout.

## Preferred Tools

- `list_plugins`
- `install_plugin`
- `update_plugin`
- `create_plugin_code_env`
- `delete_plugin`
