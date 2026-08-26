---
name: dataiku-headless-setup
description: Set up Dataiku Headless after plugin installation. Use when the user asks to install, set up, connect, configure, or repair Dataiku Headless; when its MCP tools are unavailable; or when uv may be missing. Check the runtime, offer the official platform installer with explicit approval, warm the runtime, then configure and verify a Dataiku instance.
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
5. Once uv is suitable, warm the runtime before the host first launches the server. The host gives up on an MCP server that is still downloading dependencies on its first launch, which is the most common cause of a plugin that never becomes available. Run the server once so it exits immediately on end of input. The script is `../../bin/run_mcp.py` relative to this skill file; resolve it in the plugin root before running.
   - macOS or Linux: `uv run --quiet --locked --script bin/run_mcp.py < /dev/null`
   - Windows PowerShell: `$null | uv run --quiet --locked --script bin\run_mcp.py`

   The command prints a startup line on stderr and exits with status 0 once the runtime is cached; that is success, not a failure. Do not substitute `uv sync --locked --script`: it caches the downloads but leaves the environment to be created on first launch, so the host still sees a slow first start.
6. Check whether the Dataiku MCP tools are available. If they are not, reload the plugin or restart the agent once before diagnosing a Dataiku connection problem.
7. When the MCP tools are available, run `list_instances`. If no instance is configured, run `configure_instance` and have the user complete the local setup page. If multiple instances exist without an active one, ask which to use and run `switch_instance`.
8. Verify the active profile with `get_current_instance`, then make a lightweight read-only Dataiku call such as `list_projects` to validate the saved connection. Never request or repeat the API key in chat.

Report completion with the uv version, active instance name and URL, Dataiku version when available, and whether the Dataiku read succeeded. If a restart is required, say that setup is incomplete and give the single next action.
