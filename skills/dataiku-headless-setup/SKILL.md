---
name: dataiku-headless-setup
description: Set up Dataiku Headless in either local stdio mode or customer-managed Streamable HTTP mode. Use when the user asks to install, connect, configure, or repair Dataiku Headless. Choose exactly one transport, then follow its distinct authentication and verification flow.
---

# Set Up Dataiku Headless

Bring Dataiku Headless to a verified connection without mixing its two deployment modes.

## Choose the deployment mode

1. Use **customer-managed HTTP** when the user or their administrator supplied an HTTPS MCP URL, mentions SSO/OAuth, or says the service is centrally deployed. Read [references/http.md](references/http.md) and follow it.
2. Use **local stdio** when the user wants the marketplace plugin to run on their workstation with a personal Dataiku API key. Read [references/stdio.md](references/stdio.md) and follow it.
3. If the intended mode is unclear and cannot be discovered from the configured MCP servers, ask whether the organization supplied a remote MCP URL or the user wants a local personal connection.

Keep exactly one Dataiku MCP server enabled. If local stdio and remote HTTP definitions are both active, do not guess which tools to use. Ask the user to choose a mode, then disable or remove the other definition before continuing.

A setup request does not authorize installing unrelated software or changing an administrator-managed MCP definition. Obtain explicit approval immediately before running a local runtime installer.
