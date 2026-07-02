# dataiku-mcp — Dataiku Headless

Local MCP packaging for Claude Code and Codex — the headless DSS control plane
for AI agents.

It exposes one MCP code-mode tool, `dku_exec`, which runs the `dku` CLI as your
DSS user. The plugin also installs the bundled Dataiku Headless skills through
the host agent's plugin/skill mechanism; skills are intentionally not exposed as
an MCP tool.

## Package role
This directory holds the host-specific plugin package:

- `.claude-plugin/plugin.json` for Claude Code
- `.codex-plugin/plugin.json` and `.mcp.json` for Codex
- `bin/dku-mcp-launch.sh`, shared by both plugins
- `wheels/`, the bundled Dataiku Headless wheel
- `skills/`, installed alongside the MCP server

Prerequisite at runtime: a POSIX shell. The launcher installs
[`uv`](https://docs.astral.sh/uv/) if needed.

## Runtime

- Tool: `dku_exec`
- Auth: `DKU_URL` + `DKU_API_KEY` for normal local/stdio use
- Scope: your DSS permissions and audit trail

Entry points:

- `dku-mcp`
- `python -m dku_cli.mcp`

Modes:

- `stdio`: single user, full env inheritance, current working directory
- `http`: bearer token auth, allowlisted env, per-session workdir, bubblewrap by default

In hosted mode, the real boundary is DSS API key permissions plus the sandbox
backend. `--dangerous` stripping is only a UX guard.

Runtime config:

- `DKU_URL`: DSS instance URL.
- `DKU_API_KEY`: DSS API key used by local/stdio launches and Codex-hosted local runs.
- `DKU_PROJECT`: default project injected into `dku_exec` sessions.
- `DKU_MCP_STATE_ROOT`: override the per-session state directory.
- `DKU_MCP_WORKDIR`: override the default working directory used for local path resolution.

Local `stdio` mode inherits your full shell environment. Hosted `http` mode uses
a scrubbed allowlist and explicit per-session auth. DSS-injected values such as
`DKU_API_TICKET` and backend host/port vars are runtime plumbing, not setup
knobs.

## Skills strategy

The Claude Code and Codex plugins install both:

- the one-tool MCP server (`dku_exec`)
- `skills/`, including `skills/dku-cli/`, as host-agent skills

That keeps the MCP surface small while still giving agents the latest DSS
guidance anywhere the plugin is installed.

## Maintainer commands

```bash
make plugin
make desktop-bundle
make test-plugin
```

## Troubleshooting

```bash
# verify prerequisites and auth
uvx --from <plugin>/wheels/*.whl --with "fastmcp>=2.0,<4" dku-mcp doctor
```

- **`uv: command not found`** → the launcher installs it; if your shell blocks
  `curl | sh`, install uv manually (`https://docs.astral.sh/uv/`) and restart.
- **auth errors** → re-check the DSS URL + key. Claude Code stores them in
  plugin user config; Codex inherits `DKU_URL` and `DKU_API_KEY` from its
  process environment.

## Contents

The plugin bundles:

- `wheels/`: the Dataiku Headless wheel
- `skills/`: the skill corpus installed by supported plugin hosts

Refresh both after CLI or skill changes:

```bash
make plugin
```

Relevant server files:

- `src/dku_cli/mcp/server.py`
- `src/dku_cli/mcp/executor.py`
- `src/dku_cli/mcp/sandbox.py`
- `src/dku_cli/mcp/http.py`
