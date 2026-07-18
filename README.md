# Dataiku Agent Dev Kit

An MCP server and agent skill library for operating Dataiku with an AI agent harness (Claude Code, Codex, Snowflake CoCo (Cortex Code), Cursor, OpenCode, or a custom agent). Connect your agent to a Dataiku instance to inspect projects, gather context, and drive Cobuild, Dataiku's AI building agent to build data pipelines, analytics, machine learning models, multi-agent workflows, applications, and automation pipelines inside Dataiku.

Cobuild is exposed here as a retained conversation, driven through MCP tools. This repo's own tool surface stays deliberately thin around it: read/list/get/inspect tools for grounding, three deterministic executions of existing assets (`build_datasets`, `run_recipe`, and `run_scenario`), plus a handful of bootstrap operations that are cross-project, instance-level, or must precede a project/conversation.

## MCP Server

`dataiku_mcp` is a FastMCP server that exposes Dataiku DSS operations as typed, async MCP tools. Tools are organized by domain: projects, flow, connections, datasets, Data Quality, managed folders, recipes, machine learning, insights, dashboards, scenarios, WebApps, wikis, agents, LLMs and knowledge banks, job management, and Cobuild conversations.

- Async execution for all Dataiku API calls
- Progress notifications for long-running operations
- Tiered server-side authentication (env API key or HTTP bearer token)
- Modular architecture by functional domain
- Dense, bounded orientation calls for a project overview and its Flow graph
- Cobuild conversation tools (`start_cobuild_conversation`, `send_cobuild_message`, `get_cobuild_turn_status`, `answer_cobuild_confirmation`, `list_cobuild_conversations`) as the default path for project-level asset creation
- `DKU_MCP_COBUILD_MODE` controls how much of the read-tool surface stays exposed alongside Cobuild (see Configure below)
- Optional search-based tool exposure mode for progressive disclosure

Tools do not accept API keys as arguments — authentication is resolved server-side from environment variables or request headers.
Project-variable reads redact credential-shaped fields, exclude local overrides by
default, and bound nested values before returning them to the model.

## Agent Skills

`dataiku-skills` contains prompt-based skill files that teach an agent *how* to use the MCP tools correctly — when a task should route through Cobuild vs. a direct read tool, how to interpret results, and what the current limitations are.

| Skill | Covers |
| --- | --- |
| `cobuild` | Default path for project-level asset creation/modification — start, continue, and confirm Cobuild conversations |
| `projects` | Project discovery, metadata/variables, Flow organization; `create_project` remains a direct write |
| `connections` | Connection discovery, type/category filtering, capability inspection, health checks; connection-type reference |
| `code-environments` | List available code environments to reference in a Cobuild prompt |
| `datasets` | Dataset storage/schema/metadata/quality-signal inspection; creating an Uploaded Files dataset remains a direct write |
| `jobs` | DSS job tracking, status, waiting, and log inspection |
| `data-quality` | Data Quality rule and result inspection; rule-type reference |
| `managed_folders` | Managed folder inspection; local-file upload remains a direct write |
| `recipes` | Recipe type selection and existing-recipe inspection; recipe-family references (data-prep, ML, GenAI, code) and prepare processor/formula-language reference |
| `machine-learning` | ML analysis, trained-model, and saved-model inspection; task-type references (prediction, clustering, causal, forecasting) |
| `insights` | Insight and referenced-object inspection, especially chart insights dashboards reference |
| `dashboards` | Dashboard listing and settings inspection |
| `llms-and-knowledge-banks` | LLM, Knowledge Bank, and Retrieval-Augmented LLM inspection |
| `agents` | Agent and agent-tool inspection — types, versions, configuration, execution design; agent-type and agent-tool references |
| `agent-reviews` | Agent review, test, run, and result inspection |
| `scenarios` | Scenario, run-history, and messaging-channel inspection |
| `semantic-models` | Semantic model and version inspection |
| `webapps` | WebApp and backend-state inspection |
| `wikis` | Wiki article and hierarchy inspection; wiki-content reference |
| `project-libraries` | Project library file tree inspection/search; local-file write remains a direct write |
| `cross-project-sharing` | Inspect existing cross-project sharing relationships |
| `data-collections` | Discover a dataset by topic across projects via curated Data Collections |
| `migrations` | Translate a third-party Source Bundle into a Dataiku migration plan, then hand the build off to Cobuild |

Skills are loaded on demand — each `SKILL.md`'s frontmatter `description` is what the agent harness matches against the conversation to decide when to pull it in. There is no separate root routing file; the descriptions themselves are the routing table.

## Install

Grouped by harness. Each plugin install wires up both `dataiku-skills/` and the MCP server (`uvx dataiku-headless serve`) in one step. Cloning this repo directly works too — every config file the plugins use (`.mcp.json`, `.cursor/mcp.json`, `opencode.json`, `dataiku-skills/`) is a real, readable file at the repo root.

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

### Snowflake CoCo (Cortex Code)

```
cortex plugin install dataiku/dku-headless
```

### Cursor

