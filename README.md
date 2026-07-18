# Dataiku Headless — Cobuild supervisor kit

Gather Dataiku project context, delegate building to Cobuild, and verify the result.

`dataiku-headless` connects a coding agent (Claude Code, Codex, Cursor, OpenCode, or a
custom MCP client) to a Dataiku DSS instance and gives it a deliberately narrow job:
**supervise Cobuild.** Your agent reads the project to ground itself, hands each unit of
building to **Cobuild** — the AI builder that runs *inside* DSS — and then verifies the
result with its own reads. The agent does not hand-build the flow; DSS builds it, natively
and reviewably, and your agent stays accountable for what lands.

## What it is

The tool surface reflects that division of labor:

- **Context & verification (read-only).** List, inspect, sample, and profile every object
  type — projects, flows, datasets, recipes, connections, scenarios, jobs, Data Quality,
  ML, agents, LLMs. Two composed tools do the heavy lifting: `get_project_overview`
  (one call instead of a `list_*` fan-out) and `get_flow_graph` (nodes, edges, and an
  ASCII build tree). `audit_project` is the independent finish gate.
- **Cobuild delegation — the build path.** Every in-project mutation (recipes, datasets,
  models, dashboards, scenarios, zones, wiki, deletions) is delegated through a Cobuild
  conversation. There are no direct `create_recipe` / `update_dataset` style write tools.
- **Three direct executions.** `build_datasets`, `run_recipe`, `run_scenario` — deterministic
  execution of assets that already exist. Nothing more runs outside Cobuild.
- **Four bootstrap writes.** The only writes Cobuild cannot do because they precede a
  project or conversation, or are file-uploads from the agent's own machine:
  `create_project`, `create_upload_dataset` / `create_upload_dataset_from_rows`,
  `upload_file_to_managed_folder`, `write_project_library_file`.
- **Instance management.** `list_instances`, `switch_instance`, `get_current_instance` for
  driving multiple DSS instances from one agent.

