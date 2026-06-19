# ◆ Dataiku Headless

**The headless DSS control plane for AI agents.**

Dataiku Headless turns a Dataiku DSS instance into something an agent can drive
end to end — no UI, no clicking, no screen-scraping. It ships three things that
work together:

- **One MCP code-mode tool — `dku_exec`.** A single tool that runs the `dku` CLI
  as your DSS user. Agents compose real shell commands instead of juggling
  hundreds of narrow tool definitions.
- **A full `dku` CLI — ~70 command groups.** Projects, datasets, recipes, jobs,
  scenarios, dashboards, models, agents, knowledge banks, plugins, webapps,
  Govern, admin, and more. Typed options, self-describing `--help`, prescriptive
  errors — built so an agent succeeds on the first try.
- **A skill corpus.** Task-complete playbooks and cold-detail references the host
  agent installs alongside the MCP server, so agents get the latest DSS guidance
  without anyone managing skill files by hand.

Everything runs through **sandboxed execution** with **OS-keychain auth** — every
command executes as you, with your DSS permissions and audit trail.

This repo ships:

- `dku`: the Dataiku Headless command-line interface
- `dataiku-mcp`: local MCP packaging for Claude Code, Codex, and Claude Desktop
- `dataiku-mcp/skills/dku-cli`: the agent skill corpus installed by the plugins alongside the MCP server

## Install

### CLI

```bash
git clone git@github.com:dataiku/dataiku-headless.git
cd dataiku-headless
uv tool install --from . dataiku-headless
dku auth login
dku whoami
```

### Local MCP

```bash
claude plugin marketplace add dataiku/dataiku-headless
claude plugin install dataiku-mcp
```

For Codex:

```bash
codex plugin marketplace add dataiku/dataiku-headless
codex plugin install dataiku-mcp
```

The plugin strategy is: install one MCP tool (`dku_exec`) plus the bundled
skills. Skills are installed through the host agent's plugin/skill mechanism,
not exposed as a second MCP tool, so agents get the latest DSS guidance without
users managing separate skill files.

### Claude Desktop bundle

```bash
make desktop-bundle
```

## Quick Start

```bash
dku whoami                  # verify connection
dku project list            # list projects
dku dataset head DS -P PROJ # preview data
```

Full reference: [dataiku-mcp/skills/dku-cli/SKILL.md](dataiku-mcp/skills/dku-cli/SKILL.md)

### MCP Packaging

```bash
make plugin
make desktop-bundle
make test-plugin
```

---

## Update

```bash
# CLI
cd /path/to/dataiku-headless
git pull
uv tool install --from . dataiku-headless --force --reinstall
```

---

## Development

```bash
uv sync
uv run pre-commit install
uv run pytest -v
```

---

## License

Apache 2.0
