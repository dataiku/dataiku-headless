"""dku plugin — list, get, push, delete, settings, code-env management, usages."""

from __future__ import annotations

import json
from pathlib import Path
from zipfile import ZipFile

import typer

from dku_cli.errors import handle_api_error
from dku_cli.helpers import get_client_from_ctx
from dku_cli.output import error, info, render, render_raw, resolve_output_format, success, warn

app = typer.Typer(help="Manage DSS plugins.")


def _read_plugin_id(zip_path: Path) -> str:
    """Read the plugin id from plugin.json at the root of a plugin archive."""
    try:
        with ZipFile(zip_path) as archive:
            with archive.open("plugin.json") as plugin_file:
                plugin_meta = json.load(plugin_file)
    except KeyError as exc:
        raise typer.BadParameter(
            "Plugin archive must contain plugin.json at the ZIP root."
        ) from exc
    except OSError as exc:
        raise typer.BadParameter(f"Could not read plugin archive: {zip_path}") from exc
    except json.JSONDecodeError as exc:
        raise typer.BadParameter("plugin.json is not valid JSON.") from exc

    plugin_id = str(plugin_meta.get("id", "")).strip()
    if not plugin_id:
        raise typer.BadParameter("plugin.json must define a non-empty 'id'.")
    return plugin_id


