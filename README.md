<div align="center">

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/assets/dataiku-lockup-white.svg">
  <img alt="Dataiku" src="docs/assets/dataiku-lockup-black.svg" width="280">
</picture>

<h1><code>$&nbsp;dataiku-headless</code></h1>

<p><strong>Dataiku Headless: Agentic Analytics, Data Science, and AI Development powered by Dataiku Cobuild</strong></p>

<p><code>SUPERVISE&nbsp;·&nbsp;DELEGATE&nbsp;·&nbsp;VERIFY</code></p>

<p>
  <a href="LICENSE"><img alt="License: Apache 2.0" src="https://img.shields.io/badge/License-Apache_2.0-blue.svg"></a>
  <img alt="Python 3.10+" src="https://img.shields.io/badge/python-3.10%2B-blue.svg">
  <a href="https://gofastmcp.com"><img alt="Built with FastMCP" src="https://img.shields.io/badge/MCP-FastMCP-8A2BE2"></a>
</p>

</div>

---

An MCP server and agent skill library for operating Dataiku with an AI agent harness (Claude Code, Codex, Snowflake CoCo (Cortex Code), Cursor, OpenCode, or a custom agent). Connect your agent to a Dataiku instance to inspect projects, gather context, and drive Cobuild. Cobuild is Dataiku's agent that can build data pipelines, analytics, machine learning models, multi-agent workflows, applications, and automation pipelines inside Dataiku.

Cobuild is exposed here as a retained conversation, driven through MCP tools. This repo's own tool surface stays deliberately thin around it: read/list/get/inspect tools for every object type (for context-gathering inside or outside a Cobuild conversation), plus a handful of operations Cobuild cannot do because they are cross-project, instance-level, or precede a project/conversation existing (creating a project, uploading a local file into a dataset or managed folder or project library).

## MCP Server

`dataiku_mcp` is a FastMCP server that exposes Dataiku DSS operations as typed, async MCP tools. Tools are organized by domain: projects, project folders, flow, connections, datasets, data quality, managed folders, recipes, machine learning, insights, dashboards, scenarios, WebApps, wikis, agents, LLMs and knowledge banks, job management, and Cobuild conversations.

- Async execution for all Dataiku API calls
- Progress notifications for long-running operations
- Server-side authentication (env API key or `.dataiku/config.json`)
- Modular architecture by functional domain
- Cobuild conversation tools (`start_cobuild_conversation`, `send_cobuild_message`, `answer_cobuild_confirmation`, `list_cobuild_conversations`) as the default path for project-level asset creation

Tools do not accept API keys as arguments — authentication is resolved server-side from environment variables or a config file.

## Agent Skills

`skills` exposes a single prompt-based skill entrypoint, `dataiku-headless`, plus a routed reference library under `skills/dataiku-headless/references/`. The entry skill decides which reference guide to read next, carries the shared operating rules, routes in-project asset changes through Cobuild by default, and documents the narrow direct-write exceptions for bootstrap, cross-project, instance-level, or administrative operations that Cobuild does not handle.

The reference library covers the main Dataiku object areas and workflows, including projects, project folders, datasets, recipes, jobs, connections, code environments, managed folders, project libraries, data quality, machine learning, agents, agent reviews, scenarios, semantic models, webapps, wikis, dashboards, insights, data collections, cross-project sharing, and migrations.

## Install

Each plugin bundles the skills and starts the same local `stdio` MCP server. The server intentionally starts without credentials; onboarding happens after installation through the `configure_dataiku` tool.

### Claude Code CLI 

```bash
claude plugin marketplace add https://github.com/dataiku/dku-headless.git
claude plugin install dataiku-headless@dataiku
```

### Codex CLI

```bash
codex plugin marketplace add https://github.com/dataiku/dku-headless.git
codex plugin add dataiku-headless@dataiku
```
### Grok CLI 

```bash
grok plugin install dataiku/dku-headless --trust
```

### Cursor Agent CLI 

```bash
cursor agent plugin marketplace add github.com/dataiku/dku-headless
# Tip: use /plugins in interactive mode to install `dataiku-headless` plugin from this marketplace.
```

### Snowflake CoCo

```bash
cortex plugin install dataiku/dku-headless
```

### Other AI Assistants 

#### MCP 
Add the following to your `.mcp.json` to enable the Dataiku MCP server for any agent harness that reads it:
```json
{
  "mcp": {
    "dataiku": {
      "type": "local",
      "command": ["uvx", "dataiku-headless", "serve"],
      "enabled": true
    }
  }
}
```

#### Skills 

