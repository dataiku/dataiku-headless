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
4. After installation, read `code_env.status`. Local sources inspect the normalized
   archive for `code-env/python/desc.json` and `code-env/R/desc.json`: `required` means
   a descriptor exists; `not_required` means neither exists. Store installation returns
   `unknown` because the public plugin listing does not expose the specification.
   For `required` or `unknown`, call `ensure_plugin_code_env` as a separate step.
   This uses the plugin's default interpreter unless explicitly overridden, creates
   a PLUGIN_MANAGED environment, and binds it after the build finishes. A bound name
   alone does not establish build success.
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

- `ensure_plugin_code_env` uses the public plugin creation API, never the generic
  `create_code_env` admin tool. DSS `ERR_PLUGIN_WITHOUT_CODEENV` maps to
  `status: "not_required"`. The pinned SDK drops structured error codes, so the exact
  public endpoint's no-specification message is recognized too. Permission errors,
  invalid interpreters, and other failures remain errors and carry Dataiku's reason.
- Creation and binding are separate DSS calls. `still_running` carries a `future_id`;
  resume `ensure_plugin_code_env` with that exact ID and plugin on the same instance.
  Do not start another build. Dataiku forgets a build once its result is read, so a
  `future_id` only resumes a build that has not yet been reported finished. A future
  that is not this plugin's build is refused without being read.
- An unbound managed environment may still be building. `recovery_required` lists
  the candidates in `code_env_names` and refuses to guess or create a duplicate.
  Resume the original future while it runs. Otherwise check the candidates with
  `list_code_envs`, then bind one with `code_env_name`. That binds without building,
  so its `build.status` is `unknown`.
- `binding_failed` carries the environment name, build outcome, and Dataiku's
  `error`. Fix the cause, then call again with that `code_env_name`.
  `binding_changed` means another binding was set during the build and was kept; ask
  the user which environment the plugin should use.
- `python_interpreter`, `future_id`, and `code_env_name` are mutually exclusive. An
  already-bound plugin refuses a different environment or interpreter.
- `build.status` can be `completed`, `failed`, or `unknown`. A dependency failure is
  reported beside the durable environment name, even when binding succeeds. An
  already-bound environment is returned without creating another or claiming its
  previous build succeeded. Never treat mere `status: "completed"` as plugin readiness.
- `update_plugin(rebuild_code_env=true)` updates the plugin and rebuilds its
  already-bound environment. It does not create or bind one. For a standalone rebuild,
  use the UI rather than repeating a plugin update solely to trigger a rebuild.
- A rebuild keeps the interpreter and core-package set the environment was created
  with; changes to those fields in `desc.json` do not reach an existing environment.
  When a build fails for that reason, rebuilding again cannot fix it: after correcting
  `desc.json`, ask the user to recreate the environment in the Dataiku UI.
- `not_required` concerns code environments only. Install scripts, system packages,
  presets, and other configuration may still need work in the Dataiku UI. No tool
  claims these checks are complete.
- Inspect environments with `list_code_envs` per `./code-environments.md`. Packages
  come from the plugin's specification and are not editable via `update_code_env`.

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
  user every page from `list_plugin_usages`. Deleting a plugin does not delete its code
  environment.

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
