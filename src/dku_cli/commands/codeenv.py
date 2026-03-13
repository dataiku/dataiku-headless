"""dku code-env — list, get, create, delete, update."""

from __future__ import annotations

import json

import typer

from dku_cli.errors import handle_api_error
from dku_cli.helpers import get_client_from_ctx
from dku_cli.output import info, render, resolve_output_format, success

app = typer.Typer(help="Manage DSS code environments.")


@app.command("list")
def list_envs(
    ctx: typer.Context,
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """List all code environments."""
    output = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        # dataikuapi quirk: returns dicts, not objects
        envs = client.list_code_envs()

        data = []
        for env in envs:
            data.append({
                "name": env.get("envName", ""),
                "lang": env.get("envLang", ""),
                "type": env.get("deploymentMode", ""),
                "owner": env.get("owner", ""),
            })

        render(
            data,
            ["name", "lang", "type", "owner"],
            output_format=output,
            title="Code Environments",
        )
    except Exception as e:
        handle_api_error(e)


@app.command()
def get(
    ctx: typer.Context,
    name: str = typer.Argument(help="Code environment name"),
    lang: str = typer.Option("PYTHON", "--lang", "-l", help="Language (PYTHON or R)"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Show code environment details."""
    output = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        env = client.get_code_env(lang, name)
        definition = env.get_definition()

        if output == "json":
            print(json.dumps(definition, indent=2, default=str))
        else:
            desc = definition.get("desc", {})
            packages = definition.get("specPackageList", "").strip().splitlines()
            packages = [p for p in packages if p]  # filter empty
            data = [
                {"field": "Name", "value": definition.get("envName", name)},
                {"field": "Language", "value": definition.get("envLang", lang)},
                {"field": "Type", "value": definition.get("deploymentMode", "")},
                {"field": "Interpreter", "value": desc.get("pythonInterpreter", "")},
                {"field": "Core packages", "value": desc.get("corePackagesSet", "(none)")},
                {"field": "Spec packages", "value": str(len(packages))},
                {"field": "Owner", "value": definition.get("owner", "")},
            ]

            render(data, ["field", "value"], output_format=output, title=f"Code Env: {name}")
    except Exception as e:
        handle_api_error(e)


@app.command()
def create(
    ctx: typer.Context,
    name: str = typer.Argument(help="Code environment name"),
    lang: str = typer.Option("PYTHON", "--lang", "-l", help="Language (PYTHON or R)"),
    deployment_mode: str = typer.Option(
        "DESIGN_MANAGED", "--type", "-t",
        help="Deployment mode (DESIGN_MANAGED, PLUGIN_MANAGED, etc.)",
    ),
) -> None:
    """Create a new code environment."""
    try:
        client = get_client_from_ctx(ctx)
        definition = {
            "envLang": lang,
            "envName": name,
            "deploymentMode": deployment_mode,
        }
        env = client.create_code_env(lang, name, deployment_mode, definition)
        success(f"Created code environment '{name}' ({lang})")
    except Exception as e:
        handle_api_error(e)


@app.command()
def delete(
    ctx: typer.Context,
    name: str = typer.Argument(help="Code environment name"),
    lang: str = typer.Option("PYTHON", "--lang", "-l", help="Language (PYTHON or R)"),
) -> None:
    """Delete a code environment."""
    try:
        client = get_client_from_ctx(ctx)
        env = client.get_code_env(lang, name)
        env.delete()
        success(f"Deleted code environment '{name}'")
    except Exception as e:
        handle_api_error(e)


@app.command()
def update(
    ctx: typer.Context,
    name: str = typer.Argument(help="Code environment name"),
    lang: str = typer.Option("PYTHON", "--lang", "-l", help="Language (PYTHON or R)"),
) -> None:
    """Update packages in a code environment."""
    try:
        client = get_client_from_ctx(ctx)
        env = client.get_code_env(lang, name)
        info("Updating packages...")
        env.update_packages()
        success(f"Updated packages for '{name}'")
    except Exception as e:
        handle_api_error(e)
