# Dataiku Agent Dev Kit

An MCP server and agent skill library for operating Dataiku with an AI agent harness (Claude Code, Codex, Cursor, or a custom agent). Connect your agent to a Dataiku instance to inspect projects, gather context, and drive Cobuild, Dataiku's AI building agent to build data pipelines, analytics, machine learning models, multi-agent workflows, applications, and automation pipelines inside Dataiku.

Cobuild is exposed here as a retained conversation, driven through MCP tools. This repo's own tool surface stays deliberately thin around it: read/list/get/inspect tools for every object type (for context-gathering inside or outside a Cobuild conversation), plus a handful of operations Cobuild cannot do because they are cross-project, instance-level, or precede a project/conversation existing (creating a project, uploading a local file into a dataset or managed folder or project library).

## MCP Server

`dataiku_mcp` is a FastMCP server that exposes Dataiku DSS operations as typed, async MCP tools. Tools are organized by domain: projects, flow, connections, datasets, Data Quality, managed folders, recipes, machine learning, insights, dashboards, scenarios, WebApps, wikis, agents, LLMs and knowledge banks, job management, and Cobuild conversations.

- Async execution for all Dataiku API calls
- Progress notifications for long-running operations
- Tiered server-side authentication (env API key or HTTP bearer token)
- Modular architecture by functional domain
- Cobuild conversation tools (`start_cobuild_conversation`, `send_cobuild_message`, `answer_cobuild_confirmation`, `list_cobuild_conversations`) as the default path for project-level asset creation
- `DKU_MCP_COBUILD_MODE` controls how much of the read-tool surface stays exposed alongside Cobuild (see Configure below)
- Optional search-based tool exposure mode for progressive disclosure

Tools do not accept API keys as arguments — authentication is resolved server-side from environment variables or request headers.

## Agent Skills

`dataiku-skills` contains prompt-based skill files that teach an agent *how* to use the MCP tools correctly — when a task should route through Cobuild vs. a direct read tool, how to interpret results, and what the current limitations are.

| Skill | Covers |
| --- | --- |
| `cobuild` | Default path for project-level asset creation/modification — start, continue, and confirm Cobuild conversations |
| `projects` | Project discovery, flow navigation, metadata/variable inspection; `create_project` remains a direct write |
| `connections` | DSS connection discovery, type/category filtering, capability inspection, health checks |
| `code-environments` | List available code environments to reference in a Cobuild prompt |
| `datasets` | Dataset inspection, profiling, schema; local-file upload tools remain direct writes |
| `jobs` | DSS job tracking, status, waiting, and log inspection |
| `data-quality` | Dataset Data Quality rule inspection — status, results, history |
| `managed_folders` | Managed folder inspection; local-file upload remains a direct write |
| `recipes` | Recipe and recipe-type inspection to gather context before a Cobuild write |
| `machine-learning` | ML analysis and saved-model inspection |
| `insights` | Insight inspection, especially chart insights dashboards reference |
| `dashboards` | Dashboard inspection and context-gathering |
| `llms-and-knowledge-banks` | LLM, Knowledge Bank, and RAG object inspection |
| `agents` | DSS agent, version, and agent-tool inspection |
| `agent-reviews` | Agent review, test, run, and result inspection |
| `scenarios` | Scenario, run-history, and messaging-channel inspection |
| `semantic-models` | Semantic model and version inspection |
| `webapps` | WebApp and backend-state inspection |
| `wikis` | Wiki article and hierarchy inspection |
| `project-libraries` | Project library file tree inspection/search; local-file write remains a direct write |
| `cross-project-sharing` | Inspect existing cross-project sharing relationships |
| `data-collections` | List and inspect Data Collections and their member objects |
| `migrations` | Translate a third-party Source Bundle into a Dataiku migration plan, then hand the build off to Cobuild |

Skills are loaded on demand by the agent — see `AGENTS.md` for routing rules and operating instructions.

## Getting Started

### 1. Install

```bash
uv pip install --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple dataiku-headless
```

### 2. Initialize your project

Run once in your project directory to copy the agent operating instructions and skill library:

```bash
dataiku-headless initialize
```

This writes `AGENTS.md`, `CLAUDE.md`, and `dataiku-skills/` into the current directory. Your agent harness picks them up automatically — Claude Code reads `CLAUDE.md`, Codex reads `AGENTS.md`.

**If `AGENTS.md` or `CLAUDE.md` already exist** in your project (e.g. with your own custom instructions), `initialize` will not overwrite them. Instead it writes to `AGENTS_DATAIKU_HEADLESS.md` / `CLAUDE_DATAIKU_HEADLESS.md` and prompts you to merge it into your `AGENTS.md` or `CLAUDE.md`.

### Upgrading to new versions

After upgrading the package, re-run `initialize --force` to update your project:

```bash
uv pip install --upgrade --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple dataiku-headless
dataiku-headless initialize --force
```

`--force` fully replaces `dataiku-skills/` without prompting. For `AGENTS.md` / `CLAUDE.md`, the same rule applies regardless of `--force`: if they don't exist they're written fresh; if they already exist, the updated content is written to `AGENTS_DATAIKU_HEADLESS.md` / `CLAUDE_DATAIKU_HEADLESS.md` and you're prompted to merge.

