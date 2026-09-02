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

Install it from the [Claude Code](#claude-code-cli) or [Codex](#codex-cli) plugin marketplace, or install it as an agent plugin from this GitHub repository for Cursor, Snowflake CoCo, AWS Kiro, OpenCode, and more.

## Requirements

Install [uv 0.12.0 or later](https://docs.astral.sh/uv/getting-started/installation/) and make sure it is available on your `PATH`. Dataiku Headless uses `uv` to provide its Python runtime and pinned dependencies.

## Get started with the Codex app or Claude Desktop app

Install the plugin, then ask Codex or Claude to set up your Dataiku instance. The setup flow securely saves your Dataiku URL and personal API key on your local machine.

Here's how to do it in the Codex app; Claude has a similar plugin-install flow.

![Installing and setting up the Dataiku Headless plugin with Codex](https://github.com/dataiku/dataiku-headless/releases/download/readme-media-v1/headless_install_setup_codex.gif)

Once connected, you can build in Dataiku.

Here, we use the Claude Code CLI to build a visual pipeline to clean up hospital admissions data, train a model to predict readmission within 30 days, then make predictions for new patients:

![Building a Dataiku project with Dataiku Headless and Claude Code](https://github.com/dataiku/dataiku-headless/releases/download/readme-media-v1/headless_demo_claude_code.gif)

## Install with another agent

`dataiku-headless` also works with Snowflake CoCo (Cortex Code), Cursor, OpenCode, and custom MCP-compatible agents. Each plugin starts the same local MCP server; after installation, use the same setup flow above.

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

### Claude Code CLI

```bash
claude plugin marketplace add https://github.com/dataiku/dataiku-headless.git
claude plugin install dataiku-headless@dataiku
```

### Grok CLI

```bash
grok plugin install dataiku/dataiku-headless --trust
```

### Cursor Agent CLI

```bash
cursor agent plugin marketplace add github.com/dataiku/dataiku-headless
# Tip: use /plugins in interactive mode to install `dataiku-headless` plugin from this marketplace.
```

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
      "command": ["uv", "run", "--quiet", "--locked", "--script", "./bin/run_mcp.py", "--transport", "stdio"],
      "enabled": true
    }
  }
}
```

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

`dataiku_mcp` is a FastMCP server that exposes Dataiku operations as typed, async MCP tools. Tools are organized by domain: projects, project folders, flow, connections, datasets, data quality, managed folders, recipes, machine learning, insights, dashboards, scenarios, WebApps, wikis, agents, LLMs and knowledge banks, job management, administrative tasks, and Cobuild conversations.

- Async execution for all Dataiku API calls
- Progress notifications for long-running operations
- Server-side authentication for the local stdio plugin (env API key or `.dataiku/stdio-config.json`)
- Modular architecture by functional domain
- Cobuild conversation tools (`start_cobuild_conversation`, `send_cobuild_message`, `answer_cobuild_confirmation`, `list_cobuild_conversations`) as the default path for project-level asset creation

Tools do not accept API keys as arguments — authentication is resolved server-side from environment variables or a config file.

### Streamable HTTP deployment

The local plugin remains stdio-only. A separately deployed HTTP server can be
started with `uv run --quiet --locked --script bin/run_mcp.py --transport http`.
It supports interactive OAuth login from MCP harnesses as well as MCP-audience
access tokens obtained by another application. Entra ID and Okta are supported:
the server exchanges the incoming token through Entra OBO or RFC 8693,
respectively, then sends only the resulting short-lived JWT to DSS.

It reads `~/.dataiku/http-config.json` by default, alongside the local stdio profiles
in `~/.dataiku/stdio-config.json`. Use `--settings-path PATH` only when the deployment
needs a different filesystem location. The HTTP file contains the OIDC verifier,
token-exchange client, transport settings, approved DSS catalog, and user
instance preferences. Copy [`.dataiku/http-config.json.example`](.dataiku/http-config.json.example)
as a starting point:

```bash
mkdir -p ~/.dataiku
cp .dataiku/http-config.json.example ~/.dataiku/http-config.json
chmod 600 ~/.dataiku/http-config.json
```

Keep this file access-restricted (`0600` on POSIX): it contains confidential
OAuth client secrets. When `oidc.interactive` is configured,
`server.public_url` is required as the externally visible base URL and the IdP
app's redirect URI is `<public_url>/auth/callback`. Omit both to run in direct
bearer-token mode. `user_selections` records each user's currently selected
instance; it is not a user allow-list. Any authenticated user may select an
endpoint from the catalog, and DSS applies its normal JWT user permissions.

For Okta, set `oidc.provider` to `oidc`. The example uses an OIDC web application
for interactive login and an API Services application with the Token Exchange
grant for downstream DSS access. Configure access policies for the requested
scopes, and configure trust between the MCP and DSS authorization servers if
they differ. Because the exchange URL is global, every DSS instance in one
settings file must use that target authorization server and exchange client.

For Entra ID, set `oidc.provider` to `entra` and add `tenant_id` inside the
optional `oidc.interactive` object. The interactive and token-exchange clients
may be separate Entra app registrations: the latter must represent the MCP
middle-tier API targeted by the incoming token. Register
`<public_url>/auth/callback`, expose the configured MCP scope, add each DSS API's
delegated permission, and grant administrator consent. Each instance's `scope`
must be the fully qualified downstream scope, such as
`api://<dss-application-id>/dss.access`. Entra OBO supports delegated user
tokens, not application-only tokens.

A custom application can skip interactive login and supply a bearer token
directly. The token must be a signed user access JWT with the configured issuer,
audience, and `scope` or `scp` value.

## Agent Skills

`skills` exposes a single prompt-based skill entrypoint, `dataiku-headless`, plus a routed reference library under `skills/dataiku-headless/references/`. The entry skill decides which reference guide to read next, carries the shared operating rules, routes in-project asset changes through Cobuild by default, and documents the narrow direct-write exceptions for bootstrap, cross-project, instance-level, or administrative operations that Cobuild does not handle.

The reference library covers the main Dataiku object areas and workflows, including projects, project folders, datasets, recipes, jobs, connections, code environments, managed folders, project libraries, data quality, machine learning, agents, agent reviews, scenarios, semantic models, webapps, wikis, dashboards, insights, data collections, cross-project sharing, and migrations.

## Stdio onboarding and authentication

The onboarding flow is the same:

1. Ask the agent to setup your Dataiku instance (**run `configure_instance`**).
2. Approve the MCP URL prompt.
3. Enter an instance name, Dataiku URL, and personal API key.
4. Repeat to add more instances; use `list_instances` and `switch_instance` while working.

The API key never appears in MCP tool arguments.

For HTTP deployments, `configure_instance` and `delete_instance` are disabled.
Use `list_instances`, then `switch_instance`, to select a platform-managed DSS
instance for the authenticated user.

### Where configuration lives

The resolved configuration file contains named profiles, their URLs, defaults, and a plaintext `api_key`. The setup page writes it atomically with user-only (0600) permissions; you can also edit it by hand. Use `--settings-path PATH` to select an explicit path; otherwise, the server selects its configuration file once at startup in this order:

1. An existing `./.dataiku/stdio-config.json` in the server's working directory.
2. `~/.dataiku/stdio-config.json` otherwise.

All reads, additions, and deletions use that same resolved path for the server process. See [`.dataiku/stdio-config.json.example`](.dataiku/stdio-config.json.example) for the file shape.

Environment variables are an explicit override:

**.env file:**
Copy `.env.example` to `.env` and fill in your values:
```bash
DKU_DSS_URL=https://your-instance.dataiku.com
DKU_API_KEY=your-api-key
DKU_MCP_MAX_WORKERS=4
DKU_NO_CHECK_CERTIFICATE=false
```
The canonical `bin/run_mcp.py` launcher reads this file after validating its
arguments and before importing the MCP package. `.env` only fills in variables
not already set in your shell or launcher—a real environment variable of the
same name always wins, even if it is empty. Importing `dataiku_mcp` directly does
not read `.env`; embedding callers must prepare their environment first.

**Connect to multiple instances:**
Put instance info in the resolved configuration file. See `.dataiku/stdio-config.json.example` for the expected shape.

After adding multiple instance configs, you can use the `list_instances`, `switch_instance`, and `get_current_instance` MCP tools to manage instances from the agent.

Auth resolution order:
1. Environment variables: `DKU_DSS_URL`, `DKU_API_KEY`, and optional `DKU_NO_CHECK_CERTIFICATE`
2. The resolved configuration file, using its `default_instance`

## Run

Every install path above has your harness launch the server itself. Run it standalone only if you're testing it directly — from a clone of this repo:

```bash
uv run --quiet --locked --script ./bin/run_mcp.py --transport stdio
```

## Project Structure

```text
.
├── dataiku_mcp/
│   ├── auth.py                # Dataiku client creation and HTTP token exchange
│   ├── executors.py           # Shared blocking and Cobuild executors
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
│   │   ├── jobs.py            # Async job status/log/wait tools
│   │   ├── llms_and_knowledge_banks.py  # LLM, Knowledge Bank, and RAG inspection tools
│   │   ├── managed_folders.py # Managed folder inspection tools + local-file upload write
│   │   ├── project_folders.py # Project folder hierarchy inspection and organization tools
│   │   ├── projects.py        # Project inspection tools + create_project write
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
│   │   └── utils/             # Tool validation and response-shaping utilities
│   ├── config/                # Models, stdio/HTTP configuration, and request routing
│   ├── server.py              # FastMCP construction, middleware, and transport startup
│   ├── setup_server.py        # Temporary loopback page used by URL elicitation
│   └── __init__.py            # Public API and tool-registration composition root
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
│           ├── jobs.md             # Dataiku job tracking, waiting, and log inspection
│           ├── connections.md      # Connection discovery and capability inspection
│           ├── machine-learning.md # ML analysis, trained-model, and saved-model inspection
│           ├── agents.md           # Agent and agent-tool inspection
│           ├── ...                 # Additional references for dashboards, insights, scenarios, wikis, migrations, and more
│           └── recipes/            # Nested recipe-family and shared recipe references
├── bin/
│   ├── launcher.sh             # Inactive legacy fallback retained for possible future use
│   ├── run_mcp.py              # Server entry point: PEP 723 script pinning the runtime deps inline
│   └── run_mcp.py.lock         # Committed, full dependency resolution for the entry point
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
