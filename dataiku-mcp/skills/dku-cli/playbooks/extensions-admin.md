# Extensions & Admin Playbook

Build reusable capabilities (plugins, webapps), govern AI initiatives, and operate
the instance (auth, connections, code envs, deploy, bundles).

Exact flags always come from `<command> --help`. This file is sequencing + traps.
Destructive-op tiers and exit 77: see `references/safety.md`.

## Canonical commands

```bash
# Plugin deploy
dku plugin push <dir|zip> --install
dku plugin create-code-env PLUGIN_ID -P PROJ
dku plugin set-code-env PLUGIN_ID ENV_ID -P PROJ
dku plugin get PLUGIN_ID -o json
dku plugin recipes PLUGIN_ID -P PROJ

# Admin
dku auth login --url URL --api-key KEY --profile NAME
dku whoami
dku connection list -o json
dku code-env list
dku admin instance-info
dku user list
```

## When to build a plugin vs. anything else

Reach for a plugin only when a capability must be **reusable across projects** and
packaged: a custom recipe/connector, an agent tool/guardrail, or a shippable webapp.
For a one-off transform prefer a visual/code recipe in the project. Pick the plugin
tier before writing code (1 utility → 5 enterprise platform); see `references/plugins.md`.

---

## Plugins: scaffold → develop → test → deploy

