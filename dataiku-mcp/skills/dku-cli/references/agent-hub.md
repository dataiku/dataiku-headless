# Reference: Agent Hub

Agent Hub is a **Dataiku plugin webapp** (`agent-hub`, current 1.5.x). You **build** agents with `playbooks/genai-agents.md`; you **surface** a
curated set of them to business users through Agent Hub — one branded chat UI with
LLM-orchestrated routing across enrolled agents, plus no-code end-user "Quick Agents."

**Build vs surface — pick the right tool.** "Let business users chat with our agents
in one branded place" → Agent Hub. "Create / wire / evaluate an agent" → `genai-agents`.
Don't reach for Agent Hub to build an agent; reach for it to *deliver* finished ones.

## The config surface: one endpoint, browser-session auth (not API-key)

A hub's full configuration — orchestrating LLM, enrolled agents, tools, branding — is read
and written through a single webapp-backend endpoint:

```
GET | PUT   /web-apps-backends/<proj>/<hub>/api/admin/config
```

The body is the `admin_settings` JSON (schema below). This is a **complete** config API:
from a logged-in DSS **browser session** you can script an entire hub setup against it (GET
the blob → mutate → PUT it back). No additional plugin API is needed for what it exposes.

**The catch for headless tools:** the backend resolves the *caller* identity exclusively
from DSS browser-session headers. A DSS **personal API key** (what `dku` / `dataikuapi` /
external agents authenticate with) carries no such headers, so the route returns **401** —
even though the *same* key returns 200 on `/public/api/...`. Only a browser session can
write hub config; the endpoint is not drivable by API key.

- **Create the hub webapp with `dku webapp create NAME --from-plugin <plugin-id>
  --component <webapp-component>`** (the CLI's create-then-retype path for plugin
  webapps), or in the DSS UI: *Project > Web Apps > New Web App > Agent Hub*.
- **`dku`'s surface is read/export, not config writes** — config authoring stays a
  browser-session (UI) task.

## What `dku` / the public SDK CAN do

`dku agent-hub` is intentionally minimal — exact flags via `--help`:

| Verb | Does | Reaches |
|---|---|---|
| `list` | Find hub webapps in a project (type contains `agent-hub`) | public API |
| `config` / `set-config` | Read/write ONLY the webapp `config` field | public API |
| `start` / `stop` | `start_or_restart_backend()` / `stop_backend()` | public API |

The webapp `config` field holds **only runtime knobs** — `storage_type`
(`LOCAL`\|`REMOTE`), `db_connection` (if REMOTE), `tables_prefix`, `log_level`.

> **Silent no-op gotcha:** writing hub-behavior keys (`agentHubLLM`, `enterpriseAgents`,
> `agents_ids`, …) via `set-config` is *accepted but ignored* — the plugin never reads
> them from the `config` field. This is exactly why the old `set-llm` / `add-agent` /
> `set-agent` verbs were removed. Use `set-config` only for `log_level` / `storage_type`.

## The supported programmatic READ path (the escape hatch)

The plugin ships two components that read its own DB through DSS-native,
**API-key-friendly** mechanisms — the only window into hub state available to `dku`:

- **"Export Agent Hub Data" recipe** (PYTHON, NARY output) — exports selected hub
  tables → one DSS dataset per table (mapped **by position**; add exactly as many output
  datasets as tables). Param `decompress_blobs` (default true) inflates zlib-compressed
  artifacts/traces. Tables include `agents`, `conversations`, `messages`,
  `admin_settings`, `message_agents`, feedback.
- **"Agent Hub Table" connector** (read-only) — exposes a single hub table as a dataset.

So to observe a hub programmatically — usage, feedback ratings, which agents are
enrolled, conversation volume — build one of these **in the project (UI or plugin-recipe
API)**, then read the resulting dataset with `dku dataset head/schema`. Read-only by
design; there is no write counterpart. To inspect the live config blob, export the
`admin_settings` table (one `__GLOBAL__` row, `settings` = the JSON below).

## Config data model (the `/api/admin/config` ↔ `admin_settings` blob)

Field names shift across plugin releases — **confirm by GET-ing `/api/admin/config` from a
browser session, or by exporting the `admin_settings` table with an API key (below); never
hardcode.** Current (1.5.x) `admin_settings.settings` shape:

