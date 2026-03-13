"""dku auth — login, logout, status, list, switch."""

from __future__ import annotations

import typer
from rich.prompt import Prompt

from dku_cli.auth import delete_api_key, get_api_key, store_api_key
from dku_cli.brand import ICON, print_logo, welcome
from dku_cli.config import (
    clear_profile_configs,
    delete_profile_config,
    get_active_profile,
    get_all_profiles,
    get_profile_config,
    set_active_profile,
    set_default_project,
    set_profile_config,
)
from dku_cli.output import console, error, info, success

app = typer.Typer(help="Manage DSS authentication profiles.")


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
            project_key = Prompt.ask("Default project? (leave blank to skip)", default="")
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
def status() -> None:
    """Show current authentication status."""
    profile = get_active_profile()
    config = get_profile_config(profile)
    url = config.get("url")

    if not url:
        error(f'Profile "{profile}" has no URL configured.')
        error("Run 'dku auth login' to set up.")
        raise typer.Exit(1)

    api_key = get_api_key(profile)
    if not api_key:
        error(f'Profile "{profile}" has no API key stored.')
        raise typer.Exit(1)

    # Test connection
    try:
        import dataikuapi

        client = dataikuapi.DSSClient(url, api_key=api_key)
        auth_info = client.get_auth_info()
        user = auth_info.get("authIdentifier", "unknown")
        console.print(f"[bold]Profile:[/bold]  {profile}")
        console.print(f"[bold]URL:[/bold]      {url}")
        console.print(f"[bold]User:[/bold]     {user}")
        console.print(f"[bold]Status:[/bold]   [green]{ICON} Connected[/green]")
    except Exception as e:
        console.print(f"[bold]Profile:[/bold]  {profile}")
        console.print(f"[bold]URL:[/bold]      {url}")
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
