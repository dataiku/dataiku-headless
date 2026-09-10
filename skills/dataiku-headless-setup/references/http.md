# Customer-managed HTTP setup

Use this workflow for a Dataiku Headless Streamable HTTP service deployed and administered by the user's organization. The workstation does not run the server and needs neither uv nor a Dataiku API key.

## Connection ownership

- For interactive OAuth on a plugin-capable client, prefer the customer-specific Dataiku Headless plugin distributed through the organization's Codex or Claude marketplace. It bundles the remote MCP definition and skills.
- Use a centrally managed MCP definition plus separately distributed skills for direct bearer deployments, clients without plugin support, or organizations that cannot distribute plugins.
- Otherwise, use the exact HTTPS MCP URL supplied by the user or their administrator. Do not invent or discover a customer endpoint.
- Keep exactly one Dataiku MCP definition enabled. Disable the public stdio plugin before enabling the customer-specific remote plugin.
- Authentication belongs to the MCP client. Never request an OAuth client secret, bearer token, or Dataiku API key in chat.

## Connect an unmanaged client

Use the client's native configuration only when the organization has not already installed a managed definition.

Codex:

```bash
codex mcp add dataiku --url https://mcp.customer.example/mcp
codex mcp login dataiku
```

Claude Code:

```bash
claude mcp add --scope user --transport http dataiku https://mcp.customer.example/mcp
claude mcp login dataiku
```

Replace the example URL only with the administrator-provided endpoint. If the client reports that `dataiku` already exists, inspect the existing definition rather than adding a second server. A command that changes user configuration is allowed only when the user asked to connect this client; do not replace managed configuration.

After adding or changing the definition, restart or reload the client if its tools do not appear. For interactive OAuth, complete browser-based SSO through the client's OAuth flow. For direct bearer authentication, rely on the administrator-provided client configuration; never ask the user to paste a token into chat.

## Verify access

1. Run `list_instances`. HTTP catalogs are administrator-managed; never call `configure_instance` or `delete_instance`.
2. If no instance is active, ask the user which listed instance to use and call `switch_instance`.
3. Call `get_current_instance` to verify delegated Dataiku access and capture the Dataiku version when available.
4. Call `list_projects` as a lightweight read-only permission check.

Report the active instance name and URL, Dataiku version when available, and whether the read check succeeded. For an OAuth, token-exchange, or Dataiku identity-mapping failure, report the stage and direct the user to their Dataiku Headless administrator without requesting tokens.
