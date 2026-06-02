# dku-cli Admin, Deployment, and Instance Command Syntax

Exact command syntax for plugins, deployment, identity, connections, admin, and instance-wide resources. Read `safety.md` and `admin-safety.md` before destructive commands.

## plugin

Instance-level (no project needed).

```bash
dku plugin list [-o FORMAT]
dku plugin get PLUGIN_ID [-o FORMAT]
dku plugin push ZIP_OR_DIR [--update/--install]
dku plugin delete PLUGIN_ID [--confirm/--yes/-y] [--force]
dku plugin settings PLUGIN_ID [-o FORMAT] [--set key=value ...]
dku plugin create-code-env PLUGIN_ID [--wait/--no-wait] [-o FORMAT]
dku plugin set-code-env PLUGIN_ID ENV_NAME
dku plugin update-code-env PLUGIN_ID [--wait/--no-wait]
dku plugin usages PLUGIN_ID [-P PROJECT] [-o FORMAT]
dku plugin recipes [PLUGIN_ID] [-o FORMAT]
dku plugin list-files PLUGIN_ID [-o FORMAT]
dku plugin get-file PLUGIN_ID --path FILE_PATH
dku plugin put-file PLUGIN_ID --path FILE_PATH --content CONTENT
dku plugin download PLUGIN_ID [--dest PATH]                                    # Download dev plugin as ZIP
dku plugin rename-file PLUGIN_ID --path PATH --name NEW_NAME                   # Rename file/folder (dev only)
dku plugin move-file PLUGIN_ID --path PATH --to NEW_PATH                       # Move file/folder (dev only)
dku plugin install-from-store PLUGIN_ID [--wait/--no-wait]
dku plugin install-from-git REPO_URL [--checkout BRANCH] [--subpath PATH] [--wait/--no-wait]
dku plugin update-from-store PLUGIN_ID [--wait/--no-wait]
dku plugin update-from-git PLUGIN_ID REPO_URL [--checkout BRANCH] [--subpath PATH] [--wait/--no-wait]
```

- `push` reads plugin ID from `plugin.json` inside ZIP, auto-detects update vs install
- `push` accepts a directory (containing `plugin.json`) or a `.zip` archive
- `get` shows plugin details including version, code env, and dev status
- `create-code-env` creates and waits for the managed code env (use after first install)
- `set-code-env` assigns a code env to the plugin (use after create-code-env)
- `update-code-env` rebuilds the code env after dependency changes
- `usages` shows where plugin components are used; filter by project with `-P`
- `download` downloads a dev plugin as a ZIP archive. Only works for dev plugins (not store-installed). Default filename is `<plugin_id>.zip`
- `rename-file` renames a file or folder within a dev plugin. `--path` is the current path, `--name` is just the new filename (not full path)
- `move-file` moves a file or folder to a new location within the plugin. Both `--path` and `--to` are relative to plugin root
- First install flow: `push --install && create-code-env PLUGIN && set-code-env PLUGIN ENV`
- `recipes` lists plugin recipe types available for `dku recipe create --type`. Shows the full type string (e.g., `CustomCode_plugin_recipe`). Omit PLUGIN_ID to list from all plugins
- `list-files` lists files in a dev plugin as a flattened path tree (dev plugins only)
- `get-file --path` prints the contents of a file in a dev plugin
- `put-file --path` writes content to a file in a dev plugin. `--content` accepts literal string, `@file.txt`, or `-` for stdin
- `delete --force` force-deletes even if the plugin is used by recipes, agents, etc. Requires `--confirm`/`--yes`/`-y`

## code-env

```bash
dku code-env list [-o FORMAT]
dku code-env get ENV_NAME [--lang PYTHON] [-o FORMAT]
dku code-env create ENV_NAME [--lang PYTHON] [--python-version VER]
dku code-env delete ENV_NAME [--lang PYTHON]
dku code-env update ENV_NAME [--lang PYTHON]
```

## connection

Admin-only. 403 if non-admin.

