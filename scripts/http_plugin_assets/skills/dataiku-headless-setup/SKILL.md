---
name: dataiku-headless-setup
description: Set up the organization-managed Dataiku Headless Streamable HTTP connection. Use when the user asks to install, connect, configure, or repair Dataiku Headless. Verify the remote MCP connection, complete OAuth when needed, then select and verify a Dataiku instance.
---

# Set Up Dataiku Headless

Use this workflow for the customer-managed Dataiku Headless Streamable HTTP service bundled with this plugin. The workstation does not run the server.

## Authenticate and verify access

1. Check whether the Dataiku MCP tools are available. If they are, run `list_instances`.
2. If the tools are unavailable, or `list_instances` reports that authentication is required, explain that the remote server needs OAuth login and ask whether the user wants to authenticate now.
3. Only after the user agrees, run the matching client command:
   - Codex: `codex mcp login dataiku`
   - Claude Code: `claude mcp login dataiku`
4. Have the user complete the browser-based sign-in. Reload or restart the client if the tools do not reconnect, then retry `list_instances`.
5. HTTP catalogs are administrator-managed. If no instance is active, ask the user which listed instance to use and call `switch_instance`. Never call `configure_instance` or `delete_instance`.
6. Call `get_current_instance` to verify delegated Dataiku access and capture the Dataiku version when available.
7. Call `list_projects` as a lightweight read-only permission check.

Report the active instance name and URL, Dataiku version when available, and whether the read check succeeded. For an OAuth, token-exchange, or Dataiku identity-mapping failure, report the stage and direct the user to the Dataiku Headless administrator without requesting credentials.
