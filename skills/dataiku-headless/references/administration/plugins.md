---
name: plugins
description: Discover installed Dataiku plugins, update one from the plugin store or a local path, and remove it.
---

# Plugins

Use this guide when the user asks what plugins an instance has, wants one updated or
removed. Plugin management is a direct-write exception: it is
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
3. Update an installed plugin with `update_plugin`, or remove it with `delete_plugin`.
4. `code_env_name: null` means no environment is bound; it does not tell you whether
   one is required. Check requirements and perform initial setup in the Dataiku UI.
5. After any change, re-read the plugin and report `needs_restart` when it is true.

## Update sources

Use the installed id returned by `list_plugins`. A `source="store"` update requires
that the plugin came from the store. These tools do not browse the store catalog or
install new plugins; use the Dataiku UI for installation.

For `source="local_path"`, a ZIP may hold `plugin.json` at its root or inside one wrapper
directory — what a GitHub "Download ZIP" produces — and the wrapper is dropped before
upload. The archive's own manifest names the target, so you cannot update the wrong
plugin by mistake.

There is no Git update tool: that needs Git authentication configured on the
Dataiku instance, which cannot be arranged from here. Clone the repository locally and
use `source="local_path"`, or do it in the Dataiku UI.

## Long-running operations

Each update or deletion response carries `status` — `started`, `still_running`, `completed`, or `refused` —
plus the `operation` it describes.

- `started` and `still_running` mean the work is in flight. Follow the returned
  `future_id` per `../jobs.md`, and **do not start a duplicate operation**.
- An update that does not complete inline never starts its rebuild, and reports
  `code_env_rebuild.status: "not_started"`. Follow the update, then ask for the rebuild
  again.
- Dataiku reports a failed action as an ordinary successful response, so the absence of
  an error is not evidence of success. Update and delete check the reported
  outcome before returning `completed`; for code environments, read the nested build
  status.

## Code environments

- Initial plugin code-environment creation and binding are out of scope. The tools
  report a bound environment name but do not establish whether an unbound plugin
  requires one. Use the Dataiku UI to inspect requirements and complete setup; do not
  substitute `create_code_env` for plugin-managed environment creation.
- `update_plugin(rebuild_code_env=true)` updates the plugin, then rebuilds its
  **already-bound** environment from the plugin's specification. It does not create or
  bind an environment. If none is bound, `code_env_rebuild.status` is `skipped` and the
  response directs you to the Dataiku UI. This is not evidence that no environment is
  needed.
- A rebuilt environment can still have failed to build. Read `code_env_rebuild` before
  treating the plugin as ready: `status: "failed"` includes the dependency error even
  though the plugin update itself completed. Fix the plugin's specification before
  retrying; setup changes that require recreating an environment belong in the Dataiku UI.
- Inspect a bound environment with `list_code_envs` per `./code-environments.md`. Its
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
- `update_plugin`
- `delete_plugin`
