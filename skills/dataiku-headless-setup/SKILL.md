---
name: dataiku-headless-setup
description: Set up Dataiku Headless after plugin installation. Use when the user asks to install, set up, connect, configure, or repair Dataiku Headless; when its MCP tools are unavailable; or when uv may be missing. Check the runtime, offer the official platform installer with explicit approval, then configure and verify a Dataiku instance.
---

# Set Up Dataiku Headless

Bring a new or broken plugin installation to a verified Dataiku connection. A request to set up Dataiku Headless is not approval to install software: obtain explicit approval immediately before running an installer.

## Workflow

1. First run `list_instances`. If it succeeds, the local plugin and runtime are already available; skip directly to instance configuration and verification below (step 8).
2. If the Dataiku MCP tools are unavailable, check the runtime. Run `uv --version` when local commands are available; ask the user to run it only when they are not. Dataiku Headless requires uv 0.12.0 or later.
3. If uv is missing or too old, explain briefly that it supplies the isolated Python runtime and pinned dependencies used by the local MCP server. Detect the operating system and offer the matching official Astral installer:
   - macOS or Linux: `curl -LsSf https://astral.sh/uv/install.sh | sh`
   - Windows PowerShell: `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`
4. Obtain explicit approval, run only the selected installer, and verify with `uv --version`. Do not substitute a third-party package manager or edit shell startup files unless the user asks.
5. If the current agent process cannot see the newly installed executable, use the installer's reported location to confirm it exists, then ask the user to fully restart or reload the agent. Stop and resume setup in the new session; the already-running MCP process cannot repair its own launch environment.
6. Once uv is suitable, warm the runtime by running the server once with stdin closed. Locate the absolute path of this `SKILL.md`; the plugin root is its ancestor containing both `skills/` and `runtime/` (this file is at `<plugin_root>/skills/dataiku-headless-setup/SKILL.md`). Do not assume the current working directory is the plugin root.
   - macOS or Linux: `uv run --quiet --locked --script "<plugin_root>/runtime/run_mcp.py" --transport stdio < /dev/null`
   - Windows PowerShell: `$null | uv run --quiet --locked --script "<plugin_root>\runtime\run_mcp.py" --transport stdio`

   A startup line on stderr followed by exit status 0 is expected. This checks standalone runtime startup, not the agent's MCP registration or connection. Do not substitute `uv sync --locked --script`: it caches downloads but leaves environment creation for the first server launch.
7. Retry `list_instances`. If the tools are still unavailable, reload the plugin or restart the agent once, then retry. If they are still missing, inspect the agent's MCP registration and startup error; do not repeat the warm-up/restart loop. Check the executable, script path, working directory, and any organization policy error before diagnosing a Dataiku connection problem.
8. When `list_instances` succeeds, if no instance is configured, run `configure_instance` and have the user add an instance in the local browser manager, test it when supported, save it, and select **Done**. Design and Automation require a successful connection test. Agent Management, Govern and Deployer testing is unavailable; save their locally validated profiles directly. Select **Switch to this instance after saving** to make it active. The manager stays open across operations; saving alone does not complete URL elicitation. If multiple instances exist without an active one, ask which to use and run `switch_instance`.
9. Verify the active profile with `get_current_instance`. If its `connection_status` is `failed`, the discovered profile cannot connect to Dataiku; run `configure_instance` to edit or add a working instance profile instead of treating it as set up. If it is `unsupported`, the Agent Management, Govern or Deployer profile is configured but its API tools are not implemented; explain this and offer to switch to a supported instance instead of repeating setup or probing DSS. When it is `connected`, make a lightweight read-only Dataiku call such as `list_projects` to validate the available Dataiku access. Never request or repeat the API key in chat.

Report completion with the active instance name, URL, and configured type, Dataiku version when available, and whether the Dataiku read succeeded or the selected node type has no API tools yet. Include the uv version only when runtime recovery was needed. If a restart is required, say that setup is incomplete and give the single next action.

## HTTPS certificate trust

The standard launcher trusts CAs in the operating system certificate store. For
corporate HTTPS instances, keep **Skip certificate verification** unchecked. If
verification fails, check that the internal root CA is trusted on the machine or
container running the MCP server. Do not default to disabling verification.
Previously saved profiles with verification disabled must be edited, retested,
and saved with verification enabled.

## Manage existing instances

Use `configure_instance` to reopen the local instance manager. It groups instances
by type and supports create, edit, delete, **Use now**, and **Set default**. **Use now**
changes the target of later tool calls; **Set default** selects the saved startup
profile and does not switch the active instance. Environment and Code Studio
instances remain read-only and take precedence at startup. HTTP instances remain
platform-managed and cannot use this local manager.

When editing, leave the API key blank to preserve the saved key or ticket. A new
API key replaces the credential. For Design and Automation, a successful connection test is required before
saving; changing URL, credential, certificate policy, or type requires a new test.
Deleting an active/default profile requires choosing another saved profile when
one is available. It removes only the saved instance configuration. The Dataiku
instance and its data stay in place.
After **Done**, verify the active instance with `get_current_instance`; never
infer activation from saving or choosing a default. Changes are applied immediately
and survive page expiry. The manager expires after ten minutes; reopen it if needed.
