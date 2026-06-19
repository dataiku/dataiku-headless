# dataiku-mcp — Dataiku Headless

Local MCP packaging for Claude Code and Codex — the headless DSS control plane
for AI agents.

It exposes one MCP code-mode tool, `dku_exec`, which runs the `dku` CLI as your
DSS user. The plugin also installs the bundled Dataiku Headless skills through
the host agent's plugin/skill mechanism; skills are intentionally not exposed as
an MCP tool.

## Install

```bash
claude plugin marketplace add dataiku/dataiku-headless
claude plugin install dataiku-mcp
```

You will be prompted for:

- DSS URL
- DSS personal API key

Prerequisite: a POSIX shell. The launcher installs [`uv`](https://docs.astral.sh/uv/)
if needed.

## Other agents

This same directory is also a Codex plugin:

```bash
codex plugin marketplace add dataiku/dataiku-headless
codex plugin install dataiku-mcp
```

Codex reads DSS connection from the environment:

```bash
export DKU_URL="https://your-dss-host"
export DKU_API_KEY="your-dss-personal-api-key"
```

**OpenCode** has no marketplace — install the CLI yourself, point
`opencode.json` at it, and install/copy the skills separately if you want the
same guidance surface as the Claude/Codex plugins (see
[`examples/opencode.json`](examples/opencode.json)):

```bash
uv tool install --from git+https://github.com/dataiku/dataiku-headless.git "dataiku-headless[mcp]"
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

## Runtime

- Tool: `dku_exec`
- Auth: `DKU_API_KEY`
- Scope: your DSS permissions and audit trail

Entry points:

- `dku-mcp`
- `python -m dku_cli.mcp`

Modes:

- `stdio`: single user, full env inheritance, current working directory
- `http`: bearer token auth, allowlisted env, per-session workdir, bubblewrap by default

In hosted mode, the real boundary is DSS API key permissions plus the sandbox
backend. `--dangerous` stripping is only a UX guard.

## Skills strategy

The Claude Code and Codex plugins install both:

- the one-tool MCP server (`dku_exec`)
- `skills/`, including `skills/dku-cli/`, as host-agent skills

That keeps the MCP surface small while still giving agents the latest DSS
guidance anywhere the plugin is installed. Direct MCP-only installs, such as the
OpenCode example above, only get `dku_exec`; pair them with a separate skill
install if the client supports skills.

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
- **auth errors** → re-check the DSS URL + key in the plugin config.

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