`dataiku-headless serve` will warn you if your `AGENTS.md` or `CLAUDE.md` are behind the installed package version.

### 3. Configure

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
DKU_DEFAULT_CONNECTION=filesystem_managed
DKU_DEFAULT_FOLDER_CONNECTION=filesystem_folders
DKU_DEFAULT_LLM=openai:<YOUR_CONNECTION_NAME>:gpt-5.4
DKU_DEFAULT_EMBEDDING_LLM=openai:<YOUR_CONNECTION_NAME>:text-embedding-3-small
DKU_MCP_MAX_WORKERS=4
DKU_MCP_TRANSPORT=stdio
DKU_MCP_COBUILD_MODE=CREATE_ONLY
DKU_MCP_TOOL_EXPOSURE=search
DKU_MCP_SEARCH_MAX_RESULTS=5
DKU_MCP_SEARCH_ALWAYS_VISIBLE=get_current_instance

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

Use `DKU_DEFAULT_INSTANCE` to select a non-default instance at startup. 

After adding multiple instance configs, you can use the `list_instances`, `switch_instance`, and `get_current_instance` MCP tools to manage instances from the agent.

Auth resolution order:
1. Environment variables: `DKU_DSS_URL`, `DKU_API_KEY`, and optional `DKU_NO_CHECK_CERTIFICATE`
2. Local config: `.dataiku/config.json`, using `DKU_DEFAULT_INSTANCE` when set or `default_instance` otherwise
3. Streamable HTTP request header for API key only: `Authorization: Bearer <DKU_API_KEY>`

**Tool exposure modes:** `search` (default) collapses the visible catalog to `search_tools` and `call_tool`, reducing context overhead for agents with large tool catalogs. `full` exposes all tools directly.

**Cobuild modes:** `CREATE_ONLY` (default) keeps this server's full read-tool surface enabled alongside the Cobuild conversation tools, for context-gathering independent of any Cobuild conversation. `FULL` additionally disables the read tools that duplicate what Cobuild can already inspect within its own conversation, leaving only cross-project/instance tools, the direct-write exceptions, and the Cobuild conversation tools themselves.

### 4. Connect to your agent harness

Add the MCP server to your agent — see [Connecting to an Agent Harness](#connecting-to-an-agent-harness) for Claude Code, Codex, and other harnesses.

### 5. Run

```bash
dataiku-headless serve
# or simply:
dataiku-headless
```

## Connecting to an Agent Harness

### Claude Code

```bash
claude mcp add-json dataiku-mcp '{
  "type": "stdio",
  "command": "dataiku-headless"
}' --scope user
```

### Codex

Add to `~/.codex/config.toml`:

```toml
[mcp_servers.dataiku-mcp]
command = "dataiku-headless"
```

## Project Structure

```text
.
├── dataiku_mcp/
│   ├── tools/
│   │   ├── agents.py          # Agent/agent-version/agent-tool inspection tools
│   │   ├── agent_reviews.py   # Agent review/test/run inspection tools
│   │   ├── cobuild.py         # Cobuild conversation tools (start/send/confirm/list)
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
│   ├── agents/                # Agent/agent-version/agent-tool inspection skill
│   ├── agent-reviews/         # Agent review/test/run inspection skill
│   ├── insights/              # Insight inspection skill
│   ├── code-environments/     # Code environment listing skill
│   ├── connections/           # DSS connection discovery and inspection skill
│   ├── cross-project-sharing/ # Cross-project sharing inspection skill
│   ├── dashboards/            # Dashboard inspection skill
│   ├── data-collections/      # Data Collection listing and inspection skill
│   ├── data-quality/          # Dataset Data Quality rule inspection skill
│   ├── datasets/              # Dataset inspection/profiling skill
│   ├── jobs/                  # DSS job tracking and investigation skill
│   ├── llms-and-knowledge-banks/ # LLM, Knowledge Bank, and RAG object inspection skill
│   ├── machine-learning/      # ML analysis + saved-model inspection skill
│   ├── managed_folders/       # Managed folder inspection skill
│   ├── project-libraries/     # Project library inspection/search skill
│   ├── projects/              # Project discovery + flow navigation skill
│   ├── scenarios/             # Scenario/run-history inspection skill
│   ├── semantic-models/       # Semantic model inspection skill
│   ├── webapps/               # WebApp/backend-state inspection skill
│   ├── wikis/                 # Wiki article inspection skill
│   ├── migrations/            # Source Bundle -> migration plan -> Cobuild handoff skill
│   └── recipes/
│       ├── SKILL.md                # Recipe inspection skill, covers all recipe types
│       └── references/             # prepare processor catalog + formula language (all other types need none)
├── AGENTS.md                  # Agent operating instructions
├── CODING_STANDARDS_AND_STRUCTURE.md  # Contributor guide
└── pyproject.toml
```

## Contributing

See `CODING_STANDARDS_AND_STRUCTURE.md` for local setup, coding standards, guardrails, and the PR checklist.
