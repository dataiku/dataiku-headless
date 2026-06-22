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

> **Access** — `dataiku/dku-headless` is a **private** repo. You need read access
> and HTTPS git auth to GitHub: run `gh auth login` (or put a PAT in your git
> credential helper). Every command below clones over **HTTPS** — none use SSH.
> [`uv`](https://docs.astral.sh/uv/) is required for the CLI.

### 1. CLI — required for every agent

```bash
uv tool install --from git+https://github.com/dataiku/dku-headless.git dataiku-headless --force
dku auth login          # DSS URL + personal API key
dku whoami
```

> Upgrading from the old `dku-cli` package? Uninstall it first, or the shared
> `dku` binary gets orphaned: `uv tool uninstall dku-cli` before the install above.

### 2. Claude Code — MCP + skills

```bash
claude plugin marketplace add https://github.com/dataiku/dku-headless.git
claude plugin install dataiku-mcp
```

Installs the one MCP tool (`dku_exec`) **and** the bundled skills (`dku-cli`,
`migration`, `dataiku-internal-branding`). You are prompted for your DSS URL +
API key. Restart Claude Code to load the skills.

### 3. Codex — MCP + skills

```bash
codex plugin marketplace add https://github.com/dataiku/dku-headless.git
```

Then enable the `dataiku-mcp` plugin in Codex's plugin manager (it registers
under the `dataiku-marketplace` marketplace in `~/.codex/config.toml`). Codex
reads the DSS connection from the environment:

```bash
export DKU_URL="https://your-dss-host"
export DKU_API_KEY="your-dss-personal-api-key"
```

### 4. OpenCode / any MCP client

No marketplace — install the CLI with the `mcp` extra, then point your client at
the local `dku-mcp` stdio server:

```bash
uv tool install --from git+https://github.com/dataiku/dku-headless.git "dataiku-headless[mcp]" --force
```

```json
{
  "mcp": {
    "dku": {
      "type": "local",
      "command": ["dku-mcp", "serve", "--transport", "stdio"],
      "enabled": true,
      "environment": { "DKU_URL": "https://your-dss-host", "DKU_API_KEY": "your-key" }
    }
  }
}
```

Ready-to-copy config: [`dataiku-mcp/examples/opencode.json`](dataiku-mcp/examples/opencode.json).
MCP-only clients get `dku_exec` but not the skills — copy `dataiku-mcp/skills/*`
into the client's skills directory if it supports skills.

**Plugin strategy:** one MCP tool (`dku_exec`) plus the bundled skills, installed
through the host agent's plugin/skill mechanism — not a second MCP tool — so
agents get the latest DSS guidance without managing skill files by hand.

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
# CLI — reinstall from source:
uv tool install --from git+https://github.com/dataiku/dku-headless.git dataiku-headless --force --reinstall

# MCP + skills (bundled in the plugin) — refresh the marketplace, then update:
claude plugin marketplace update dataiku-marketplace   # Claude Code
claude plugin update dataiku-mcp                        # restart your agent to apply
codex plugin marketplace upgrade dataiku-marketplace   # Codex
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
