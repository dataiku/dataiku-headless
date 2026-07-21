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

An MCP server and agent skill library for operating Dataiku with an AI agent harness (Claude Code, Codex, Snowflake CoCo (Cortex Code), Cursor, OpenCode, or a custom agent). Connect your agent to a Dataiku instance to inspect projects, gather context, and drive Cobuild, Dataiku's AI building agent to build data pipelines, analytics, machine learning models, multi-agent workflows, applications, and automation pipelines inside Dataiku.

Cobuild is exposed here as a retained conversation, driven through MCP tools. This repo's own tool surface stays deliberately thin around it: read/list/get/inspect tools for grounding, three deterministic executions of existing assets (`build_datasets`, `run_recipe`, and `run_scenario`), plus a handful of bootstrap operations that are cross-project, instance-level, or must precede a project/conversation.

Cobuild conversations and their retained turns are **process-local**: they live only in the running server process, with no durable store. A server restart drops them, so start a new conversation rather than reusing an old id. A single turn can run for minutes; when a call reaches its wait timeout it returns a pollable `turn_id` (the worker keeps running). Poll it with `get_cobuild_turn_status` — **never resend a timed-out turn**, or you may duplicate a mutation.

## MCP Server

`dataiku_mcp` is a FastMCP server that exposes Dataiku DSS operations as typed, async MCP tools. Tools are organized by domain: projects, flow, connections, datasets, Data Quality, managed folders, recipes, machine learning, scenarios, agents, LLMs and knowledge banks, job management, project audit, and Cobuild conversations. The remaining Cobuild-built families (dashboards, insights, WebApps, wikis, evaluation stores, semantic models, agent tools/reviews, RAG LLMs) are read through one generic `get_object_settings` inspector rather than per-domain modules.

- Async execution for all Dataiku API calls
- Progress notifications for long-running operations
- Server-side authentication (env API key or `.dataiku/config.json`)
- Modular architecture by functional domain
- Dense, bounded orientation calls for a project overview and its Flow graph
- `get_object_settings`: one closed, redacted deep-read for independent verification across the Cobuild-built object families (agents, dashboards, wikis, semantic models, and more); it returns saved settings, not live/runtime state — obtain runtime proof (a WebApp's running backend, an agent review's runs) by delegating a read-only Cobuild turn. Discover ids for the families with no dedicated `list_*` tool from `get_project_overview`'s `object_inventory` section
- `audit_project`: a read-only, bounded Flow review after a build — a deterministic finish gate, not a correctness oracle. DSS Flow consistency and explicit output contracts fail closed; documentation and layout conventions stay advisory
- Cobuild conversation tools (`start_cobuild_conversation`, `send_cobuild_message`, `get_cobuild_turn_status`, `answer_cobuild_confirmation`, `list_cobuild_conversations`) as the default path for project-level asset creation
- One fixed, directly visible tool catalog of 58 tools (53 non-Cobuild inspect/execute/bootstrap tools plus 5 Cobuild conversation tools) — no tool-exposure or Cobuild "mode" that makes capabilities depend on deployment configuration. `references/tool-index.md` in the skill lists every name with a one-line purpose (generated from the live registry)

Tools do not accept API keys as arguments — authentication is resolved server-side from environment variables or a config file.
Project-variable reads redact credential-shaped fields, exclude local overrides by
default, and clip oversized values before returning them to the model.

## Agent Skill

`dataiku-skills/dataiku-headless` is one broad entry point for Dataiku work. Its
frontmatter `description` is what the agent harness matches against the conversation
to decide when to load it — there is no separate root routing file. Once loaded, the
`SKILL.md` carries permanent operating rules and a task table that selects one
objective playbook:

| Objective | Playbook |
| --- | --- |
| Build or change project assets through Cobuild | `build-via-cobuild.md` |
| Inspect and explain without mutation | `inspect-and-explain.md` |
| Execute behavior that already exists | `direct-execution.md` |
| Verify a delegated result | `verify-cobuild-output.md` |
| Migrate a legacy workflow | `migrate.md` |

Object, recipe, connection, ML/GenAI, safety, and migration facts live in
`references/`, loaded only when the chosen playbook needs them. Detailed Agent, Data
Quality, wiki, formula, prepare-processor, and migration-source material is preserved
there too.

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