```bash
dku connection list [--type TYPE] [-o FORMAT]
dku connection get CONNECTION_NAME [-o FORMAT]
dku connection create NAME --type TYPE [--definition JSON]
dku connection delete CONNECTION_NAME --yes --confirm-name CONNECTION_NAME   # tier-3 cascade: orphans every dataset using it
dku connection test CONNECTION_NAME
dku connection schemas CONNECTION_NAME [-P PROJECT] [-o FORMAT]    # SQL schemas / Iceberg namespaces
dku connection tables CONNECTION_NAME [-P PROJECT] [--schema SCHEMA] [-o FORMAT]  # Importable tables
dku connection sync-acls CONNECTION_NAME [--root/--datasets] [--wait/--no-wait]
```

- `list --type` filters by connection type (Snowflake, PostgreSQL, EC2, etc.) using fast `list_connections_names` endpoint
- `test` only works on SQL and cloud connections. Filesystem/LLM/local connections exit 2 with `unsupported_operation` — use `dku connection get` to inspect instead
- `schemas` lists SQL schemas or Iceberg namespaces. Requires project context (`-P`)
- `tables` lists tables available for import. Use `--schema` to narrow results. Auto-detects SQL vs Iceberg
- `sync-acls` syncs HDFS ACLs (only useful with User Isolation + DSS-managed HDFS ACL). `--datasets` syncs dataset ACLs instead of root

- `get` shows connection details including type, params, and usability settings
- `delete` removes the connection. `--yes` skips confirmation

## user

```bash
dku user list [-o FORMAT]
dku user get LOGIN [-o FORMAT]
dku user create LOGIN --password PASS [--display-name NAME] [--email EMAIL] [--groups G1,G2]
dku user delete LOGIN [--yes]
dku user activity LOGIN [-o FORMAT]                        # Last login, session activity timestamps
dku user add-secret LOGIN --name NAME --value VALUE        # Add/replace a user secret
```

- `get` shows user details including display name, email, groups, and admin status
- `delete` removes the user. `--yes` skips confirmation

## code-studio

Manage Code Studio instances — interactive development environments in DSS.

```bash
dku code-studio list [-P PROJECT] [-o FORMAT]
dku code-studio create NAME --template TEMPLATE_ID [-P PROJECT]
dku code-studio get CS_ID [-P PROJECT] [-o FORMAT]
dku code-studio delete CS_ID [-P PROJECT]
dku code-studio status CS_ID [-P PROJECT] [-o FORMAT]
dku code-studio start CS_ID [--wait/--no-wait] [-P PROJECT]
dku code-studio stop CS_ID [--wait/--no-wait] [-P PROJECT]
dku code-studio change-owner CS_ID --owner NEW_OWNER [-P PROJECT]
dku code-studio templates [-o FORMAT]
```

- `templates` is a client-level command (no `--project` needed) — lists available templates
- `start`/`stop` return DSSFuture; `--wait` (default) blocks until state change completes
- States: STOPPED, STARTING, RUNNING, STOPPING
- Use `dku code-studio templates` to find the `TEMPLATE_ID` for `create`

---

## api-deployer

Deploy API services to API Nodes. No `--project` needed — operates at instance level.

```bash
dku api-deployer list-infras [-o FORMAT]
dku api-deployer list-services [-o FORMAT]
dku api-deployer get-service SERVICE_ID [-o FORMAT]
dku api-deployer list-deployments [-o FORMAT]
dku api-deployer create-deployment --id ID --service-id SERVICE_ID --infra-id INFRA_ID --version VERSION [--ignore-warnings]
dku api-deployer get-deployment DEPLOYMENT_ID [-o FORMAT]
dku api-deployer update-deployment DEPLOYMENT_ID [--wait/--no-wait]
dku api-deployer delete-deployment DEPLOYMENT_ID
dku api-deployer deployment-status DEPLOYMENT_ID [-o FORMAT]
```

**Flags are `--service-id` / `--infra-id`** (not `--service` / `--infra`).
Get `SERVICE_ID` from `dku api-deployer list-services` and `INFRA_ID` from
`dku api-deployer list-infras`. `VERSION` is the package ID you published
(see `api-service publish-package`).

If `create-deployment` fails with `WARNING : Dataiku Govern Instance is
unreachable` (or any other `WARNING :` validation message), retry with
`--ignore-warnings` — these are non-fatal warnings that block creation by
default. Common on dev/sandbox instances with no reachable Govern node.

`deployment-status -o json` returns `health` (HEALTHY when serving),
`health_messages`, and `service_urls` (base URLs — append `/<endpoint>/predict`
to query a deployed endpoint).

---

## project-deployer

