"""dku auth — login, logout, status, list, switch."""

from __future__ import annotations

import os

import dataikuapi
import typer

from dku_cli.auth import (
    KeyStatus,
    delete_api_key,
    get_api_key_with_status,
    infer_api_key_kind,
)
from dku_cli.brand import ICON
from dku_cli.client import AUTH_MODE_IN_POD_TICKET, get_client, resolve_auth
from dku_cli.commands._auth_login import login_impl, redact_url
from dku_cli.config import (
    clear_profile_configs,
    delete_profile_config,
    get_active_profile,
    get_all_profiles,
    get_profile_config,
    set_active_profile,
)
from dku_cli.output import (
    console,
    error,
    info,
    render,
    render_raw,
    resolve_output_format,
    success,
)

app = typer.Typer(help="Manage DSS authentication profiles.")


def _shell_squote(value: str) -> str:
    return value.replace("'", "'\\''")


def _resolve_project_source(profile: str) -> tuple[str | None, str]:
    if os.environ.get("DKU_PROJECT"):
        return os.environ["DKU_PROJECT"], "env"
    default_project = get_profile_config(profile).get("default_project")
    if default_project:
        return default_project, f"profile:{profile}"
    return None, "missing"


def _resolve_auth_sources(
    flag_url: str | None,
    flag_api_key: str | None,
    resolved_url: str,
    resolved_key: str,
    profile: str,
) -> tuple[str, str]:
    profile_cfg = get_profile_config(profile)

    if flag_url:
        url_source = "flag"
    elif os.environ.get("DKU_URL"):
        url_source = "env"
    elif profile_cfg.get("url") and resolved_url:
        url_source = f"profile:{profile}"
    else:
        url_source = "unknown"

    if flag_api_key:
        api_key_source = "flag"
    elif os.environ.get("DKU_API_KEY"):
        api_key_source = "env"
    elif resolved_key:
        api_key_source = f"profile:{profile}"
    else:
        api_key_source = "missing"

    return url_source, api_key_source


@app.command()
def login(
    profile: str = typer.Option("default", "--profile", "-p", help="Profile name"),
    url: str = typer.Option(None, "--url", help="DSS instance URL"),
    api_key: str = typer.Option(
        None,
        "--api-key",
        help=(
            "DSS API key (omit for prompt). Supported formats: Personal "
            "(dkuaps-...), Global (32-char alphanumeric), Deployer (dkuapdp-...), "
            "Automation (dkuapau-...), API-node (dkuapan-...). All are accepted."
        ),
    ),
) -> None:
    """Authenticate with a DSS instance.

    Accepts any DSS API key format — Personal, Global, Deployer, Automation,
    or API-node. The detected kind is shown after a successful login.
    """
    login_impl(profile, url, api_key)


@app.command()
def logout(
    profile: str = typer.Option(None, "--profile", "-p", help="Profile to remove"),
    all_profiles: bool = typer.Option(False, "--all", help="Remove all profiles"),
) -> None:
    """Remove stored credentials."""
    if all_profiles:
        profiles = get_all_profiles()
        for name in profiles:
            delete_api_key(name)
        removed = clear_profile_configs()
        success(f"Removed {removed} profile(s)")
        return

    target = profile or get_active_profile()
    deleted_key = delete_api_key(target)
    deleted_profile = delete_profile_config(target)

    if deleted_key or deleted_profile:
        success(f'Removed credentials for "{target}"')
    else:
        info(f'No credentials found for "{target}"')


