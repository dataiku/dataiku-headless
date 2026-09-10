# Local stdio setup

Use this workflow only for the local `dataiku-headless` plugin. It starts the MCP server on the user's workstation and authenticates to Dataiku with a personal API key.

1. Run `uv --version` when local commands are available. Dataiku Headless requires uv 0.12.0 or later.
2. If uv is missing or too old, explain that it supplies the isolated Python runtime and pinned dependencies used by the local MCP server. Detect the operating system and offer the matching official Astral installer:
   - macOS or Linux: `curl -LsSf https://astral.sh/uv/install.sh | sh`
   - Windows PowerShell: `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`
3. Obtain explicit approval, run only the selected installer, and verify with `uv --version`. Do not substitute a third-party package manager or edit shell startup files unless the user asks.
4. If the current process cannot see the newly installed executable, confirm the installer's reported location, then ask the user to restart or reload the agent. Resume setup in the new session.
5. Warm the runtime once with stdin closed. Locate this setup skill's plugin root as the ancestor containing both `skills/` and `runtime/`; do not assume the working directory is the plugin root.
   - macOS or Linux: `uv run --quiet --locked --script "<plugin_root>/runtime/run_mcp.py" --transport stdio < /dev/null`
   - Windows PowerShell: `$null | uv run --quiet --locked --script "<plugin_root>\runtime\run_mcp.py" --transport stdio`

   A startup line on stderr followed by exit status 0 is expected. Do not substitute `uv sync --locked --script`.
6. Check whether the Dataiku MCP tools are available. If not, reload the plugin or restart the agent once before diagnosing a Dataiku connection problem.
7. Run `list_instances`. If no instance is configured, run `configure_instance` and have the user complete the local setup page. If multiple instances exist without an active one, ask which to use and run `switch_instance`.
8. Run `get_current_instance`. If its connection failed, use `configure_instance` to replace or add a working profile. When connected, call `list_projects` as a lightweight read-only access check. Never request or repeat the API key in chat.

Report the uv version, active instance name and URL, Dataiku version when available, and whether the read check succeeded. If a restart is required, report setup as incomplete and give the single next action.
