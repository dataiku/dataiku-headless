"""dku config — get, set, list, path, variables, set-variables."""

from __future__ import annotations

from typing import List, Optional

import typer

from dku_cli.config import (
    CONFIG_FILE,
    get_config,
    get_default_project,
    set_dangerous_mode,
    set_default_project,
)
from dku_cli.output import error, info, render, render_raw, success

app = typer.Typer(help="Manage CLI configuration.")

# Keys that can be set via 'dku config set'
_SETTABLE_KEYS = {"default_project"}


@app.command("set")
def set_value(
    key: str = typer.Argument(help="Config key (default_project)"),
    value: str = typer.Argument(help="Config value"),
) -> None:
    """Set a configuration value."""
    if key not in _SETTABLE_KEYS:
        error(f"Unknown key: {key}. Valid keys: {', '.join(sorted(_SETTABLE_KEYS))}")
        raise typer.Exit(1)

    set_default_project(value)
    success(f"Set {key} = {value}")


@app.command("get")
def get_value(
    key: str = typer.Argument(help="Config key"),
) -> None:
    """Get a configuration value."""
    if key == "default_project":
        val = get_default_project()
    else:
        error(f"Unknown key: {key}. Valid keys: {', '.join(sorted(_SETTABLE_KEYS))}")
        raise typer.Exit(1)

    if val:
        print(val)
    else:
        info(f"{key} is not set")


@app.command("list")
def list_config() -> None:
    """Show all configuration."""
    cfg = get_config()
    if not cfg:
        info("No configuration set. Run 'dku config set' or 'dku auth login'.")
        return

    data = []
    for section, values in cfg.items():
        if isinstance(values, dict):
            for k, v in values.items():
                data.append({"section": section, "key": k, "value": str(v)})
        else:
            data.append({"section": "(root)", "key": section, "value": str(values)})

    render(
        data,
        ["section", "key", "value"],
        title="Configuration",
    )


@app.command("path")
def show_path() -> None:
    """Print config file path."""
    print(CONFIG_FILE)


@app.command("list-profiles")
def list_profiles_alias() -> None:
    """List configured auth profiles (alias for `dku auth list`).

    Profiles are stored in the auth section of `config.toml`, so the
    canonical command lives under `dku auth`. This alias closes the
    discoverability gap — agents who reach for `dku config list-profiles`
    naturally now land on the right output instead of a "did you mean
    'set-variables'" suggestion that helps no one.
    """
    from dku_cli.commands.auth_cmd import list_profiles as _auth_list_profiles

    _auth_list_profiles()


@app.command("set-safety")
def set_safety(
    mode: str = typer.Argument(help="Safety mode: guarded or dangerous"),
) -> None:
    """Persist the safety mode to config.toml.

    - guarded: destructive commands require --yes (default).
    - dangerous: skip safety guards for tier 2–3 commands (tier 4 admin never
      bypassable). Equivalent to setting DKU_DANGEROUS=1 persistently.
    """
    mode_lower = mode.strip().lower()
    if mode_lower not in ("guarded", "dangerous"):
        error("Safety mode must be 'guarded' or 'dangerous'.")
        raise typer.Exit(1)
    set_dangerous_mode(mode_lower == "dangerous")
    success(f"Set safety mode = {mode_lower}")


@app.command("get-safety")
def get_safety(ctx: typer.Context) -> None:
    """Show the active safety mode and why it is active.

    Precedence: --dangerous flag > DKU_DANGEROUS env > config.toml > default (guarded).
    """
    from dku_cli.safety import is_dangerous_mode

    enabled, reason = is_dangerous_mode(ctx)
    mode = "dangerous" if enabled else "guarded"
    reason_map = {
        "flag": "--dangerous flag",
        "env": "DKU_DANGEROUS env var",
        "config": "config.toml (dangerous_mode=true)",
        "default": "default (guarded is the default mode)",
    }
    print(mode)
    info(f"reason: {reason_map.get(reason, reason)}")


@app.command("variables")
def variables(
    ctx: typer.Context,
) -> None:
    """Show instance-level variables."""
    from dku_cli.errors import handle_api_error
    from dku_cli.helpers import get_client_from_ctx

    try:
        client = get_client_from_ctx(ctx)
        vars_data = client.get_variables()
        render_raw(vars_data)
    except Exception as e:
        handle_api_error(e)


@app.command("set-variables")
def set_variables(
    ctx: typer.Context,
    set_var: Optional[List[str]] = typer.Option(
        None, "--set", help="Set standard variable (key=value)"
    ),
) -> None:
    """Set instance-level standard variables."""
    from dku_cli.errors import handle_api_error
    from dku_cli.helpers import get_client_from_ctx

    if not set_var:
        error("Provide --set key=value.")
        raise typer.Exit(1)

    try:
        client = get_client_from_ctx(ctx)
        current = client.get_variables()
        standard = current.get("standard", {})
        for item in set_var:
            if "=" not in item:
                error(f"Invalid format: {item}. Use key=value.")
                raise typer.Exit(1)
            k, v = item.split("=", 1)
            standard[k] = v
        current["standard"] = standard
        client.set_variables(current)
        success("Updated instance variables")
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)
