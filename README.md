# ◆ dataiku-mcp + dku-cli

This repo ships:

- `dku`: the Dataiku CLI
- `dataiku-mcp`: local MCP packaging for Claude Code, Codex, and Claude Desktop
- `dataiku-mcp/skills/dku-cli`: agent reference material installed by the plugins alongside the MCP server

## Install

### CLI

```bash
git clone git@github.com:dataiku/dataiku-cli.git
cd dataiku-cli
uv tool install --from . dku-cli
dku auth login
dku whoami
```

### Local MCP

```bash
claude plugin marketplace add dataiku/dataiku-cli
claude plugin install dataiku-mcp
```

For Codex:

```bash
codex plugin marketplace add dataiku/dataiku-cli
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
cd /path/to/dataiku-cli
git pull
uv tool install --from . dku-cli --force --reinstall
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
