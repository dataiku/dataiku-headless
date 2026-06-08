# dataiku-mcp-bundle

Claude Desktop `.mcpb` packaging for the same local MCP.

## Install (end user)

1. Download `dataiku-mcp.mcpb` (from the GitHub release).
2. In Claude Desktop: **Settings → Extensions → Install**, pick the file.
3. Enter your DSS URL and DSS personal API key.

## How it works

The bundle reuses:

- `../dataiku-mcp/bin`
- `../dataiku-mcp/wheels`

## Build (maintainer)

```bash
make plugin
make desktop-bundle
```

The bundle is a release artifact. Do not commit `dist/dataiku-mcp.mcpb`.