@app.command("list")
def list_plugins(
    ctx: typer.Context,
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """List installed plugins."""
    output = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        # dataikuapi quirk: list_plugins() returns dicts, not objects
        plugins = client.list_plugins()

        data = []
        for p in plugins:
            data.append(
                {
                    "id": p.get("id", "")
                    if isinstance(p, dict)
                    else getattr(p, "plugin_id", ""),
                    "version": p.get("version", "") if isinstance(p, dict) else "",
                    "dev": str(p.get("isDev", False)) if isinstance(p, dict) else "",
                }
            )

        render(
            data,
            ["id", "version", "dev"],
            output_format=output,
            title="Plugins",
            headers={"id": "ID", "version": "VERSION", "dev": "DEV"},
        )
    except Exception as e:
        handle_api_error(e)


@app.command()
def push(
    ctx: typer.Context,
    zip_path: Path = typer.Argument(help="Path to plugin ZIP file"),
    update: bool = typer.Option(
        True, "--update/--install", help="Update existing or install new"
    ),
) -> None:
    """Push a plugin ZIP to DSS."""
    if not zip_path.exists():
        error(f"File not found: {zip_path}")
        raise typer.Exit(1)
    if not zip_path.suffix == ".zip":
        error("File must be a .zip archive")
        raise typer.Exit(1)

    plugin_id = _read_plugin_id(zip_path)

    try:
        client = get_client_from_ctx(ctx)
        installed_ids = {
            p.get("id", "") if isinstance(p, dict) else getattr(p, "plugin_id", "")
            for p in client.list_plugins()
        }

        with zip_path.open("rb") as f:
            if update and plugin_id in installed_ids:
                plugin = client.get_plugin(plugin_id)
                plugin.update_from_zip(f)
                success(f"Updated plugin '{plugin_id}'")
            else:
                client.install_plugin_from_archive(f)
                success(f"Installed plugin '{plugin_id}'")

    except Exception as e:
        handle_api_error(e)


@app.command()
def settings(
    ctx: typer.Context,
    plugin_id: str = typer.Argument(help="Plugin ID"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
    set_param: list[str] = typer.Option(None, "--set", help="Set parameter: key=value"),
) -> None:
    """View or update plugin settings."""
    output = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        plugin = client.get_plugin(plugin_id)
        plugin_settings = plugin.get_settings()
        raw = plugin_settings.get_raw()

        if set_param:
            config = raw.get("config", {})
            for param in set_param:
                if "=" not in param:
                    error(f"Invalid format: {param} (expected key=value)")
                    raise typer.Exit(1)
                key, value = param.split("=", 1)
                config[key] = value
                info(f"Set {key} = {value}")
            raw["config"] = config
            plugin_settings.save()
            success(f"Plugin '{plugin_id}' settings updated")
        else:
            config = raw.get("config", {})
            code_env = raw.get("codeEnvName", "")

            data = [{"key": "Code Environment", "value": code_env or "(default)"}]
            for k, v in config.items():
                display_v = (
                    "****"
                    if "password" in k.lower()
                    or "secret" in k.lower()
                    or "key" in k.lower()
                    else str(v)
                )
                data.append({"key": k, "value": display_v})

            render(
                data,
                ["key", "value"],
                output_format=output,
                title=f"Plugin Settings: {plugin_id}",
            )
    except Exception as e:
        handle_api_error(e)


@app.command()
def get(
    ctx: typer.Context,
    plugin_id: str = typer.Argument(help="Plugin ID"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Show plugin details including version, code env, and dev status."""
    output = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        # dataikuapi quirk: list_plugins() returns dicts — find this plugin's metadata
        plugins = client.list_plugins()
        plugin_meta = None
        for p in plugins:
            pid = p.get("id", "") if isinstance(p, dict) else getattr(p, "plugin_id", "")
            if pid == plugin_id:
                plugin_meta = p
                break

        if plugin_meta is None:
            error(f"Plugin '{plugin_id}' not found.")
            info("Run: dku plugin list")
            raise typer.Exit(3)

        plugin = client.get_plugin(plugin_id)
        plugin_settings = plugin.get_settings()
        raw = plugin_settings.get_raw()
        code_env = raw.get("codeEnvName", "")

        if output == "json":
            render_raw(
                {
                    "id": plugin_id,
                    "version": plugin_meta.get("version", "") if isinstance(plugin_meta, dict) else "",
                    "dev": plugin_meta.get("isDev", False) if isinstance(plugin_meta, dict) else False,
                    "codeEnvName": code_env,
                    "config": raw.get("config", {}),
                },
                output_format="json",
            )
        else:
            data = [
                {"field": "ID", "value": plugin_id},
                {"field": "Version", "value": plugin_meta.get("version", "") if isinstance(plugin_meta, dict) else ""},
                {"field": "Dev", "value": str(plugin_meta.get("isDev", False)) if isinstance(plugin_meta, dict) else ""},
                {"field": "Code Env", "value": code_env or "(default)"},
            ]
            config = raw.get("config", {})
            for k, v in config.items():
                display_v = (
                    "****"
                    if "password" in k.lower()
                    or "secret" in k.lower()
                    or "key" in k.lower()
                    else str(v)
                )
                data.append({"field": k, "value": display_v})

            render(
                data,
                ["field", "value"],
                output_format=output,
                title=f"Plugin: {plugin_id}",
            )
    except SystemExit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command()
def delete(
    ctx: typer.Context,
    plugin_id: str = typer.Argument(help="Plugin ID"),
    force: bool = typer.Option(False, "--force", help="Force delete even if plugin is in use"),
    confirm: bool = typer.Option(
        False, "--confirm", "--yes", "-y", help="Confirm deletion"
    ),
) -> None:
    """Delete a plugin. Requires --confirm / --yes flag.

    Use --force to delete even if the plugin is used by recipes, agents, etc.
    """
    if not confirm:
        warn("Deletion requires --confirm (or --yes / -y) flag.")
        raise typer.Exit(1)
    try:
        client = get_client_from_ctx(ctx)
        plugin = client.get_plugin(plugin_id)
        future = plugin.delete(force=force)
        if future is not None:
            future.wait_for_result()
        success(f"Deleted plugin '{plugin_id}'")
    except Exception as e:
        handle_api_error(e)


@app.command("create-code-env")
def create_code_env(
    ctx: typer.Context,
    plugin_id: str = typer.Argument(help="Plugin ID"),
    wait: bool = typer.Option(True, "--wait/--no-wait", help="Wait for code env creation"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Create the managed code environment for a plugin.

    Use after first install: dku plugin push ... --install && dku plugin create-code-env PLUGIN_ID
    """
    output = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        plugin = client.get_plugin(plugin_id)
        if output != "json":
            info(f"Creating code environment for plugin '{plugin_id}'...")
        future = plugin.create_code_env()

        if wait:
            result = future.wait_for_result()
            env_name = result.get("envName", "") if isinstance(result, dict) else ""
            if output == "json":
                render_raw(
                    {"pluginId": plugin_id, "envName": env_name},
                    output_format="json",
                )
            else:
                success(f"Created code environment '{env_name}' for plugin '{plugin_id}'")
                info(f"Assign it: dku plugin set-code-env {plugin_id} {env_name}")
        else:
            success(f"Code environment creation started for plugin '{plugin_id}'")
    except Exception as e:
        handle_api_error(e)


@app.command("set-code-env")
def set_code_env(
    ctx: typer.Context,
    plugin_id: str = typer.Argument(help="Plugin ID"),
    env_name: str = typer.Argument(help="Code environment name to assign"),
) -> None:
    """Assign a code environment to a plugin.

    After creating a code env: dku plugin set-code-env PLUGIN_ID ENV_NAME
    """
    try:
        client = get_client_from_ctx(ctx)
        plugin = client.get_plugin(plugin_id)
        plugin_settings = plugin.get_settings()
        plugin_settings.set_code_env(env_name)
        plugin_settings.save()
        success(f"Assigned code environment '{env_name}' to plugin '{plugin_id}'")
    except Exception as e:
        handle_api_error(e)


@app.command("update-code-env")
def update_code_env(
    ctx: typer.Context,
    plugin_id: str = typer.Argument(help="Plugin ID"),
    wait: bool = typer.Option(True, "--wait/--no-wait", help="Wait for update to complete"),
) -> None:
    """Rebuild a plugin's code environment after dependency changes.

    Run after updating requirements.txt: dku plugin push ... && dku plugin update-code-env PLUGIN_ID
    """
    try:
        client = get_client_from_ctx(ctx)
        plugin = client.get_plugin(plugin_id)
        info(f"Updating code environment for plugin '{plugin_id}'...")
        future = plugin.update_code_env()

        if wait:
            future.wait_for_result()
            success(f"Updated code environment for plugin '{plugin_id}'")
        else:
            success(f"Code environment update started for plugin '{plugin_id}'")
    except Exception as e:
        handle_api_error(e)


@app.command()
def usages(
    ctx: typer.Context,
    plugin_id: str = typer.Argument(help="Plugin ID"),
    project: str | None = typer.Option(None, "--project", "-P", help="Filter by project key"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Show where a plugin's components are used across projects."""
    output = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        plugin = client.get_plugin(plugin_id)
        usage_obj = plugin.list_usages(project_key=project)

        # DSSPluginUsages has .get_raw() returning usage data
        raw = usage_obj.get_raw() if hasattr(usage_obj, "get_raw") else {}

        if output == "json":
            render_raw(raw, output_format="json")
        else:
            usages_list = raw.get("usages", [])
            if not usages_list:
                info(f"No usages found for plugin '{plugin_id}'")
                return

            data = []
            for u in usages_list:
                data.append(
                    {
                        "project": u.get("projectKey", ""),
                        "type": u.get("objectType", ""),
                        "id": u.get("objectId", ""),
                        "element": u.get("elementKind", ""),
                    }
                )

            render(
                data,
                ["project", "type", "id", "element"],
                output_format=output,
                title=f"Plugin Usages: {plugin_id}",
            )
    except Exception as e:
        handle_api_error(e)
