# ◆ Dataiku Headless

**The headless DSS control plane for AI agents.**

Dataiku Headless turns a Dataiku DSS instance into something an agent can drive
end to end — no UI, no clicking, no screen-scraping. It ships three things that
work together:

- **One MCP code-mode tool — `dku_exec`.** A single tool that runs the `dku` CLI
  as your DSS user. Agents compose real shell commands instead of juggling
  hundreds of narrow tool definitions.
- **A full `dku` CLI — dozens of command groups.** Projects, datasets, recipes, jobs,
  scenarios, dashboards, models, agents, knowledge banks, plugins, webapps,
  Govern, admin, and more. Typed options, self-describing `--help`, prescriptive
  errors — built so an agent succeeds on the first try.
- **A skill corpus.** Task-complete playbooks and cold-detail references the host
  agent installs alongside the MCP server, so agents get the latest DSS guidance
  without anyone managing skill files by hand.

Every command executes **as you**, with **your DSS permissions and audit trail**,
authenticated from `DKU_API_KEY` or a stored local credential.

> **Security model — read before deploying.** Authorization is **your DSS API
> key's permissions**, not the CLI. Execution isolation depends on the transport:
> - **Local / stdio** (every quick-start below, and Claude Code / Codex / Claude Desktop):
>   `dku_exec` runs as **a normal shell on your machine with your full environment**
>   — the same trust level as your agent's own shell. **No sandbox.**
> - **Hosted / HTTP** (multi-tenant, *experimental*): runs inside a **bubblewrap**
>   sandbox when available; binds to loopback by default. If bubblewrap is absent it
>   falls back to an **unisolated subprocess** — run `dku-mcp doctor` to check.
>
> The tiered destructive-op guards (exit 77 on a missing confirmation flag) are
> **accident prevention, not an authorization boundary**: a confirmation flag is
> model-settable, so a real boundary requires your harness to relay exit-77 to a
> human. See [`docs/design/safety-stance.md`](docs/design/safety-stance.md).

This repo ships:

- `dku`: the Dataiku Headless command-line interface
- `dataiku-mcp`: local MCP packaging for Claude Code, Codex, and Claude Desktop
- `dataiku-mcp/skills/dku-cli`: the agent skill corpus installed by the plugins alongside the MCP server

**Requirements:** Python 3.10–3.13, DSS 14.5+.

## Install

Install from git or a local clone:

```bash
uv tool install git+https://github.com/dataiku/dku-headless.git
export DKU_URL=https://dss.example.com
export DKU_API_KEY=dkuaps-...
dku whoami                 # verify connection
```

All install paths — MCP extras, agent-host plugins (Claude Code, Codex, Claude
Desktop), updating, and auth — are in [`docs/install.md`](docs/install.md).

## Quick start

```bash
dku whoami                  # verify connection
dku project list            # list projects
dku dataset head DS -P PROJ # preview data
```

## Configuration

Common environment variables:

- `DKU_URL`: DSS instance URL.
- `DKU_API_KEY`: DSS API key for non-interactive use, CI, containers, and agent hosts.
- `DKU_PROFILE`: select a saved auth profile created with `dku auth login`.
- `DKU_PROJECT`: default project key for project-scoped commands.
- `DKU_FORMAT`: default output mode (`tsv`, `json`, `csv`, `ids`, `quiet`).
- `DKU_HUMAN_MODE=1`: human presentation at a terminal — readable help text, aligned tables, indented JSON. Presentation only: never changes safety behavior, piped output, or output under an explicit `--format`.
- `DKU_DANGEROUS=1`: bypass tier-2 and tier-3 confirmation guards for the current session. Tier-4 admin guards still block.
- `DKU_MCP_STATE_ROOT`: override the MCP server session-state directory.
- `DKU_MCP_WORKDIR`: override the MCP server working directory for local path resolution.

Precedence is flags first, then environment variables, then the active saved profile.

Examples:

```bash
export DKU_URL=https://dss.example.com
export DKU_API_KEY=dkuaps-...
export DKU_PROJECT=MY_PROJECT
export DKU_HUMAN_MODE=1
dku --help
```

Full reference: [`dataiku-mcp/skills/dku-cli/SKILL.md`](dataiku-mcp/skills/dku-cli/SKILL.md)
and `dku <command> --help`.

MCP packaging: `make plugin`, `make desktop-bundle`, `make test-plugin`.

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

## More

| Resource | Link |
|---|---|
| Release notes | [GitHub Releases](https://github.com/dataiku/dku-headless/releases) |
| Safety model | [`docs/design/safety-stance.md`](docs/design/safety-stance.md) |
| Install guide | [`docs/install.md`](docs/install.md) |
| MCP plugin docs | [`dataiku-mcp/README.md`](dataiku-mcp/README.md) |
| Agent skill corpus | [`dataiku-mcp/skills/dku-cli/`](dataiku-mcp/skills/dku-cli/) |
| Command reference | `dku <command> --help` |