**Auto-discovered:** `.cursor/mcp.json` at the repo root wires up the MCP tools with no install step.

**Plugin** (adds skills too): install the [`dataiku` plugin](https://cursor.com/marketplace) from Cursor's Marketplace UI (Customize → Marketplace → search `dataiku`).

### OpenCode

**Auto-discovered:** `opencode.json` at the repo root wires up the MCP tools with no install step.

## Configure

Set your Dataiku connection information and other configuration details:

**Temporary:**
```bash
export DKU_DSS_URL="https://your-instance.dataiku.com"
export DKU_API_KEY="your-api-key"
```

**.env file:**
Copy `.env.example` to `.env` and fill in your values:
```bash
DKU_DSS_URL=https://your-instance.dataiku.com
DKU_API_KEY=your-api-key
DKU_MCP_MAX_WORKERS=4
DKU_MCP_TRANSPORT=stdio
DKU_MCP_COBUILD_MODE=CREATE_ONLY
DKU_MCP_TOOL_EXPOSURE=search
DKU_MCP_SEARCH_MAX_RESULTS=5
DKU_MCP_SEARCH_ALWAYS_VISIBLE=get_current_instance
DKU_COBUILD_TIMEOUT_SECONDS=1200
DKU_COBUILD_MAX_TIMEOUT_SECONDS=1800
DKU_MCP_MAX_COBUILD_TURNS=8

# Set to true/1 to skip SSL verification, matching Dataiku's local config.
DKU_NO_CHECK_CERTIFICATE=false

# Optional streamable-http settings
FASTMCP_HOST=127.0.0.1
FASTMCP_PORT=8000
FASTMCP_STREAMABLE_HTTP_PATH=/mcp
```

**Upload tool behavior depends on transport:**

- `stdio` exposes `create_upload_dataset`, which uploads from a local file path visible to the MCP server process.
- `streamable-http` exposes `create_upload_dataset_from_rows`, which uploads tabular data passed as `columns` plus positional `rows` when a server-local file path is not usable.

**Connect to multiple instances:**
Put instance info in `.dataiku/config.json`. See `.dataiku/config.json.example` for the expected shape. 

After adding multiple instance configs, you can use the `list_instances`, `switch_instance`, and `get_current_instance` MCP tools to manage instances from the agent.

Auth resolution order:
1. Environment variables: `DKU_DSS_URL`, `DKU_API_KEY`, and optional `DKU_NO_CHECK_CERTIFICATE`
2. The first existing config file: `$DKU_CONFIG_DIR/config.json`, `./.dataiku/config.json`, then `$XDG_CONFIG_HOME/dataiku-headless/config.json` (or `~/.config/dataiku-headless/config.json`)
3. Streamable HTTP request header for API key only: `Authorization: Bearer <DKU_API_KEY>`

The old `DKU_DEFAULT_CONNECTION`, `DKU_DEFAULT_FOLDER_CONNECTION`,
`DKU_DEFAULT_LLM`, and `DKU_DEFAULT_EMBEDDING_LLM` settings were never consumed
by a tool. They are no longer part of the configuration contract; pass concrete
object identifiers in the relevant tool or Cobuild instruction instead.

**Long Cobuild turns:** `DKU_COBUILD_TIMEOUT_SECONDS` sets how long a tool call
waits before returning a pollable `turn_id`; it does not cancel work already
running in DSS. `DKU_COBUILD_MAX_TIMEOUT_SECONDS` caps a caller-supplied timeout,
and `DKU_MCP_MAX_COBUILD_TURNS` bounds live turns across server processes that
share the same state directory. Keep that capacity setting the same in those
processes. Durable conversation and turn state defaults to the XDG user state
directory and can be relocated with `DKU_MCP_STATE_DIR`.

**Tool exposure modes:** `search` (default) collapses the visible catalog to `search_tools` and `call_tool`, reducing context overhead for agents with large tool catalogs. `full` exposes all tools directly.

**Cobuild modes:** `CREATE_ONLY` (default) keeps this server's full read-tool surface enabled alongside the Cobuild conversation tools, for context-gathering independent of any Cobuild conversation. `FULL` additionally disables the read tools that duplicate what Cobuild can already inspect within its own conversation, leaving only cross-project/instance tools, the direct-write exceptions, and the Cobuild conversation tools themselves.

## Run

Every install path above has your harness launch the server itself via `uvx`. Run it standalone only if you're testing it directly or running `streamable-http` as a standing service:

```bash
uv pip install --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple dataiku-headless
dataiku-headless serve
# or simply:
dataiku-headless
```

## Project Structure

```text
.
├── dataiku_mcp/
│   ├── tools/
│   │   ├── agents.py          # Agent/agent-version/agent-tool inspection tools
│   │   ├── agent_reviews.py   # Agent review/test/run inspection tools
│   │   ├── cobuild.py         # Cobuild conversation tools (start/send/poll/confirm/list)
│   │   ├── insights.py        # Insight inspection tools, especially chart insights
│   │   ├── connections.py     # DSS connection discovery/test tools
│   │   ├── cross_project_sharing.py  # Cross-project sharing inspection tools
│   │   ├── data_collections.py  # Data Collection listing/inspection tools
│   │   ├── data_quality.py    # Dataset Data Quality rule inspection tools
│   │   ├── dashboards.py      # Dashboard inspection tools
│   │   ├── datasets.py        # Dataset inspection tools + local-file upload writes
│   │   ├── evaluation_stores.py  # Evaluation Store inspection tools
│   │   ├── flow.py            # Flow inspection tools
│   │   ├── instances.py       # Multi-instance switching tools
│   │   ├── jobs.py            # Async job status/log/wait tools
│   │   ├── llms_and_knowledge_banks.py  # LLM, Knowledge Bank, and RAG inspection tools
│   │   ├── managed_folders.py # Managed folder inspection tools + local-file upload write
│   │   ├── projects.py        # Project inspection tools + create_project write
│   │   ├── scenarios.py       # Scenario/run-history/messaging-channel inspection tools
│   │   ├── semantic_models.py # Semantic model inspection tools
│   │   ├── webapps.py         # WebApp/backend-state inspection tools
│   │   ├── wikis.py           # Wiki article inspection tools
│   │   ├── project_libraries.py  # Project library inspection/search + local-file write
│   │   ├── recipes.py         # Recipe inspection tools
│   │   ├── machine_learning/  # ML analysis/saved-model inspection tools
│   │   └── utils/             # Shared runtime utilities
│   ├── config.py
│   ├── config_mcp.py          # Tool exposure + Cobuild mode configuration
│   ├── __init__.py
│   └── __main__.py
├── dataiku-skills/
│   ├── cobuild/               # Default path for project-level asset creation via Cobuild
│   ├── agents/
│   │   ├── SKILL.md                # Agent/agent-version/agent-tool inspection skill
│   │   └── references/             # Agent-type references (simple, structured, code) + agent tools
│   ├── agent-reviews/         # Agent review/test/run inspection skill
│   ├── insights/              # Insight inspection skill
│   ├── code-environments/     # Code environment listing skill
│   ├── connections/
│   │   ├── SKILL.md                # DSS connection discovery and inspection skill
│   │   └── references/             # Connection type/category reference
│   ├── cross-project-sharing/ # Cross-project sharing inspection skill
│   ├── dashboards/            # Dashboard inspection skill
│   ├── data-collections/      # Data Collection listing and inspection skill
│   ├── data-quality/
│   │   ├── SKILL.md                # Dataset Data Quality rule inspection skill
│   │   └── references/             # Rule-type reference
│   ├── datasets/
│   │   ├── SKILL.md                # Dataset inspection/profiling skill
│   │   └── references/             # Uploaded Files dataset reference
│   ├── jobs/                  # DSS job tracking and investigation skill
│   ├── llms-and-knowledge-banks/ # LLM, Knowledge Bank, and RAG object inspection skill
│   ├── machine-learning/
│   │   ├── SKILL.md                # ML analysis + saved-model inspection skill
│   │   └── references/             # Task-type references (prediction, clustering, causal, forecasting)
│   ├── managed_folders/       # Managed folder inspection skill
│   ├── project-libraries/     # Project library inspection/search skill
│   ├── projects/              # Project discovery + flow navigation skill
│   ├── scenarios/             # Scenario/run-history inspection skill
│   ├── semantic-models/       # Semantic model inspection skill
│   ├── webapps/               # WebApp/backend-state inspection skill
│   ├── wikis/
│   │   ├── SKILL.md                # Wiki article inspection skill
│   │   └── references/             # Wiki content reference
│   ├── migrations/            # Source Bundle -> migration plan -> Cobuild handoff skill
│   └── recipes/
│       ├── SKILL.md                # Recipe inspection skill, covers all recipe types
│       └── references/
│           ├── recipe-types/       # Recipe-family references (data-prep, ML, GenAI, code)
│           └── shared/              # Prepare processor catalog + formula language
├── .claude-plugin/
│   ├── plugin.json             # Claude Code plugin manifest (points at dataiku-skills/ and .mcp.json)
│   └── marketplace.json        # Marketplace catalog (single-plugin, source: "./")
├── .codex-plugin/
│   └── plugin.json             # Codex plugin manifest (points at dataiku-skills/ and .mcp.json)
├── .mcp.json                   # Shared MCP server config (uvx dataiku-headless serve), read by both manifests
├── opencode.json               # OpenCode project-level MCP config (auto-discovered)
├── .cursor/
│   └── mcp.json                # Cursor project-level MCP config (auto-discovered)
├── .cursor-plugin/
│   ├── plugin.json             # Cursor plugin manifest (bundles dataiku-skills/ as skills + .mcp.json)
│   └── marketplace.json        # Marketplace catalog (single-plugin, source: ".")
├── CODING_STANDARDS_AND_STRUCTURE.md  # Contributor guide
└── pyproject.toml
```

## Contributing

See `CODING_STANDARDS_AND_STRUCTURE.md` for local setup, coding standards, guardrails, and the PR checklist.
