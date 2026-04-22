"""dku auth — login, logout, status, list, switch."""

from __future__ import annotations

import os
from urllib.parse import urlsplit, urlunsplit

import dataikuapi
import typer
from rich.prompt import Prompt

from dku_cli.auth import delete_api_key, get_api_key, store_api_key
from dku_cli.brand import ICON, print_logo, welcome
from dku_cli.client import resolve_auth
from dku_cli.config import (
    clear_profile_configs,
    delete_profile_config,
    get_active_profile,
    get_default_project,
    get_all_profiles,
    get_profile_config,
    set_active_profile,
    set_default_project,
    set_profile_config,
)
from dku_cli.output import console, error, info, success

app = typer.Typer(help="Manage DSS authentication profiles.")


def _redact_url(url: str) -> str:
    parts = urlsplit(url)
    hostname = parts.hostname or ""
    netloc = hostname
    if parts.port:
        netloc = f"{hostname}:{parts.port}"
    return urlunsplit((parts.scheme, netloc, "", "", ""))


def _resolve_project_source() -> tuple[str | None, str]:
    if os.environ.get("DKU_PROJECT"):
        return os.environ["DKU_PROJECT"], "env"
    default_project = get_default_project()
    if default_project:
        return default_project, f"profile:{get_active_profile()}"
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
    api_key: str = typer.Option(None, "--api-key", help="API key (omit for prompt)"),
) -> None:
    """Authenticate with a DSS instance."""
    interactive = not api_key

    if interactive:
        print_logo(subtitle=f"dku auth login  —  profile: {profile}")

    if not url:
        url = Prompt.ask("DSS URL")
    url = url.rstrip("/")

    if not api_key:
        api_key = Prompt.ask("API Key", password=True)

    # Validate connection
    try:
        import dataikuapi

        client = dataikuapi.DSSClient(url, api_key=api_key)
        auth_info = client.get_auth_info()
        user = auth_info.get("authIdentifier", "unknown")
    except Exception as e:
        error(f"Could not connect to {url}: {e}")
        raise typer.Exit(1)

    # Get DSS version
    try:
        version = client.get_instance_info().raw.get("dssVersion", "unknown")
    except Exception:
        version = "unknown"

    # Store credentials
    set_profile_config(profile, url)
    storage = store_api_key(profile, api_key)

    success(welcome(user, url, version))
    info(f"Credentials stored in {storage}")
    if profile != "default":
        info(f'Profile "{profile}" is now active')

    # Prompt for default project in interactive mode
    if interactive:
        try:
            project_key = Prompt.ask(
                "Default project? (leave blank to skip)", default=""
            )
            if project_key.strip():
                set_default_project(project_key.strip())
                info(f"Default project set to {project_key.strip()}")
        except (EOFError, KeyboardInterrupt):
            pass


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
def status(ctx: typer.Context) -> None:
    """Show current authentication status."""
    opts = ctx.obj or {}
    profile = opts.get("profile") or get_active_profile()
    flag_url = opts.get("url")
    flag_api_key = opts.get("api_key")

    try:
        url, api_key = resolve_auth(url=flag_url, api_key=flag_api_key, profile=profile)
    except Exception:
        error(f'Profile "{profile}" is not fully configured.')
        error("Run 'dku auth login' to set up.")
        raise typer.Exit(1)

    url_source, api_key_source = _resolve_auth_sources(
        flag_url, flag_api_key, url, api_key, profile
    )
    project_key, project_source = _resolve_project_source()

    try:
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

        console.print(f"[bold]Profile:[/bold]  {profile}")
        console.print(f"[bold]URL:[/bold]      {_redact_url(url)}")
        console.print(f"[bold]URL Src:[/bold]  {url_source}")
        console.print(f"[bold]Key Src:[/bold]  {api_key_source}")
        console.print(f"[bold]User:[/bold]     {user}")
        if groups:
            console.print(f"[bold]Groups:[/bold]   {', '.join(groups)}")
        console.print(f"[bold]DSS:[/bold]      {version} ({node_type})")
        if project_key:
            console.print(f"[bold]Project:[/bold]  {project_key} [{project_source}]")
            try:
                client.get_project(project_key).get_metadata()
                console.print(
                    f"[bold]Project OK:[/bold] [green]{ICON} Accessible[/green]"
                )
            except Exception as exc:
                console.print(
                    f"[bold]Project OK:[/bold] [red]{ICON} Error: {exc}[/red]"
                )
        else:
            console.print("[bold]Project:[/bold]  none configured")
        console.print(f"[bold]Status:[/bold]   [green]{ICON} Connected[/green]")
    except Exception as e:
        console.print(f"[bold]Profile:[/bold]  {profile}")
        console.print(f"[bold]URL:[/bold]      {_redact_url(url)}")
        console.print(f"[bold]Status:[/bold]   [red]{ICON} Error: {e}[/red]")
        raise typer.Exit(1)


@app.command("list")
def list_profiles() -> None:
    """List all configured profiles."""
    profiles = get_all_profiles()
    active = get_active_profile()

    if not profiles:
        info("No profiles configured. Run 'dku auth login' to get started.")
        return

    for name, cfg in profiles.items():
        marker = " *" if name == active else ""
        has_key = "key stored" if get_api_key(name) else "no key"
        url = cfg.get("url", "no url")
        console.print(f"  {name}{marker}  {url}  ({has_key})")


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