`dataiku_mcp` is a [FastMCP](https://gofastmcp.com) server: every tool is a typed, async
MCP tool, all blocking DSS API calls run off an event loop, and long operations emit
progress notifications. Tools never accept an API key as an argument — authentication is
resolved server-side from environment variables or the request's bearer token.

## How delegation works

A Cobuild turn can run for minutes, so delegation is a small state machine rather than a
blocking call:

1. **`start_cobuild_conversation(project_key)`** opens a thread and registers it durably.
   The returned `conversation_id` is the handle for everything that follows; it is persisted,
   so follow-ups keep working after the MCP server restarts.
2. **`send_cobuild_message(conversation_id, project_key, message, allow_edit_project=…, timeout_seconds=…)`**
   sends one instruction. `allow_edit_project` is a **per-message grant, default `false`** —
   inspection and planning run read-only, and you flip it `true` only on the message that
   carries an explicitly requested build.
3. **Timeout ≠ failure.** If a turn exceeds `timeout_seconds`, the tool returns
   `status: timeout` and *retains the work* in a background thread. Poll it with
   **`get_cobuild_turn_status`** — never re-send, which would double-run the build. Sending
   while a turn is already in flight returns `status: in_progress` instead of overlapping.
4. **Deletions require confirmation.** When Cobuild proposes a destructive change it returns
   `status: needs_confirmation` with the objects to delete. Inspect them, then
   **`answer_cobuild_confirmation(…, choice="APPROVE"|"CANCEL")`**. The `confirmation_id` is
   restorable from the durable store, so a confirmation survives a restart.
5. **`list_cobuild_conversations(project_key)`** rediscovers a project's conversations
   (and any pending confirmation / in-flight turn) after a restart.

Conversation metadata lives under `DKU_MCP_STATE_DIR` (see [Configure](#configure)); the
in-memory handles are only a hot cache.

## Tool surface

One fixed surface — no exposure modes, no search mode. **53 non-cobuild + 5 cobuild tools**
are registered; transport gating (below) trims a few at runtime.

| Role | Tools | Representative |
| --- | ---: | --- |
| Context & verification (read-only) | 41 | `get_project_overview`, `get_flow_graph`, `get_dataset_profile`, `get_recipe_settings`, `get_job_log`, `get_data_quality_status` |
| Independent audit | 1 | `audit_project` |
| Cobuild delegation | 5 | `start_cobuild_conversation`, `send_cobuild_message`, `get_cobuild_turn_status`, `answer_cobuild_confirmation`, `list_cobuild_conversations` |
| Direct execution (existing assets) | 3 | `build_datasets`, `run_recipe`, `run_scenario` |
| Bootstrap writes | 5 | `create_project`, `create_upload_dataset` / `_from_rows`, `upload_file_to_managed_folder`, `write_project_library_file` |
| Instance management | 3 | `list_instances`, `switch_instance`, `get_current_instance` |

The exhaustive list with a one-line purpose for every tool is generated into the skill's
`dataiku-skills/dataiku-headless/references/tool-index.md`.

**Transport gating** (set by `DKU_MCP_TRANSPORT`):

- `stdio` exposes `create_upload_dataset` (uploads from a local file path the server can see)
  and the instance-management tools.
- `streamable-http` exposes `create_upload_dataset_from_rows` (tabular `columns` + `rows`,
  for when no server-local file path exists) and removes `switch_instance` / `list_instances`,
  since a shared HTTP server should not carry per-client instance state.

## The skill

The kit ships **one** agent skill, `dataiku-skills/dataiku-headless/`, loaded on demand when
its `SKILL.md` frontmatter `description` matches the conversation. `SKILL.md` is the router
(permanent rules + a task→playbook table), `soul.md` is the judgment layer for multi-stage
work (decompose → delegate → verify → finish), and `playbooks/` holds one recipe per task
kind (build via Cobuild, inspect, direct execution, verify output, migrate). `references/`
carries the facts an agent opens only when it needs them, including the generated tool-index.

## Install

Each plugin install wires up both `dataiku-skills/` and the MCP server in one step. Cloning
the repo works too — every config file the plugins reference (`.mcp.json`, `.cursor/mcp.json`,
`opencode.json`, `dataiku-skills/`) is a real file at the repo root.

### Claude Code

```
/plugin marketplace add dataiku/dku-headless
/plugin install dataiku@dataiku
```

### Codex

```
/plugins
```
Add the marketplace and install `dataiku` from there.

### Cursor

- **Auto-discovered:** `.cursor/mcp.json` at the repo root wires up the MCP tools with no
  install step.
- **Plugin** (adds the skill too): install the `dataiku` plugin from Cursor's Marketplace UI
  (Customize → Marketplace → search `dataiku`).

### OpenCode

**Auto-discovered:** `opencode.json` at the repo root wires up the MCP tools with no install
step.

## Configure

Set your Dataiku connection. The minimum is a URL and an API key:

```bash
export DKU_DSS_URL="https://your-instance.dataiku.com"
export DKU_API_KEY="your-api-key"
```

Or copy `.env.example` to `.env` and fill it in. Full variable reference:

| Variable | Default | Purpose |
| --- | --- | --- |
| `DKU_DSS_URL` | — | DSS instance URL. Setting it is what marks an instance as configured. |
| `DKU_API_KEY` | — | API key. May instead be supplied per-request over streamable-http as `Authorization: Bearer <key>`. |
| `DKU_INSTANCE_NAME` | `dss-env` | Name for the env-configured instance; it takes precedence over any `default_instance` in `.dataiku/config.json`. |
| `DKU_NO_CHECK_CERTIFICATE` | `false` | `true`/`1` skips SSL verification (matches Dataiku's local config). |
| `DKU_DEFAULT_CONNECTION` | — | Optional default dataset connection, fed to Cobuild prompts / upload tools when omitted. |
| `DKU_DEFAULT_FOLDER_CONNECTION` | — | Optional default managed-folder connection. |
| `DKU_DEFAULT_LLM` | — | Optional default LLM id. |
| `DKU_DEFAULT_EMBEDDING_LLM` | — | Optional default embedding LLM id. |
| `DKU_MCP_MAX_WORKERS` | `4` | Thread-pool size for blocking DSS API calls. |
| `DKU_MCP_TRANSPORT` | `stdio` | `stdio` or `streamable-http`. Gates the transport-specific tools. |
| `DKU_MCP_STATE_DIR` | `~/.local/state/dataiku-headless` | Durable Cobuild conversation registry — conversations and pending confirmations survive restarts. |

Streamable-http also honors the standard FastMCP settings `FASTMCP_HOST`, `FASTMCP_PORT`,
and `FASTMCP_STREAMABLE_HTTP_PATH`.

### Multiple instances

Put instance definitions in `.dataiku/config.json` (see `.dataiku/config.json.example` for
the shape), then drive them from the agent with `list_instances`, `switch_instance`, and
`get_current_instance`. Auth resolves in this order:

1. Environment variables (`DKU_DSS_URL` / `DKU_API_KEY`, named by `DKU_INSTANCE_NAME`) — this
   instance takes precedence and becomes the current one.
2. `.dataiku/config.json`, using its `default_instance`.
3. For streamable-http only, the API key from `Authorization: Bearer <DKU_API_KEY>`.

## Development

```bash
uv sync                # create .venv and install with dependencies (Python 3.10+, uv)
uv run pytest          # smoke + surface + cobuild + context + audit tests; no live DSS needed
uv run ruff check .    # lint (rule set pinned in pyproject.toml)
```

Two maintenance scripts keep the skill honest and run in CI: one regenerates the skill's
tool-index from the registered tool surface, and one validates the skill's internal
reference links. The registered tool set itself is pinned by the allow-list in
`tests/test_smoke.py` — any add/remove/rename must update it on purpose.

Run the server standalone (only needed for direct testing or running streamable-http as a
standing service):

```bash
./bin/run_mcp.sh           # uv run python -m dataiku_mcp
# or, from an installed package:
uvx dataiku-headless serve
```

See `CODING_STANDARDS_AND_STRUCTURE.md` for contribution scope, the tool-surface and
write-routing conventions, and the PR checklist.
