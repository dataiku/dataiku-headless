# Install — Dataiku Headless

Single source of truth for installing `dku-headless` (the `dku` CLI) and its MCP server (`dku-mcp`).

**Requirements:** Python 3.10–3.13, DSS 14.5+. **CLI:** `dku` · **MCP server:** `dku-mcp`

> Install from source or git. Git installs need read access to the repo while
> it stays private.

### CLI install

[uv](https://docs.astral.sh/uv/) (recommended):
```bash
uv tool install git+https://github.com/dataiku/dku-headless.git
```

From a clone:
```bash
git clone https://github.com/dataiku/dku-headless.git
cd dku-headless
uv tool install --from . dku-headless
```

### MCP extras

Add the `[mcp]` extra for the `dku-mcp` server (required for agent-host integration):
```bash
# from git
uv tool install "dku-headless[mcp] @ git+https://github.com/dataiku/dku-headless.git"
# from a clone
uv tool install ".[mcp]"
```

### Verify

```bash
dku --help
dku-mcp --help
```

### Authentication

```bash
export DKU_URL=https://dss.example.com
export DKU_API_KEY=dkuaps-...
dku whoami                  # verify connection
```

For CI, containers, and agent harnesses, prefer `DKU_API_KEY`. For local
interactive use, `dku auth login` stores a profile credential in the OS keychain
via `keyring`; if no keychain is available, the CLI writes a mode-0600 plaintext
credentials file and warns.

Resolution order is:

1. explicit CLI flags such as `--url`, `--api-key`, `--profile`, `--format`
2. environment variables
3. the active saved profile created by `dku auth login`

### Common environment variables

Use [`.env.example`](../.env.example) as the template.

- `DKU_URL`: DSS instance URL.
- `DKU_API_KEY`: DSS API key for non-interactive use.
- `DKU_PROFILE`: select a saved profile.
- `DKU_PROJECT`: default project key for project-scoped commands.
- `DKU_FORMAT`: default output mode (`tsv`, `json`, `csv`, `ids`, `quiet`).
- `DKU_TEXT_HELP=1`: show readable help text in a terminal instead of compact JSON.
- `DKU_DANGEROUS=1`: bypass tier-2 and tier-3 confirmation guards for the current session.

Notes:

- `DKU_PROJECT` overrides the profile's saved `default_project`.
- `DKU_API_KEY` / `DKU_URL` override stored profile credentials for the current session.
- `DKU_TEXT_HELP` affects help rendering only. Non-interactive help remains compact JSON.
- Tier-4 admin safety guards are never bypassed by `DKU_DANGEROUS`.

### MCP runtime overrides

For `dku-mcp`, the main operator-set overrides are:

- `DKU_MCP_STATE_ROOT`: change where per-session MCP state is stored.
- `DKU_MCP_WORKDIR`: change the working directory used to resolve local relative paths.

### Update

```bash
cd /path/to/dku-headless
git pull
uv tool install --from . dku-headless --force --reinstall
```

`--force` alone is not enough for `uv tool install` — always pair it with `--reinstall`.
