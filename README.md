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

Work in Dataiku from your AI assistant. Describe what you want to accomplish,
and Dataiku Headless helps you explore data, build pipelines, train models,
create custom AI agents, and manage production deployments.

Use it with the [ChatGPT desktop app (Codex or Work)](docs/getting-started/chatgpt-desktop.md),
[Claude desktop app](docs/getting-started/claude-desktop.md),
[Cursor desktop app](docs/getting-started/cursor-desktop.md),
[GitHub Copilot desktop app](docs/getting-started/github-copilot-desktop.md),
[Snowflake CoCo desktop app](docs/getting-started/snowflake-coco-desktop.md),
[Codex CLI](docs/getting-started/codex-cli.md),
[Claude Code CLI](docs/getting-started/claude-code-cli.md),
[GitHub Copilot CLI](docs/getting-started/github-copilot-cli.md),
[Cursor Agent CLI](docs/getting-started/cursor-agent-cli.md),
[Snowflake CoCo CLI](docs/getting-started/snowflake-coco-cli.md),
[Grok CLI](docs/getting-started/grok-cli.md), or
[another MCP-compatible agent](docs/getting-started/other-mcp-agents.md).
Your work lives in Dataiku, where you can review and continue it.

## What you can do

- **Understand data, models, agents, and applications:** explore your data and
  understand how your models, agents, and applications work.
- **Build with Cobuild:** create and improve data pipelines, analytics, machine
  learning models, agents, and applications.
- **Deploy:** publish automated data pipelines, ML models, agents, and custom API Services to production environments (production databases, k8s clusters, and more).
- **Monitor:** review pipeline runs, agent evaluation results, and API service
  health.
- **Manage and customize your Dataiku environment:** inspect connections, organize projects, manage
  code environments, develop plugins, and manage users.

Build in a Dataiku Design environment, then publish and deploy to configured
production environments (Automation nodes and API infrastructures) through the  Deployer. Headless lets you work across
these environments from your assistant.

## Try asking

Once connected, use your own project and dataset names in requests such as:

- “Explain this project's Flow and check the datasets for data quality issues.”
- “Build a visual pipeline to clean this dataset and train a prediction model.”
- “Find out why the latest scenario run failed.”
- “Create a project bundle with the selected data and publish it for deployment.”

## Get started

1. **Install and connect Dataiku Headless.** Choose your harness guide:
   [ChatGPT desktop (Codex or Work)](docs/getting-started/chatgpt-desktop.md),
   [Claude desktop](docs/getting-started/claude-desktop.md),
   [Cursor desktop](docs/getting-started/cursor-desktop.md),
   [GitHub Copilot desktop](docs/getting-started/github-copilot-desktop.md),
   [Snowflake CoCo desktop](docs/getting-started/snowflake-coco-desktop.md),
   [Codex CLI](docs/getting-started/codex-cli.md),
   [Claude Code CLI](docs/getting-started/claude-code-cli.md),
   [GitHub Copilot CLI](docs/getting-started/github-copilot-cli.md),
   [Cursor Agent CLI](docs/getting-started/cursor-agent-cli.md),
   [Snowflake CoCo CLI](docs/getting-started/snowflake-coco-cli.md),
   [Grok CLI](docs/getting-started/grok-cli.md), or
   [another MCP-compatible agent](docs/getting-started/other-mcp-agents.md).
2. **Start with a project.** Ask your agent to show the projects you can access,
   then describe what you want to explore or build.

If your organization provides a remote Dataiku Headless plugin, use its
installation and login instructions instead. Inside a Dataiku Code Studio, the
hosting instance is discovered automatically.

For multiple instances, credentials, certificates, or advanced configuration,
see [Connecting to Dataiku](docs/connecting-to-dataiku.md).

## See it in action

In this example, Claude Code builds a visual pipeline to clean hospital
admissions data, trains a model to predict readmission within 30 days, and makes
predictions for new patients:

![Building a Dataiku project with Dataiku Headless and Claude Code](https://github.com/dataiku/dataiku-headless/releases/download/readme-media-v1/headless_demo_claude_code.gif)

## How it works

Dataiku Headless connects your AI assistant to Dataiku through MCP and provides
skills that guide the assistant through inspection, building, and verification.
Cobuild handles changes to project logic. You can return to an ongoing Cobuild
conversation, answer its questions, and review the resulting project.

For detailed workflows, see the [agent skill guide](skills/dataiku-headless/SKILL.md).
Administrators can use the [HTTP deployment guide](docs/self-hosting/http-deployment.md) to
provide a centrally managed connection with enterprise login.

## Contributing

See [Contributing](CONTRIBUTING.md) to report an issue or open a pull request.
Contributors can find implementation guidance in the
[coding standards](CODING_STANDARDS_AND_STRUCTURE.md) and publishing instructions
in the [release guide](RELEASE.md). To build or update a Dataiku plugin, see the
[plugin development guide](skills/dataiku-headless/references/plugin-development.md).

## License

Licensed under the **[Apache License 2.0](LICENSE)**. Copyright 2026 Dataiku.