### 1. Scaffold
Plugin root = a directory containing `plugin.json` (id is immutable after first release).
Layout: `python-lib/<pkg>/` holds core logic with **zero `dataiku` imports** (testable
without DSS); component dirs (`custom-recipes/`, `python-agent-tools/`, `webapps/`, …) are
thin wrappers. `code-env/python/desc.json` + `spec/requirements.txt` declare deps —
**always include pandas, numpy, python-dateutil, requests** (the `dataiku` runtime imports
them at load even if you don't). Component dir → recipe type mapping and `plugin.json`
fields: `references/plugins.md`.

### 2. Develop
Add one component dir at a time (recipe / agent-tool / guardrail / webapp). Format with
`ruff` before pushing. Dev-plugin files are editable remotely:
`dku plugin list-files`, `get-file`, `put-file`, `rename-file`, `move-file`.

### 3. Test
Core logic in `python-lib/` → fast unit tests, mock at the DSS boundary (`dataiku` module).
Component wrappers → mock `get_recipe_config` / tool `invoke` input. Integration tests run
against a live DSS (`dataiku-plugin-tests-utils`). Patterns: `references/plugins.md`.

### 4. Deploy (CLI)
```
# First install
dku plugin push <dir|zip> --install
dku plugin create-code-env <plugin>       # NOT auto-created on install
dku plugin set-code-env <plugin> <env>    # without this, backend runs on bare DSS Python
# Update
dku plugin push <dir|zip>
dku plugin update-code-env <plugin>       # only if deps changed
# Verify
dku plugin get <plugin> -o json
dku plugin recipes <plugin>               # registered recipe types
dku plugin usages <plugin>                # check before delete
```
Gotchas (fixes inline):
- **Code env never auto-creates** → backend silently runs without your deps. Always
  `create-code-env` + `set-code-env` after first install.
- **Recipe type is `CustomCode_<recipeDir>`** — plugin id is NOT in the string. Verify
  with `dku plugin recipes`; a fresh install may need a DSS restart to register types.
- **ZIP must have `plugin.json` at root** — zipping the parent folder is rejected.
- **`create-code-env` failure leaves a broken env** → delete it before retrying.
- **`plugin push` accepts a directory or a `.zip`**; it auto-detects install vs update.
- `dku plugin delete --force` deletes even when in use; requires `--yes`.

### Review
Spawn the `plugin-reviewer` agent for a scored report. Fallback: read all source, apply
the checklist in `references/plugins.md`, run `ruff check` + `ruff format --check`.

---

## Webapps: backend → frontend → deploy

Two kinds: **project webapp** (4-tab editor in a project) and **plugin webapp**
(`webapps/<id>/` shipped in a plugin). Framework: prefer **DASH** for data/chart-driven
apps, **STANDARD** for handcrafted HTML/CSS/JS. Durable patterns: `references/webapps.md`.

There is **no public API to create a webapp** — create it in the DSS UI, then drive it:
`dku webapp start | stop | restart | status | logs | get-definition | set-definition`.
No `delete` via API (DSS returns 405) — delete in the UI.

Backend rule (the #1 failure): **never write `app = Flask(__name__)`** in a plugin webapp —
DSS injects `app` globally and registers `/__ping`; shadowing it makes the backend never
start. Import config from `dataiku.customwebapp` (NOT `dataiku.webapp`). Dash/Streamlit
backends DO define their own app object.

Frontend rule: call backends via `window.getWebAppBackendUrl('endpoint')` (no `/api/`
prefix; route names must match `@app.route`). In plugin webapps the function lives on
`window.parent` — check both.

Deploy: SPA frontends build to `resource/dist/` (Vite **single-bundle** output, see
gotchas), then reload the plugin. Debug after restart:
```
dku webapp restart <id> -P <proj>        # blocks until up or crashed; prints crash reason + log tail on failure (exit 1)
dku webapp logs   <id> -P <proj>         # shows live tail OR last crash tail if backend is down
dku webapp logs   <id> -P <proj> --follow | grep -Ei 'error|traceback'
```
`start`/`restart` wait on the boot future — no need to poll `status` separately.
`webapp logs` falls back to `lastCrashLogTail` when the backend has crashed, so
you get the traceback even before attempting a restart. Capped at ~80 server-side
lines; use `--follow` for live tail (refused when backend is stopped).

Top webapp gotchas (fixes in `references/webapps.md`): wrong folder (`webapps/` not
`custom-webapps/`); missing `app.js`/`meta.json`; missing `codeEnv: PLUGIN_MANAGED`;
Vite code-splitting/base-path breaking resource loading; WebSockets unsupported (poll only);
plugin dir is read-only (use `workload_local_folder`); DSS caches `body.html` (recreate the
instance after editing it).

---

## Govern

Tracked approval workflows for AI/ML initiatives (artifacts → blueprints → sign-offs) have
their own playbook: **`playbooks/govern.md`** (payload shapes in `references/govern.md`).

---

## Admin & deploy

All admin commands need an admin API key (403 otherwise). Instance-level commands take no
`-P`. Destructive tiers + exit 77 + admin lockout risks: `references/safety.md`.

**connection** — `list --type` filters by connector; `test` works on SQL/cloud only
(filesystem/LLM exit 2 — use `get` to inspect); `schemas`/`tables` need project context.

**code-env** — `dku code-env list`/create/update; plugin-managed envs are created via
`dku plugin create-code-env`.

**api-service → api-deployer** (deploy a model endpoint to API nodes, instance-level):
```
dku api-service create-package <svc> --package v1     # --package is required
dku api-service publish-package <svc> v1
dku api-deployer create-deployment --service-id <svc> --infra-id <infra> ...
dku api-deployer deployment-status <dep> -o json      # health, service_urls
```
Flags are `--service-id`/`--infra-id` (not `--service`/`--infra`). On a `WARNING :`
validation failure (e.g. Govern unreachable on a sandbox) retry with `--ignore-warnings`.

**project-deployer / bundle** (deploy project bundles to Automation nodes): flags are
`--project-id`/`--infra-id`/`--bundle-id`; same `--ignore-warnings` retry. `dku bundle
activate` runs preload then activate.

**Other instance ops:** `dku user`, `dku api-key` (secret shown once; `--admin` for full
rights, else no permissions), `dku admin` (`logs`/`get-log`, `usage`, `instance-info`,
`sanity-check`), `dku cluster` (managed only; `delete` does not stop first),
`dku meaning`, `dku project-folder`, `dku workspace`, `dku git` (per-project; all need `-P`).

---

## Auth / profile setup

```
dku auth login                                  # interactive: prompts URL + key, stores in keyring
dku auth login --url <url> --api-key <key> --profile prod   # non-interactive / CI
dku auth list | status | switch <profile> | logout
dku whoami                                      # confirm node type (DESIGN/AUTOMATION/GOVERN)
```
Env vars `DKU_URL` / `DKU_API_KEY` / `DKU_PROJECT` override saved profiles (CI). A profile
showing `[?]` node type predates node-type tracking — re-run `auth login --profile <name>`.
Don't merge stderr into stdout before `jq`: parse stdout on success; for machine-readable
failures use the global `dku --errors json …` (before the noun).
