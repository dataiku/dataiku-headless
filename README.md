<div align="center">

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/assets/dataiku-lockup-white.svg">
  <img alt="Dataiku" src="docs/assets/dataiku-lockup-black.svg" width="280">
</picture>

<h1>Dataiku Headless</h1>

<p><strong>Agentic Analytics, Data Science, and AI Development powered by Dataiku Cobuild</strong></p>

<p>
  <a href="LICENSE"><img alt="License: Apache 2.0" src="https://img.shields.io/badge/License-Apache_2.0-blue.svg"></a>
  <img alt="Python 3.10+" src="https://img.shields.io/badge/python-3.10%2B-blue.svg">
</p>

</div>

## About Dataiku Headless

Work in Dataiku from your AI assistant. Describe what you want to accomplish,
and Dataiku Headless helps you explore data, build pipelines, train models,
create custom AI agents, and manage production deployments.

Use it with:

- [ChatGPT desktop app (Codex or Work)](docs/getting-started/chatgpt-desktop.md) /
  [Codex CLI](docs/getting-started/codex-cli.md)
- [Claude desktop app (Cowork or Claude Code)](docs/getting-started/claude-desktop.md) /
  [Claude Code CLI](docs/getting-started/claude-code-cli.md)
- [Cursor desktop app](docs/getting-started/cursor-desktop.md) /
  [Cursor Agent CLI](docs/getting-started/cursor-agent-cli.md)
- [GitHub Copilot desktop app](docs/getting-started/github-copilot-desktop.md) /
  [GitHub Copilot CLI](docs/getting-started/github-copilot-cli.md)
- [Snowflake CoCo desktop app](docs/getting-started/snowflake-coco-desktop.md) /
  [Snowflake CoCo CLI](docs/getting-started/snowflake-coco-cli.md)
- [Grok CLI](docs/getting-started/grok-cli.md)
- [Google Antigravity](docs/getting-started/google-antigravity.md)
- [Another MCP-compatible agent](docs/getting-started/other-mcp-agents.md)

Your work lives in Dataiku, where you can review and continue it.

## What you can do

- **Understand data, models, agents, and applications:** explore your data and
  understand how your models, agents, and applications work.
- **Build with Cobuild:** create and improve data pipelines, analytics, machine
  learning models, agents, and applications.
- **Deploy:** publish project bundles to Automation nodes, create and publish
  [API Services](skills/dataiku-headless/references/api-services.md), and deploy
  their versions to API infrastructures such as Kubernetes clusters.
  Pipelines running on Automation nodes can write outputs to production
  databases.
- **Monitor:** review pipeline runs, agent evaluation results, and API service
  health, and [test deployed API endpoints](skills/dataiku-headless/references/api-deployer.md#test-deployed-endpoints).
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

1. **Install and connect Dataiku Headless.** Follow the guide for your assistant
   [above](#about-dataiku-headless).
2. **Start with a project.** Ask your agent to show the projects you can access,
   then describe what you want to explore or build.

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

If your organization provides a custom Dataiku Headless plugin, follow its
setup instructions. For more connection options, see
[Connecting to Dataiku](docs/connecting-to-dataiku.md).

## Contributing

See [Contributing](CONTRIBUTING.md) to report an issue or open a pull request.
Contributors can find implementation guidance in the
[coding standards](CODING_STANDARDS_AND_STRUCTURE.md) and publishing instructions
in the [release guide](RELEASE.md). Finalize versions and release notes in the
last feature/fix PR with `uv run python scripts/finalize_release.py release/X.Y.Z`.
Release branches publish automatically after merging into main and passing CI.

## License

Licensed under the **[Apache License 2.0](LICENSE)**. Copyright 2026 Dataiku.