Deploy project bundles to Automation Nodes. No `--project` needed — operates at instance level.

```bash
dku project-deployer list-infras [-o FORMAT]
dku project-deployer list-projects [-o FORMAT]
dku project-deployer list-deployments [-o FORMAT]
dku project-deployer create-deployment --id ID --project-id KEY --infra-id INFRA_ID --bundle-id BUNDLE_ID [--ignore-warnings]
dku project-deployer get-deployment DEPLOYMENT_ID [-o FORMAT]
dku project-deployer update-deployment DEPLOYMENT_ID [--wait/--no-wait]
dku project-deployer delete-deployment DEPLOYMENT_ID
dku project-deployer deployment-status DEPLOYMENT_ID [-o FORMAT]
```

**Flags are `--project-id` / `--infra-id` / `--bundle-id`** (not `--project-key`
/ `--infra` / `--bundle`). As with `api-deployer`, retry with `--ignore-warnings`
if creation fails on a `WARNING :` (e.g. Govern instance unreachable).

---

## git

Manage DSS project version control (branches, commits, tags, push/pull).

```bash
dku git status [-P PROJECT] [-o FORMAT]
dku git log [--count N] [-P PROJECT] [-o FORMAT]
dku git diff [--from COMMIT] [--to COMMIT] [-P PROJECT] [-o FORMAT]
dku git commit -m MESSAGE [-P PROJECT]
dku git pull [--branch NAME] [-P PROJECT] [-o FORMAT]
dku git push [--branch NAME] [-P PROJECT] [-o FORMAT]
dku git fetch [-P PROJECT] [-o FORMAT]
dku git branches [--remote] [-P PROJECT] [-o FORMAT]
dku git create-branch NAME [--from COMMIT] [-P PROJECT]
dku git delete-branch NAME [--force] [--remote] [-P PROJECT]
dku git switch BRANCH [-P PROJECT] [-o FORMAT]
dku git tags [-P PROJECT] [-o FORMAT]
dku git create-tag NAME [--ref REF] [-m MESSAGE] [-P PROJECT]
dku git remote [--set URL] [--name NAME] [-P PROJECT] [-o FORMAT]
dku git reset-to-upstream [-P PROJECT] --yes
dku git reset-to-head [-P PROJECT] --yes
```

- `commit`: DSS auto-adds untracked files before committing
- `remote`: reads remote URL by default; use `--set URL` to update
- `branches --remote`: lists remote tracking branches
- `reset-to-upstream`: hard-resets the current branch to its remote — drops uncommitted changes and local-only commits. Requires the current branch to track a remote (push it or `switch` to a tracking branch first); fails on local-only branches.
- `reset-to-head`: drops only uncommitted changes; local commits are kept.
- All commands require `--project` since git is per-project in DSS

---

## bundle

```bash
dku bundle list [-P PROJECT] [-o FORMAT]
dku bundle export BUNDLE_ID [-P PROJECT]
dku bundle download BUNDLE_ID [-P PROJECT] [--dest DIR]
dku bundle import FILE [-P PROJECT]
dku bundle activate BUNDLE_ID [-P PROJECT]
```

- `activate` calls `preload_bundle` then `activate_bundle`

## continuous

```bash
dku continuous list [-P PROJECT] [-o FORMAT]
dku continuous start RECIPE_ID [-P PROJECT]
dku continuous stop RECIPE_ID [-P PROJECT]
dku continuous status RECIPE_ID [-P PROJECT] [-o FORMAT]
```

- Manages continuous recipe activities (streaming recipes that run indefinitely)
- `list` shows recipe ID, desired state, and current state
- `status` returns `desiredState` (STARTED/STOPPED) and `mainLoopState.state` (RUNNING/etc.)

## api-service

```bash
dku api-service list [-P PROJECT] [-o FORMAT]
dku api-service create SERVICE_ID [-P PROJECT]
dku api-service get SERVICE_ID [-P PROJECT] [-o FORMAT]
dku api-service create-package SERVICE_ID --package PKG_ID [--release-notes TEXT] [-P PROJECT]
dku api-service list-packages SERVICE_ID [-P PROJECT] [-o FORMAT]
dku api-service add-endpoint SERVICE_ID -e ENDPOINT_ID -m MODEL_ID [-t TYPE] [-P PROJECT]
dku api-service list-endpoints SERVICE_ID [-P PROJECT] [-o FORMAT]
dku api-service publish-package SERVICE_ID --package PKG_ID [--published-service ID] [-P PROJECT]
dku api-service delete-package SERVICE_ID --package PKG_ID [-P PROJECT]
```

