---
name: dataiku-headless-setup
description: Set up Dataiku Headless after plugin installation. Use when the user asks to install, set up, connect, configure, or repair Dataiku Headless; when its MCP tools are unavailable; or when uv may be missing. Check the runtime, offer the official platform installer with explicit approval, then configure and verify a Dataiku instance.
---

# Set Up Dataiku Headless

Bring a new or broken plugin installation to a verified Dataiku connection. A request to set up Dataiku Headless is not approval to install software: obtain explicit approval immediately before running an installer.

## Workflow

1. Check the runtime first. Run `uv --version` when local commands are available; ask the user to run it only when they are not. Dataiku Headless requires uv 0.12.0 or later.
2. If uv is missing or too old, explain briefly that it supplies the isolated Python runtime and pinned dependencies used by the local MCP server. Detect the operating system and offer the matching official Astral installer:
   - macOS or Linux: `curl -LsSf https://astral.sh/uv/install.sh | sh`
   - Windows PowerShell: `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`
3. Obtain explicit approval, run only the selected installer, and verify with `uv --version`. Do not substitute a third-party package manager or edit shell startup files unless the user asks.
4. If the current agent process cannot see the newly installed executable, use the installer's reported location to confirm it exists, then ask the user to fully restart or reload the agent. Stop and resume setup in the new session; the already-running MCP process cannot repair its own launch environment.
5. Once uv is suitable, warm the runtime by running the server once with stdin closed. Locate the absolute path of this `SKILL.md`; the plugin root is its ancestor containing both `skills/` and `runtime/` (this file is at `<plugin_root>/skills/dataiku-headless-setup/SKILL.md`). Do not assume the current working directory is the plugin root.
   - macOS or Linux: `uv run --quiet --locked --script "<plugin_root>/runtime/run_mcp.py" --transport stdio < /dev/null`
   - Windows PowerShell: `$null | uv run --quiet --locked --script "<plugin_root>\runtime\run_mcp.py" --transport stdio`

   A startup line on stderr followed by exit status 0 is expected. Do not substitute `uv sync --locked --script`: it caches downloads but leaves environment creation for the first server launch.
6. Check whether the Dataiku MCP tools are available. If they are not, reload the plugin or restart the agent once before diagnosing a Dataiku connection problem.
7. When the MCP tools are available, run `list_instances`. If no instance is configured, run `configure_instance` and have the user complete the local setup page. If multiple instances exist without an active one, ask which to use and run `switch_instance`.
8. Verify the active profile with `get_current_instance`. If its `connection_status` is `failed`, the discovered profile cannot connect to Dataiku; run `configure_instance` to replace or add a working profile instead of treating it as set up. When it is `connected`, make a lightweight read-only Dataiku call such as `list_projects` to validate the available Dataiku access. Never request or repeat the API key in chat.

Report completion with the uv version, active instance name and URL, Dataiku version when available, and whether the Dataiku read succeeded. If a restart is required, say that setup is incomplete and give the single next action.
