---
name: plugins
description: Discover store plugins, manage installed Dataiku plugins, and set up their managed code environments.
---

# Plugins

Use this guide to find store plugins, inspect installed plugins, install, update, or
remove one, or prepare its initial code environment. Plugin management is a direct-write exception: it is
instance-wide, not an in-project asset, and Cobuild cannot perform it.

To build or update the plugin itself, start with
[Plugin development](../plugin-development.md), then return here to install it.

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
3. Use `install_plugin` for a new plugin or `update_plugin` for an existing one, and
   `delete_plugin` to remove one. `source="local_path"` works only in stdio, because
   it reads the server's filesystem. Store and Git sources work in both transports.
4. After installation, read `code_env.status`: `required` when a local archive has
   `code-env/python/desc.json` or `code-env/R/desc.json`, `not_required` when it has
   neither, and `unknown` for store or Git installs. For `required` or `unknown`, call
   `ensure_plugin_code_env` as described under Code environments.
5. Verify with `list_plugins(search=plugin_id, search_mode="exact")`: after an
   install or update, confirm the installed id and returned version; after deletion,
   confirm the id is absent. After environment setup, add `include_details=true` and
   confirm `code_env_name` matches the setup result, then read `build.status`.
   Report `needs_reload` and `needs_restart` when true. Installation and environment
   setup alone do not show that the components work.

## Sources

### Store discovery

`list_plugins` searches installed plugins. To discover store plugins and releases,
fetch the public catalog with the agent's web or HTTP tools:

1. Read the target Dataiku version with `get_current_instance`, or use the version
   the user is planning for.
2. Fetch `https://update.dataiku.com/dss/{major_version}/plugins/list.json`:
   [Dataiku 15](https://update.dataiku.com/dss/15/plugins/list.json) or
   [Dataiku 14](https://update.dataiku.com/dss/14/plugins/list.json), for example.
3. Search `items` by `id`, `meta.label`, `meta.description`, or `meta.tags`. Read
   `storeVersion` for the offered version and `revisions` for listed releases and
   release notes. Check `storeFlags.downloadable` and the plugin's documentation
   for requirements specific to a minor version or environment.
4. Use the catalog's exact `id` for installation; never guess it. For updates, use
   the installed ID from `list_plugins` and compare its version with `storeVersion`.

A `source="store"` update requires that the plugin came from the store. Store calls
do not accept a release version; listing a revision does not select it for installation.

### Local archives

For `source="local_path"`, a ZIP may hold `plugin.json` at its root or inside one wrapper
directory — what a GitHub "Download ZIP" produces — and the wrapper is dropped before
upload. The archive's own manifest names the target, so you cannot update the wrong
plugin by mistake.

### Git sources

Use `install_plugin(source="git", repository_url=..., checkout=...)` to have Dataiku
fetch a repository. Choose an explicit branch, tag, or commit; use a commit for a
reproducible installation. `subpath` is the UI's **Path in repository**: set it to
the relative folder containing `plugin.json` (for example, `plugins/my-plugin`),
or omit it for the repository root.
Omit `plugin_id` and `local_path`: the remote manifest determines the installed ID.
This installs a packaged plugin, not an editable development plugin.

For a Git update:

1. Use the local agent's Git or GitHub access to read `plugin.json` at the chosen
   branch, tag, or commit and `subpath`.
2. Confirm its ID matches the installed plugin. Dataiku takes the update target
   from the fetched manifest, so this check belongs to the agent.
3. Call `update_plugin(source="git", plugin_id=..., repository_url=...,
   checkout=...)` with the same revision and `subpath`. Use a commit SHA when you
   need to ensure the revision cannot move after inspection.
4. Verify the installed ID and version. The tool also checks Dataiku's reported ID
   before starting any requested environment rebuild.

If the agent cannot read the repository, explain which access is missing and help
the user set it up before updating. Local Git access is separate from Dataiku's
access described below.

### Git access

Dataiku fetches repositories using its own Git configuration. Logging into GitHub
or configuring Git on the Headless machine does not provide that access. Public
repositories may need no credentials; private repositories need read access.

If access fails, help the user check the following in the
[Git setup guide](https://doc.dataiku.com/dss/latest/collaboration/git.html)
for their Dataiku version:

- An administrator must allow the repository in **Administration > Settings > Git**.
- Where per-user SSH keys are supported and enabled, use **Profile > Credentials >
  SSH** and register the public key with the Git provider. Enter private keys and
  passphrases only in Dataiku's credential UI.
- For admin-managed SSH or HTTPS, an administrator configures credentials on the
  Dataiku server. Access must work without interactive prompts; SSH host keys must
  be validated.

Authentication failures suggest missing credentials or repository permission.
“Repository not found” can also mean a wrong URL or a private repository the user
cannot access. Check host-key, network, checkout, and subpath errors separately.
Never ask for secrets in chat or put tokens in repository URLs. Headless does not
configure Git credentials.

## Long-running operations

Each install, update, or deletion response carries `status` — `started`, `still_running`, `completed`, or `refused` —
plus the `operation` it describes. Git operations can also return
`verification_required`: Dataiku reported completion, but the installed plugin
could not be verified. Inspect `list_plugins` before retrying or preparing its environment.

- `started` and `still_running` mean the work is in flight. Follow the returned
  `future_id` per [Jobs](../jobs.md), and **do not start a duplicate operation**.
  For Git installation, the plugin ID may only become known on completion. If you
  fetch a Git operation's result yourself, check `pluginDesc.desc.id` (against the
  expected ID for updates) and verify it with `list_plugins`.
- Git errors omit raw subprocess output, which may contain secrets. Follow any
  returned future ID or inspect installed plugins before retrying after a failure.
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
  Do not fetch this build's result with `get_future_status(fetch_result=true)`;
  `ensure_plugin_code_env` needs that result to finish binding the environment.
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

- **Installed plugin settings, presets, and parameter sets.** These commonly hold credentials, and
  parameter names are not a secrecy boundary either, so no tool reads or writes them, and
  `list_plugins` never returns plugin configuration. Configure presets in the Dataiku UI.
- Project-level plugin settings, editing files on the instance, and plugin download.
  You can write plugin files and parameter-set descriptors locally using the
  development guide; users enter actual preset values in the UI.

## Preferred Tools

- `list_plugins`
- `list_plugin_usages`
- `install_plugin`
- `ensure_plugin_code_env`
- `update_plugin`
- `delete_plugin`