@app.command()
def status(
    ctx: typer.Context,
) -> None:
    """Show current authentication status."""
    fmt = resolve_output_format()
    opts = ctx.obj or {}
    profile = opts.get("profile") or get_active_profile()
    flag_url = opts.get("url")
    flag_api_key = opts.get("api_key")

    # Ticket-mode profiles take a separate path: no stored URL/key, the client
    # is wired through DKU_API_TICKET + DKU_BACKEND_HOST/PORT injected by DSS.
    profile_cfg = get_profile_config(profile)
    is_ticket_mode = (
        not flag_url
        and not flag_api_key
        and profile_cfg.get("auth_mode") == AUTH_MODE_IN_POD_TICKET
    )

    if is_ticket_mode:
        try:
            client = get_client(profile=profile)
        except Exception as e:
            if fmt == "json":
                render_raw(
                    {
                        "profile": profile,
                        "status": "not_configured",
                        "error": str(e),
                    },
                    output_format=fmt,
                )
            else:
                error(f'Profile "{profile}" (in-pod ticket) cannot resolve auth.')
                error(str(e))
            raise typer.Exit(1)
        host = os.environ.get("DKU_BACKEND_HOST", "?")
        port = os.environ.get("DKU_BACKEND_PORT", "?")
        proto = os.environ.get("DKU_BACKEND_PROTOCOL", "http")
        url = f"{proto}://{host}:{port}"
        api_key = "<in-pod-ticket>"
        url_source = "DKU_BACKEND_HOST/PORT (in-pod)"
        api_key_source = "DKU_API_TICKET (in-pod)"
        project_key, project_source = _resolve_project_source(profile)
    else:
        try:
            url, api_key = resolve_auth(
                url=flag_url, api_key=flag_api_key, profile=profile
            )
        except Exception:
            if fmt == "json":
                render_raw(
                    {
                        "profile": profile,
                        "status": "not_configured",
                        "error": "Profile is not fully configured",
                    },
                    output_format=fmt,
                )
            else:
                error(f'Profile "{profile}" is not fully configured.')
                error("Run 'dku auth login' to set up.")
            raise typer.Exit(1)

        url_source, api_key_source = _resolve_auth_sources(
            flag_url, flag_api_key, url, api_key, profile
        )
        project_key, project_source = _resolve_project_source(profile)

    try:
        if not is_ticket_mode:
            client = dataikuapi.DSSClient(url, api_key=api_key)
        auth_info = client.get_auth_info()
        user = auth_info.get("authIdentifier", "unknown")
        groups = auth_info.get("groups", [])
        try:
            instance = client.get_instance_info().raw
            version = instance.get("dssVersion", "unknown")
            node_type = instance.get("nodeType", "unknown")
        except Exception:
            version = "unknown"
            node_type = "unknown"

        project_ok: bool | None = None
        project_error: str | None = None
        if project_key:
            try:
                client.get_project(project_key).get_metadata()
                project_ok = True
            except Exception as exc:
                project_ok = False
                project_error = str(exc)

        api_key_kind = infer_api_key_kind(api_key)
        if fmt == "json":
            render_raw(
                {
                    "profile": profile,
                    "url": url,
                    "url_source": url_source,
                    "api_key_source": api_key_source,
                    "api_key_kind": api_key_kind,
                    "user": user,
                    "groups": groups,
                    "dss_version": version,
                    "node_type": node_type,
                    "project": project_key,
                    "project_source": project_source,
                    "project_ok": project_ok,
                    "project_error": project_error,
                    "status": "connected",
                },
                output_format=fmt,
            )
            return

        console.print(f"[bold]Profile:[/bold]  {profile}")
        console.print(f"[bold]URL:[/bold]      {redact_url(url)}")
        console.print(f"[bold]URL Src:[/bold]  {url_source}")
        console.print(f"[bold]Key Src:[/bold]  {api_key_source}")
        console.print(f"[bold]Key Kind:[/bold] {api_key_kind}")
        console.print(f"[bold]User:[/bold]     {user}")
        if groups:
            console.print(f"[bold]Groups:[/bold]   {', '.join(groups)}")
        console.print(f"[bold]DSS:[/bold]      {version} ({node_type})")
        if project_key:
            console.print(
                f"Project:  {project_key} [{project_source}]",
                markup=False,
            )
            if project_ok:
                console.print(
                    f"[bold]Project OK:[/bold] [green]{ICON} Accessible[/green]"
                )
            else:
                console.print(
                    f"[bold]Project OK:[/bold] [red]{ICON} Error: {project_error}[/red]"
                )
        else:
            console.print("[bold]Project:[/bold]  none configured")
        console.print(f"[bold]Status:[/bold]   [green]{ICON} Connected[/green]")
    except Exception as e:
        if fmt == "json":
            render_raw(
                {
                    "profile": profile,
                    "url": url,
                    "status": "error",
                    "error": str(e),
                },
                output_format=fmt,
            )
        else:
            console.print(f"[bold]Profile:[/bold]  {profile}")
            console.print(f"[bold]URL:[/bold]      {redact_url(url)}")
            console.print(f"[bold]Status:[/bold]   [red]{ICON} Error: {e}[/red]")
        raise typer.Exit(1)


