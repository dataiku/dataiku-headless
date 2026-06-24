# Install — Dataiku Headless

Single source of truth for installing `dku-headless` (the `dku` CLI) and its MCP server (`dku-mcp`).

**Requirements:** Python 3.10–3.13, DSS 14.5+. **CLI:** `dku` · **MCP server:** `dku-mcp`

> Not yet published to PyPI — install from source or git. (Git installs need
> read access to the repo while it stays private.)

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
uv tool install --from . "dku-headless[mcp]"
```

### Verify

```bash
dku --help
dku-mcp --help
```

### Authentication

```bash
dku auth login              # interactive: DSS URL + API key
dku whoami                  # verify connection
```

Credentials are stored in the OS keychain via `keyring`, with a file fallback.

### Update

```bash
cd /path/to/dku-headless
git pull
uv tool install --from . dku-headless --force --reinstall
```

`--force` alone is not enough for `uv tool install` — always pair it with `--reinstall`.
