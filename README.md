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

## About Dataiku Headless

Dataiku Headless is an MCP server with tools for working in Dataiku, plus skills that teach AI assistants how to use them. Connect it to a Dataiku instance, and your AI assistant can build data pipelines, models, dashboards, agents, and more.

Install it from the [Claude Code](#claude-code-cli) or [Codex](#codex-cli) plugin marketplace. The repository also ships an [Agent Plugins](https://agent-plugins.org/) v1.0.0 package for Cursor and other conforming clients.

## Requirements

Dataiku Headless uses [uv 0.12.0 or later](https://docs.astral.sh/uv/getting-started/installation/) to provide its isolated Python runtime and pinned dependencies. You do not need to install it before installing the plugin: the setup skill checks for uv and, with your approval, can run the official installer for your platform.

## Get started with the Codex app or Claude Desktop app

Install the plugin, then select or ask **Set up Dataiku Headless**. In Claude Code, you can explicitly run `/dataiku-headless:dataiku-headless-setup`. The setup skill checks the local runtime, helps install uv when needed, and securely saves your Dataiku URL and personal API key on your local machine.

Here's how to do it in the Codex app; Claude has a similar plugin-install flow.

![Installing and setting up the Dataiku Headless plugin with Codex](https://github.com/dataiku/dataiku-headless/releases/download/readme-media-v1/headless_install_setup_codex.gif)

Once connected, you can build in Dataiku.

Here, we use the Claude Code CLI to build a visual pipeline to clean up hospital admissions data, train a model to predict readmission within 30 days, then make predictions for new patients:

![Building a Dataiku project with Dataiku Headless and Claude Code](https://github.com/dataiku/dataiku-headless/releases/download/readme-media-v1/headless_demo_claude_code.gif)

## Install with another agent

`dataiku-headless` also works with Cursor, OpenCode, and other Agent Plugins-compatible clients. The portable package uses the root `plugin.json`, root `mcp.json`, and the shared `skills/` directory; dedicated manifests remain for Claude Code and Codex.

> **First launch:** If Dataiku Headless tools are unavailable, first check that `uv` is installed and on your `PATH`:
>
> ```bash
> uv --version
> ```
>
> If the command is not found (or reports a version below 0.12.0), install uv using the [official installation guide](https://docs.astral.sh/uv/getting-started/installation/), then fully restart your agent app. If uv is available, the first launch may still take a little longer; wait a minute and restart the app once. An agent with local-command access can perform this check and, with your approval, run the appropriate installer for your platform.

### Codex CLI

```bash
codex plugin marketplace add https://github.com/dataiku/dataiku-headless.git
codex plugin add dataiku-headless@dataiku
```

### Agent Plugins (portable)

This repository is an [Agent Plugins](https://agent-plugins.org/) v1.0.0 package: root `plugin.json`, root `mcp.json`, and Agent Skills under `skills/`. Any client that implements the standard can load the portable core directly from this directory.

Harness-specific manifests (`.claude-plugin/`, `.codex-plugin/`, …) remain for install paths those clients already support. They are additive compatibility layers; the portable files are the cross-client floor.

### Claude Code CLI

```bash
claude plugin marketplace add https://github.com/dataiku/dataiku-headless.git
claude plugin install dataiku-headless@dataiku
```

### Grok CLI

```bash
grok plugin install dataiku/dataiku-headless --trust
```

### Cursor

Open **Customize** in the Cursor sidebar, add this GitHub repository as a
plugin source, then install `dataiku-headless` at your preferred user or project
scope. Cursor detects the root Agent Plugins manifest and loads the bundled
skills and MCP server.

### Snowflake CoCo

```bash
cortex plugin install dataiku/dataiku-headless
```

### Other AI assistants

#### MCP

Add the following to your `.mcp.json` from a checkout of this repository:

```json
{
  "mcp": {
    "dataiku": {
      "type": "local",
      "command": ["uv", "run", "--quiet", "--locked", "--script", "./runtime/run_mcp.py"],
      "enabled": true
    }
  }
}
```

Portable Agent Plugins clients read root `mcp.json` instead. It launches the same locked `uv` script entry point as the existing manifests.

#### Skills

The `skills/*/SKILL.md` files follow the universal skill format:

```bash
npx skills add dataiku/dataiku-headless
```

## What it does

Dataiku Headless is an MCP server and agent skill library for operating Dataiku from an AI agent. Connect it to a Dataiku instance to inspect projects, gather context, and use Cobuild—Dataiku's agent for building data pipelines, analytics, machine learning models, multi-agent workflows, applications, and automation pipelines.

Cobuild runs as a retained conversation through MCP tools. This repository intentionally keeps its own tool surface small: inspection tools, three deterministic executions of existing assets (`build_datasets`, `run_recipe`, and `run_scenario`), and a few bootstrap actions that Cobuild cannot perform, such as creating a project or uploading a local file.

## Capability reference

For a quick reference to what Headless can inspect, what Cobuild builds, and the
limited direct actions Headless supports, see the
[Headless capability matrix](docs/capabilities.md).

## MCP Server

`dataiku_mcp` is a FastMCP server that exposes Dataiku operations as typed, async MCP tools. Tools are organized by domain: projects, project folders, flow, connections, datasets, data quality, managed folders, recipes, machine learning, insights, dashboards, scenarios, WebApps, wikis, agents, LLMs and knowledge banks, instance plugins, job management, administrative tasks, and Cobuild conversations.

- Async execution for all Dataiku API calls
- Progress notifications for long-running operations
- Server-side authentication (env API key or `.dataiku/config.json`)
- Modular architecture by functional domain
- Cobuild conversation tools (`start_cobuild_conversation`, `send_cobuild_message`, `answer_cobuild_confirmation`, `list_cobuild_conversations`) as the default path for project-level asset creation

Tools do not accept API keys as arguments — authentication is resolved server-side from environment variables or a config file.

## Agent Skills

`skills` exposes two prompt-based entrypoints: `dataiku-headless-setup` for first-time installation, runtime recovery, and instance configuration; and `dataiku-headless` for Dataiku work. The main entry skill decides which reference guide to read next, carries the shared operating rules, routes in-project asset changes through Cobuild by default, and documents the narrow direct-write exceptions for bootstrap, cross-project, instance-level, or administrative operations that Cobuild does not handle.

The reference library covers the main Dataiku object areas and workflows, including projects, project folders, datasets, recipes, jobs, connections, code environments, plugins, managed folders, project libraries, data quality, machine learning, agents, agent reviews, scenarios, semantic models, webapps, wikis, dashboards, insights, data collections, cross-project sharing, and migrations.

## Onboarding and authentication

The onboarding flow is the same:

1. Ask the agent to **Set up Dataiku Headless** (or run `/dataiku-headless:dataiku-headless-setup` in Claude Code).
2. Approve the MCP URL prompt.
3. Enter an instance name, Dataiku URL, and personal API key.
4. Repeat to add more instances; use `list_instances` and `switch_instance` while working.

The API key never appears in MCP tool arguments.

### Where configuration lives

The resolved configuration file contains named profiles, their URLs, defaults, and a plaintext `api_key`. The setup page writes it atomically with user-only (0600) permissions; you can also edit it by hand. The server selects its configuration file once at startup, in this order:

1. The explicit `DKU_CONFIG_FILE` path, when set.
2. An existing `./.dataiku/config.json` in the server's working directory.
3. `~/.dataiku/config.json` otherwise.

All reads, additions, and deletions use that same resolved path for the server process. See [`.dataiku/config.json.example`](.dataiku/config.json.example) for the file shape.

Environment variables are an explicit override:

**.env file:**
Copy `.env.example` to `.env` and fill in your values:
```bash
DKU_DSS_URL=https://your-instance.dataiku.com
DKU_API_KEY=your-api-key
DKU_MCP_MAX_WORKERS=4
DKU_NO_CHECK_CERTIFICATE=false
```
`.env` only fills in variables not already set in your shell or launcher — a real environment variable of the same name always wins, even if it's empty.

**Connect to multiple instances:**
Put instance info in the resolved configuration file. See `.dataiku/config.json.example` for the expected shape.

After adding multiple instance configs, you can use the `list_instances`, `switch_instance`, and `get_current_instance` MCP tools to manage instances from the agent.

Auth resolution order:
1. Environment variables: `DKU_DSS_URL`, `DKU_API_KEY`, and optional `DKU_NO_CHECK_CERTIFICATE`
2. The resolved configuration file, using its `default_instance`

## Run

Every install path above has your harness launch the server itself. Run it standalone only if you're testing it directly — from a clone of this repo:

```bash
uv run --quiet --locked --script ./runtime/run_mcp.py   # same command the plugin manifests use
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
│   │   ├── connections.py     # Dataiku connection discovery/test tools
│   │   ├── cross_project_sharing.py  # Cross-project sharing inspection tools
│   │   ├── data_collections.py  # Data Collection listing/inspection tools
│   │   ├── data_quality.py    # Dataset Data Quality rule inspection tools
│   │   ├── dashboards.py      # Dashboard inspection tools
│   │   ├── datasets.py        # Dataset inspection tools + local-file upload writes
│   │   ├── evaluation_stores.py  # Evaluation Store inspection tools
│   │   ├── flow.py            # Flow inspection tools
│   │   ├── instances.py       # Multi-instance switching tools
│   │   ├── jobs.py            # Async job status/log/wait/abort tools
│   │   ├── llms_and_knowledge_banks.py  # LLM, Knowledge Bank, and RAG inspection tools
│   │   ├── managed_folders.py # Managed folder inspection tools + local-file upload write
│   │   ├── plugins.py         # Instance plugin listing, updates, and deletion
│   │   ├── project_folders.py # Project folder hierarchy inspection and organization tools
│   │   ├── projects.py        # Project inspection, creation, variables, and settings
│   │   ├── scenarios.py       # Scenario/run-history/messaging-channel inspection tools
│   │   ├── semantic_models.py # Semantic model inspection tools
│   │   ├── groups.py          # Instance group administration tools
│   │   ├── licensing.py       # Instance licensing status inspection tool
│   │   ├── users.py           # Instance user administration tools
│   │   ├── webapps.py         # WebApp/backend-state inspection tools
│   │   ├── wikis.py           # Wiki article inspection tools
│   │   ├── project_libraries.py  # Project library inspection/search + local-file write
│   │   ├── recipes.py         # Recipe inspection tools
│   │   ├── machine_learning/  # ML analysis/saved-model inspection tools
│   │   └── utils/             # Shared runtime utilities
│   ├── config.py              # Instance/profile loading from config file + env vars
│   ├── config_mcp.py          # MCP configuration
│   ├── setup_server.py        # Temporary loopback page used by URL elicitation
│   └── __init__.py
├── skills/
│   └── dataiku-headless/
│       ├── SKILL.md                # Single `dataiku-headless` entry skill: route, inspect, delegate, verify
│       └── references/
│           ├── administration.md   # Route instance-level user, group, and licensing tasks
│           ├── cobuild.md          # Default in-project write path via Cobuild
│           ├── project-folders.md  # Project folder hierarchy inspection and organization
│           ├── projects.md         # Project discovery, metadata, variables, and flow orientation
│           ├── datasets.md         # Dataset inspection/profiling + Uploaded Files direct-write exception
│           ├── recipes.md          # Recipe inspection and recipe-family routing
│           ├── jobs.md             # Dataiku job tracking, waiting, aborting, and log inspection
│           ├── connections.md      # Connection discovery and capability inspection
│           ├── machine-learning.md # ML analysis, trained-model, and saved-model inspection
│           ├── agents.md           # Agent and agent-tool inspection
│           ├── ...                 # Additional references for dashboards, insights, scenarios, wikis, migrations, and more
│           └── recipes/            # Nested recipe-family and shared recipe references
├── runtime/
│   ├── launcher.sh             # Inactive legacy fallback retained for possible future use
│   ├── run_mcp.py              # Server entry point: PEP 723 script pinning the runtime deps inline
│   └── run_mcp.py.lock         # Committed, full dependency resolution for the entry point
├── plugin.json                 # Agent Plugins v1.0.0 portable manifest
├── mcp.json                    # Agent Plugins portable stdio MCP config
├── .claude-plugin/
│   ├── plugin.json             # Claude Code plugin manifest (skills + unconfigured stdio MCP)
│   └── marketplace.json        # Marketplace catalog (single-plugin, source: "./")
├── .codex-plugin/
│   └── plugin.json             # Codex plugin manifest
├── .mcp.json                   # Bundled Codex/ChatGPT MCP config
├── CODING_STANDARDS_AND_STRUCTURE.md  # Contributor guide
└── pyproject.toml
```

## Contributing

See `CODING_STANDARDS_AND_STRUCTURE.md` for local setup, coding standards, guardrails, and the PR checklist, and `RELEASE.md` for how versions and releases are cut.

## License

Licensed under the **[Apache License 2.0](LICENSE)**. Copyright 2026 Dataiku.
