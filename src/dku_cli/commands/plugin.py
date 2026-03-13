"""dku plugin — list, push, settings."""

from __future__ import annotations

import json
from pathlib import Path
from zipfile import ZipFile

import typer

from dku_cli.errors import handle_api_error
from dku_cli.helpers import get_client_from_ctx
from dku_cli.output import error, info, render, resolve_output_format, success

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
            data.append({
                "id": p.get("id", "") if isinstance(p, dict) else getattr(p, "plugin_id", ""),
                "version": p.get("version", "") if isinstance(p, dict) else "",
                "dev": str(p.get("isDev", False)) if isinstance(p, dict) else "",
            })

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
    update: bool = typer.Option(True, "--update/--install", help="Update existing or install new"),
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
    set_param: list[str] = typer.Option(
        None, "--set", help="Set parameter: key=value"
    ),
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
                display_v = "****" if "password" in k.lower() or "secret" in k.lower() or "key" in k.lower() else str(v)
                data.append({"key": k, "value": display_v})

            render(
                data,
                ["key", "value"],
                output_format=output,
                title=f"Plugin Settings: {plugin_id}",
            )
    except Exception as e:
        handle_api_error(e)