@app.command("export-env")
def export_env(
    ctx: typer.Context,
) -> None:
    """Emit shell `export` lines for DKU_URL / DKU_API_KEY.

    For external scripts that use `dataikuapi` directly (not the `dku` CLI):

        eval "$(dku auth export-env --profile X)"

    Then `dataikuapi.DSSClient()` picks up the environment. Use `--format json`
    to capture both values as an object for non-shell consumers.
    """
    fmt = resolve_output_format()
    opts = ctx.obj or {}
    profile = opts.get("profile") or get_active_profile()
    flag_url = opts.get("url")
    flag_api_key = opts.get("api_key")

    profile_cfg = get_profile_config(profile)
    if (
        not flag_url
        and not flag_api_key
        and profile_cfg.get("auth_mode") == AUTH_MODE_IN_POD_TICKET
    ):
        error(
            f'Profile "{profile}" uses in-pod ticket auth — no static API key to '
            "export."
        )
        error(f"Run dataikuapi scripts with: dku ... --profile {profile}")
        raise typer.Exit(1)

    try:
        url, api_key = resolve_auth(url=flag_url, api_key=flag_api_key, profile=profile)
    except Exception:
        error(f'Profile "{profile}" is not fully configured.')
        error("Run 'dku auth login' to set up.")
        raise typer.Exit(1)

    if fmt == "json":
        render_raw({"DKU_URL": url, "DKU_API_KEY": api_key}, output_format="json")
        return

    print(f"export DKU_URL='{_shell_squote(url)}'")
    print(f"export DKU_API_KEY='{_shell_squote(api_key)}'")


@app.command("list")
def list_profiles() -> None:
    """List all configured profiles.

    JSON output round-trips every persisted profile field (name, url,
    node_type, default_project, active flag, has_key) so callers can pipe
    through `jq` without needing a second `auth status` call.
    """
    output_fmt = resolve_output_format()
    profiles = get_all_profiles()
    active = get_active_profile()

    if not profiles:
        if output_fmt == "json":
            render_raw([], output_format="json")
        else:
            info("No profiles configured. Run 'dku auth login' to get started.")
        return

    rows = []
    key_results = {}  # name -> KeyResult, for the rich text-output labels
    for name, cfg in profiles.items():
        auth_mode = cfg.get("auth_mode") or "api_key"
        key_result = get_api_key_with_status(name)
        key_results[name] = key_result
        rows.append(
            {
                "name": name,
                "active": name == active,
                "node_type": cfg.get("node_type", "?"),
                "url": cfg.get("url", ""),
                "default_project": cfg.get("default_project", ""),
                "auth_mode": auth_mode,
                "has_key": key_result.status == KeyStatus.OK,
            }
        )

    if output_fmt == "json":
        render_raw(rows, output_format="json")
        return

    if output_fmt == "csv":
        render(
            rows,
            [
                "name",
                "active",
                "node_type",
                "url",
                "default_project",
                "auth_mode",
                "has_key",
            ],
            output_format="csv",
        )
        return

    # Default: human-friendly text matching the historical layout
    for row in rows:
        marker = " *" if row["active"] else ""
        key_result = key_results[row["name"]]
        if row["auth_mode"] == AUTH_MODE_IN_POD_TICKET:
            auth_label = "in-pod ticket"
        elif key_result.status == KeyStatus.OK:
            auth_label = "key stored"
        elif key_result.status == KeyStatus.DENIED:
            # Don't say "no key" — the entry is likely still there. Tell the
            # user the truth so they don't waste time re-running `auth login`.
            auth_label = (
                "keychain access denied (entry may exist; re-prompt may be required)"
            )
        elif key_result.status == KeyStatus.BACKEND_ERROR:
            auth_label = f"keychain error ({key_result.detail or ''})"
        else:
            auth_label = "no key"
        url = row["url"] or (
            "in-pod backend"
            if row["auth_mode"] == AUTH_MODE_IN_POD_TICKET
            else "no url"
        )
        console.print(
            f"  {row['name']}{marker}  [{row['node_type']}]  {url}  ({auth_label})"
        )


@app.command()
def switch(
    profile: str = typer.Argument(help="Profile to switch to"),
) -> None:
    """Switch active profile."""
    profiles = get_all_profiles()
    if profile not in profiles:
        error(f'Profile "{profile}" does not exist.')
        error(f"Available: {', '.join(profiles.keys())}")
        raise typer.Exit(1)

    set_active_profile(profile)
    success(f'Switched to profile "{profile}"')
