# Dataiku Agent Dev Kit

An MCP server and agent skill library for operating Dataiku DSS with an AI agent harness (Claude Code, Codex, or a custom agent). Connect your agent to a DSS instance and build project pipelines, prepare data, train models, and more — all driven by natural language.

## MCP Server

`dataiku_mcp` is a FastMCP server that exposes Dataiku DSS operations as typed, async MCP tools. Tools are organized by domain: projects, flow, connections, datasets, Data Quality, managed folders, recipes, machine learning, insights, dashboards, scenarios, WebApps, wikis, agents, LLMs and knowledge banks, and job management.

- Async execution for all Dataiku API calls
- Progress notifications for long-running operations
- Tiered server-side authentication (env API key or HTTP bearer token)
- Modular architecture by functional domain
- Optional search-based tool exposure mode for progressive disclosure

Tools do not accept API keys as arguments — authentication is resolved server-side from environment variables or request headers.

## Agent Skills

`dataiku-skills` contains prompt-based skill files that teach an agent *how* to use the MCP tools correctly — when to read before writing, how to route tasks by type, how to interpret results, and what the current limitations are.


| Skill | Covers |
| --- | --- |
| `projects` | Project discovery, flow navigation, metadata and variables editing |
| `connections` | DSS connection discovery, type/category filtering, capability inspection, health checks |
| `code-environments` | List available code environments; set the code env for Python, R, and PySpark recipes or ML analyses |
| `datasets` | Dataset inspection, profiling, schema |
| `jobs` | DSS job tracking, status, waiting, and log inspection |
| `data-quality` | Dataset Data Quality rule CRUD, status, results, history, and computation |
| `managed_folders` | Managed folder inspection and maintenance |
| `recipes` | All visual and code recipe operations; recipe-type subskills |
| `machine-learning` | ML analysis creation, tuning, training, deployment |
| `insights` | Insight CRUD, especially chart insights and chart payload editing |
| `dashboards` | Dashboard CRUD, page filters, and dashboard tile layouts |
| `llms-and-knowledge-banks` | LLM, Knowledge Bank, and RAG object operations |
| `agents` | DSS agent creation, configuration, and management (ReAct and BLOCKS_GRAPH) |
| `agent-reviews` | Agent review CRUD, trait and test management, run execution, and per-test/per-trait result inspection |
| `scenarios` | Scenario CRUD, step/trigger/reporter editing, execution, run history, and messaging channel discovery |
| `semantic-models` | Semantic model and version CRUD — entities, attributes, relationships, glossary terms, golden queries, distinct-values index |
| `webapps` | WebApp creation, inspection, full-settings updates, backend restart/stop |
| `wikis` | Wiki article CRUD — create, read, update, delete, and hierarchy management |
| `project-libraries` | Project library file tree (read/write/move/delete) and external git-imported libraries |
| `cross-project-sharing` | Share and unshare DSS objects (datasets, managed folders, saved models) between projects |
| `data-collections` | List and inspect Data Collections and their member objects |

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
│   │   ├── agents.py          # Agent creation and management tools
│   │   ├── insights.py        # Insight tools, especially chart insights
│   │   ├── connections.py     # DSS connection discovery/test tools
│   │   ├── data_quality.py    # Dataset Data Quality rule tools
│   │   ├── dashboards.py      # Dashboard tools
│   │   ├── datasets.py        # Dataset tools
│   │   ├── evaluation_stores.py  # Evaluation Store tools
│   │   ├── flow.py            # Flow tools
│   │   ├── instances.py       # Multi-instance switching tools
│   │   ├── jobs.py            # Build/recipe run + async job status tools
│   │   ├── llms_and_knowledge_banks.py  # LLM, Knowledge Bank, and RAG tools
│   │   ├── managed_folders.py # Managed folder tools
│   │   ├── projects.py        # Project tools
│   │   ├── scenarios.py       # Scenario tools
│   │   ├── semantic_models.py # Semantic model tools
│   │   ├── webapps.py         # WebApp tools
│   │   ├── wikis.py           # Wiki article CRUD tools
│   │   ├── project_libraries.py  # Project library file tree + external git-imported libraries
│   │   ├── recipes.py         # Recipe tools
│   │   ├── machine_learning/  # ML tools
│   │   └── utils/             # Shared runtime utilities
│   ├── config.py
│   ├── __init__.py
│   └── __main__.py
├── dataiku-skills/
│   ├── agents/               # Agent creation and management skill
│   ├── insights/             # Insight skill, especially chart insights
│   ├── code-environments/    # Code environment listing and assignment skill
│   ├── connections/          # DSS connection discovery and inspection skill
│   ├── cross-project-sharing/ # Object sharing between projects skill
│   ├── dashboards/           # Dashboard skill
│   ├── data-collections/     # Data Collection listing and inspection skill
│   ├── data-quality/         # Dataset Data Quality rule skill and payload examples
│   ├── datasets/             # Dataset inspection/profiling skill
│   ├── jobs/                 # DSS job tracking and investigation skill
│   ├── llms-and-knowledge-banks/ # LLM, Knowledge Bank, and RAG object inspection/build skill
│   ├── machine-learning/     # ML analysis + training skill
│   ├── managed_folders/      # Managed folder inspection/maintenance skill
│   ├── project-libraries/    # Project library file tree + external git library skill
│   ├── projects/             # Project discovery + flow navigation skill
│   ├── scenarios/            # Scenario operations skill + step/trigger/reporter reference
│   ├── semantic-models/      # Semantic model CRUD skill
│   ├── webapps/              # WebApp creation/inspection/update/runtime skill
│   ├── wikis/                # Wiki article CRUD skill
│   └── recipes/
│       ├── SKILL.md                # Parent recipe operations skill
│       └── recipe-types/           # One child skill per recipe type
├── AGENTS.md                  # Agent operating instructions
├── CODING_STANDARDS_AND_STRUCTURE.md  # Contributor guide
└── pyproject.toml
```

## Contributing

See `CODING_STANDARDS_AND_STRUCTURE.md` for local setup, coding standards, guardrails, and the PR checklist.