The skills/*/SKILL.md files follow the universal skill format and work with any tool that reads it.  

Install the skill for your agent harness:
```bash
npx skills add dataiku/dku-headless
```


## Onboarding and authentication

The onboarding flow is the same:

1. Ask the agent to setup your DSS instance (**run `configure_dataiku`**).
2. Approve the MCP URL prompt.
3. Enter an instance name, DSS URL, and personal API key.
4. Repeat to add more instances; use `list_instances` and `switch_instance` while working.

The API key never appears in MCP tool arguments.

### Where configuration lives

`~/.dataiku/config.json` contains named profiles, their URLs, defaults, and a plaintext `api_key`. The setup page writes it atomically with user-only (0600) permissions; you can also edit it by hand. See [`.dataiku/config.json.example`](.dataiku/config.json.example).

Config file resolution is `DKU_CONFIG_FILE` → `~/.dataiku/config.json` → repo-local `./.dataiku/config.json`. Browser setup writes to `DKU_CONFIG_FILE` when set, otherwise to the home config.

At startup, config profiles are loaded first and the file's `default_instance` is active. Setting `DKU_DSS_URL` adds an environment-backed profile named `DKU_INSTANCE_NAME` (or `dss-env`) and makes it active instead. `switch_instance` changes the active profile only for the current MCP process.

Environment variables are an explicit override:

```bash
export DKU_INSTANCE_NAME="ci"
export DKU_DSS_URL="https://your-instance.dataiku.com"
export DKU_API_KEY="your-api-key"
```

**.env file:**
Copy `.env.example` to `.env` and fill in your values:
```bash
DKU_DSS_URL=https://your-instance.dataiku.com
DKU_API_KEY=your-api-key
DKU_MCP_MAX_WORKERS=4

# Set to true/1 to skip SSL verification, matching Dataiku's local config.
DKU_NO_CHECK_CERTIFICATE=false
```

**Connect to multiple instances:**
Put instance info in `.dataiku/config.json`. See `.dataiku/config.json.example` for the expected shape. The file's `default_instance` selects the startup instance.

After adding multiple instance configs, you can use the `list_instances`, `switch_instance`, and `get_current_instance` MCP tools to manage instances from the agent.

Auth resolution order:
1. Environment variables: `DKU_DSS_URL`, `DKU_API_KEY`, and optional `DKU_NO_CHECK_CERTIFICATE`
2. Local config: `.dataiku/config.json`, using its `default_instance`

## Run

Every install path above has your harness launch the server itself via `uvx`. Run it standalone only if you're testing it directly:

```bash
#TODO: remove the test.pypi index once published to pypi.org
uv pip install --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple dataiku-headless
dataiku-headless serve
# or simply:
dataiku-headless
```

Local development without any install (from a clone): `bash ./bin/run_mcp.sh`.

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
│   │   ├── project_folders.py # Project folder hierarchy inspection and organization tools
│   │   ├── projects.py        # Project inspection tools + create_project write
│   │   ├── scenarios.py       # Scenario/run-history/messaging-channel inspection tools
│   │   ├── semantic_models.py # Semantic model inspection tools
│   │   ├── webapps.py         # WebApp/backend-state inspection tools
│   │   ├── wikis.py           # Wiki article inspection tools
│   │   ├── project_libraries.py  # Project library inspection/search + local-file write
│   │   ├── recipes.py         # Recipe inspection tools
│   │   ├── machine_learning/  # ML analysis/saved-model inspection tools
│   │   └── utils/             # Shared runtime utilities
│   ├── config.py              # Instance/profile loading from config file + env vars
│   ├── config_mcp.py          # MCP configuration
│   ├── setup_server.py        # Temporary loopback page used by URL elicitation
│   ├── __init__.py
│   └── __main__.py
├── skills/
│   └── dataiku-headless/
│       ├── SKILL.md                # Single `dataiku-headless` entry skill: route, inspect, delegate, verify
│       └── references/
│           ├── cobuild.md          # Default in-project write path via Cobuild
│           ├── project-folders.md  # Project folder hierarchy inspection and organization
│           ├── projects.md         # Project discovery, metadata, variables, and flow orientation
│           ├── datasets.md         # Dataset inspection/profiling + Uploaded Files direct-write exception
│           ├── recipes.md          # Recipe inspection and recipe-family routing
│           ├── jobs.md             # DSS job tracking, waiting, and log inspection
│           ├── connections.md      # Connection discovery and capability inspection
│           ├── code-environments.md # Available code environments for prompts and execution context
│           ├── machine-learning.md # ML analysis, trained-model, and saved-model inspection
│           ├── agents.md           # Agent and agent-tool inspection
│           ├── ...                 # Additional references for dashboards, insights, scenarios, wikis, migrations, and more
│           └── recipes/            # Nested recipe-family and shared recipe references
├── .claude-plugin/
│   ├── plugin.json             # Claude Code plugin manifest (skills + unconfigured stdio MCP)
│   └── marketplace.json        # Marketplace catalog (single-plugin, source: "./")
├── .codex-plugin/
│   └── plugin.json             # Codex manifest with skills, stdio MCP, and env_vars passthrough
├── .mcp.json                   # Shared MCP config (bash ./bin/run_mcp.sh) for contributor dogfooding
├── CODING_STANDARDS_AND_STRUCTURE.md  # Contributor guide
└── pyproject.toml
```

## Contributing

See `CODING_STANDARDS_AND_STRUCTURE.md` for local setup, coding standards, guardrails, and the PR checklist.

## License

Licensed under the **[Apache License 2.0](LICENSE)**. Copyright 2026 Dataiku.