```json
{
  "agentHubLLM": "openai:CONN:gpt-4o",        // the orchestrating LLM
  "orchestrationMode": "tools",                // "tools" (LLM routes) | "manual" (user picks)
  "agentHubOptionalInstructions": "…",         // global system prompt
  "enterpriseAgents": [                         // agents enrolled from other projects
    {"id": "PROJECT:agent:AGENT_ID", "projectKey": "PROJECT", "type": "agent",
     "name": "…", "description": "…", "exampleQuestions": ["…"],
     "additionalInstructions": "…", "allowInsightsCreation": true,
     "storiesWorkspace": "WS_KEY", "pluginAgentType": null}],
  "myAgentsEnabled": true,                      // end-user "Quick Agents" (no-code RAG)
  "myAgentsTextCompletionModels": [{"id": "…", "name": "…"}],
  "myAgentsEmbeddingModel": "…", "myAgentsFsConnection": "…",
  "myAgentsFolder": "…", "myAgentsManagedTools": ["…"],
  "enableDocumentUpload": true, "conversationVisionLLM": "…",
  "chartsGenerationMode": "auto",
  "themeColor": "#2AB1AC", "themeColorMode": "light", "homepageTitle": "…",
  "leftPanelLogoPath": "…", "homepageImagePath": "…", "customCssPath": "…"
}
```

- **Enterprise agent token = `PROJECT_KEY:type:AGENT_ID`** (e.g.
  `AGENTCONNECT:agent:rMtLeB1n`; an augmented LLM is `PORTAL:retrieval-augmented-llm:…`).
  `type ∈ agent | augmented_llm`. These are the *finished DSS agents* you built in
  `genai-agents`, exposed to the Mesh and then enrolled here.
- **Quick Agents ("My Agents")** are distinct objects: end users build them inside the
  hub from documents + sample questions; persisted in the `agents` table with a backing
  project + managed-folder docs, shareable to users/groups. `myAgents*` keys gate which
  models/tools/sharing are allowed.
- **Orchestration:** in `tools` mode the `agentHubLLM` treats each enrolled agent as a
  callable tool and routes the query; in `manual` mode the user selects the agent.

> **Legacy-shape gotcha:** older local exports use a snake_case shape (`LLMs[]`,
> `agents_ids[]`, `tool_agent_configurations[]`, `augmented_llms_ids[]`). Current hubs
> store the camelCase `admin_settings` above — don't model new work on the old shape.

## Storage model

| Mode | Where | Notes |
|---|---|---|
| `LOCAL` (default) | SQLite `data_store.db` in the webapp's workload folder | single-node |
| `REMOTE` | a DSS SQL connection (PostgreSQL / Snowflake / MySQL / MSSQL) | scalable, shared; set `tables_prefix` when colocating with other apps or Alembic migrations can collide |

The backend auto-runs Alembic migrations on start (auto-backup first); `dku agent-hub
start` triggers `start_or_restart_backend()`, which re-runs them.

## Relationship to DSS agents and Agent Hub

- **DSS agents** (`TOOLS_USING_AGENT` / `STRUCTURED_AGENT`) are built and evaluated with
  `playbooks/genai-agents.md`, exposed to the Mesh as `agent:ID`, then **enrolled** into a
  hub by an admin in the UI. Agent Hub is the delivery layer, not the build layer.
- **Programmatic agent building** (project objects, public API) does **not** touch Agent
  Hub — it produces DSS agents. Agent Hub is the separate, UI-managed surface that
  *surfaces* those agents. There is no programmatic bridge between the two.

## Gotchas

- `dku agent-hub list` empty → no hub exists; create it in the UI first, then manage
  lifecycle/runtime via CLI.
- `set-config` persists `{log_level, storage_type, db_connection, tables_prefix}` only;
  anything else is a silent no-op. (Distinct from `/api/admin/config`, which is the real
  hub config — but that one needs a browser session, not the `dku` API key; see top.)
- Don't read the webapp `config` field expecting hub settings — the real config is the
  `admin_settings` row / `/api/admin/config` blob. Read it via `/api/admin/config` from a
  browser session, or export the `admin_settings` table with an API key.
- A personal API key gets **401** on `/api/admin/config` (identity comes from browser-ticket
  headers); it gets 200 on `/public/api/...`. Don't mistake the 401 for "wrong URL."