# Set to true/1 to skip SSL verification, matching Dataiku's local config.
DKU_NO_CHECK_CERTIFICATE=false
```

**Transport is stdio, always.** The server is a single-user, single-credential
local plugin that the agent harness launches and speaks to over stdio. There is
no HTTP transport: an HTTP server would demand per-request credential ownership
and shared-state machinery this v1 deliberately excludes. If a hosted/multi-user
deployment is ever needed, it belongs in its own project, not behind an env flag
here. `create_upload_dataset` uploads from a local file path visible to the MCP
server process.

**Connect to multiple instances:**
Put instance info in `.dataiku/config.json`. See `.dataiku/config.json.example` for the expected shape. 

After adding multiple instance configs, you can use the `list_instances`, `switch_instance`, and `get_current_instance` MCP tools to manage instances from the agent.

Auth resolution order:
1. Environment variables: `DKU_DSS_URL`, `DKU_API_KEY`, and optional `DKU_NO_CHECK_CERTIFICATE`
2. The first existing config file: `$DKU_CONFIG_DIR/config.json`, `./.dataiku/config.json`, then `$XDG_CONFIG_HOME/dataiku-headless/config.json` (or `~/.config/dataiku-headless/config.json`)

The old `DKU_DEFAULT_CONNECTION`, `DKU_DEFAULT_FOLDER_CONNECTION`,
`DKU_DEFAULT_LLM`, and `DKU_DEFAULT_EMBEDDING_LLM` settings were never consumed
by a tool. They are no longer part of the configuration contract; pass concrete
object identifiers in the relevant tool or Cobuild instruction instead.

**Fixed tool surface:** the server registers one directly visible catalog. It
has no tool-exposure or Cobuild mode, so a deployment environment variable
cannot silently hide a verification tool.

## Run

Every install path above has your harness launch the server itself via `uvx`. Run it standalone only if you're testing it directly:

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
│   │   ├── agents.py          # Agent listing (list_agents)
│   │   ├── cobuild.py         # Cobuild conversation tools (start/send/poll/confirm/list)
│   │   ├── code_environments.py  # Code environment listing (list_code_envs)
│   │   ├── connections.py     # DSS connection discovery/test tools
│   │   ├── cross_project_sharing.py  # Cross-project shared-object listing
│   │   ├── data_collections.py  # Data Collection listing/inspection tools
│   │   ├── data_quality.py    # Dataset Data Quality rule inspection tools
│   │   ├── datasets.py        # Dataset inspection tools + local-file upload writes
│   │   ├── flow.py            # Flow graph, zones, and object-metadata inspection tools
│   │   ├── instances.py       # Multi-instance listing/switching tools
│   │   ├── jobs.py            # Job status/log/wait + build_datasets/run_recipe execution
│   │   ├── llms_and_knowledge_banks.py  # LLM listing (list_llms)
│   │   ├── managed_folders.py # Managed folder inspection tools + local-file upload write
│   │   ├── object_settings.py # One generic redacted deep-read across 13 Cobuild-built families (get_object_settings)
│   │   ├── project_audit.py   # Read-only bounded Flow audit gate (audit_project)
│   │   ├── project_libraries.py  # Project library inspection + local-file write (bounded)
│   │   ├── projects.py        # Project inspection/overview tools + create_project write
│   │   ├── recipes.py         # Recipe inspection tools
│   │   ├── scenarios.py       # Scenario inspection + run_scenario execution/history
│   │   ├── machine_learning/  # ML analysis/saved-model inspection tools
│   │   └── utils/             # Shared runtime utilities
│   ├── config.py
│   ├── config_mcp.py          # Worker-pool configuration
│   ├── __init__.py
│   └── __main__.py
├── dataiku-skills/
│   └── dataiku-headless/
│       ├── SKILL.md           # One objective router and permanent operating rules
│       ├── playbooks/         # Build, inspect, execute, verify, and migrate workflows
│       └── references/        # Object, recipe, ML/GenAI, safety, and source facts
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

## License

Licensed under the **[Apache License 2.0](LICENSE)**. Copyright 2026 Dataiku.