- `create-package` **requires `--package PKG_ID`** (the version identifier you choose, e.g. `v1`) — the DSS server rejects the call without it
- `add-endpoint` types: prediction (default), clustering, forecasting, causal
- `publish-package` publishes to API Deployer. `--published-service` overrides the target service ID

**Full deploy chain** (model → live endpoint):
```bash
dku api-service create SVC -P PROJ
dku api-service add-endpoint SVC -e predict -m MODEL_ID -P PROJ
dku api-service create-package SVC --package v1 -P PROJ
dku api-service publish-package SVC --package v1 -P PROJ
dku api-deployer create-deployment --id SVC_prod --service-id SVC --infra-id INFRA --version v1 [--ignore-warnings]
dku api-deployer update-deployment SVC_prod --wait
dku api-deployer deployment-status SVC_prod -o json   # health + service_urls
```

## project-folder

```bash
dku project-folder list [-o FORMAT]
dku project-folder create NAME [--parent FOLDER_ID]
dku project-folder move-project PROJECT_KEY --folder FOLDER_ID
```

- `list` shows recursive tree from root with indented folder names, IDs, and project keys
- `create` creates a subfolder under the given parent (default: ROOT)
- `move-project` moves a project to a different folder. Get folder IDs from `list`

## meaning

```bash
dku meaning list [-o FORMAT]
dku meaning get MEANING_ID [-o json]
dku meaning create MEANING_ID --label LABEL [--type TYPE] [--description DESC]
dku meaning update MEANING_ID --definition JSON
```

- Instance-level (no project context needed), admin-only for create/update
- Types: DECLARATIVE, VALUES_LIST, VALUES_MAPPING, PATTERN
- `get` returns full definition including entries/mappings/pattern
- `update` requires the full definition dict (get → modify → update)

## cluster

```bash
dku cluster list [-o FORMAT]
dku cluster get CLUSTER_ID [-o json]
dku cluster create NAME [--type TYPE] [--arch HADOOP|KUBERNETES]
dku cluster start CLUSTER_ID
dku cluster stop CLUSTER_ID [--terminate/--no-terminate]
dku cluster status CLUSTER_ID [-o FORMAT]
dku cluster delete CLUSTER_ID [--yes]
```

- Admin-only. Manages Hadoop and Kubernetes clusters
- `start`/`stop` only work for managed clusters (not manual)
- `stop --no-terminate` detaches without deleting the underlying infra
- `delete` does NOT stop the cluster first — stop it first if it's running

## api-key

```bash
dku api-key list [-o FORMAT]
dku api-key get KEY_ID [-o json]
dku api-key create --label LABEL [--description DESC] [--admin] [-o FORMAT]
dku api-key delete KEY_ID [--yes]
```

- Admin-only. Secret key shown only at creation time
- `create --admin` grants full admin rights. Without `--admin`, key has no permissions (add groups via `get` → modify → `set_definition`)
- The `key` field in JSON output is the secret — store it securely

## admin

```bash
dku admin logs [-o FORMAT]
dku admin get-log LOG_NAME
dku admin usage [--per-project] [-o FORMAT]
dku admin instance-info [-o FORMAT]
dku admin sanity-check [--wait/--no-wait] [-o FORMAT]
```

- All commands require admin API key
- `logs` lists files with name + size. `get-log` outputs the content
- `usage` shows project/dataset/recipe/user counts. `--per-project` adds breakdown
- `instance-info` shows node type, version, hostname, Java/Python versions
- `sanity-check` runs DSS health checks and reports issues by severity

## workspace

```bash
dku workspace list [-o FORMAT]
dku workspace create KEY --name NAME [--description DESC] [--color #HEX] [-o FORMAT]
dku workspace get KEY [-o json]
dku workspace list-objects KEY [-o FORMAT]
dku workspace delete KEY [--yes]
```

- Instance-level (no project context). Admin rights needed for create/delete
- `list-objects` shows datasets, dashboards, articles, apps in the workspace. Some objects (stories/HTML links) may not have a `reference` field
- Use workspaces to organize content across projects for end-user consumption
