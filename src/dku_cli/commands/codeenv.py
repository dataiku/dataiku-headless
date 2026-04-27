"""dku code-env — list, get, create, delete, update, set-packages, usages, logs."""

from __future__ import annotations

import json

import typer

from dku_cli.errors import handle_api_error
from dku_cli.helpers import get_client_from_ctx, read_text_input
from dku_cli.output import info, render, render_raw, resolve_output_format, success

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
            data.append(
                {
                    "name": env.get("envName", ""),
                    "lang": env.get("envLang", ""),
                    "type": env.get("deploymentMode", ""),
                    "owner": env.get("owner", ""),
                }
            )

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
                {
                    "field": "Core packages",
                    "value": desc.get("corePackagesSet", "(none)"),
                },
                {"field": "Spec packages", "value": str(len(packages))},
                {"field": "Owner", "value": definition.get("owner", "")},
            ]

            render(
                data,
                ["field", "value"],
                output_format=output,
                title=f"Code Env: {name}",
            )
    except Exception as e:
        handle_api_error(e)


@app.command()
def create(
    ctx: typer.Context,
    name: str = typer.Argument(help="Code environment name"),
    lang: str = typer.Option("PYTHON", "--lang", "-l", help="Language (PYTHON or R)"),
    deployment_mode: str = typer.Option(
        "DESIGN_MANAGED",
        "--type",
        "-t",
        help="Deployment mode (DESIGN_MANAGED, PLUGIN_MANAGED, etc.)",
    ),
    requirements: str | None = typer.Option(
        None,
        "--requirements",
        "-r",
        help="Initial package spec: literal string, @requirements.txt, or - for stdin. "
        "One package per line. Triggers a post-create rebuild.",
    ),
    package: list[str] = typer.Option(
        None,
        "--package",
        help="Add a single package (repeatable). Combined with --requirements if both given. "
        "Triggers a post-create rebuild.",
    ),
) -> None:
    """Create a new code environment.

    Examples:
      dku code-env create my_env
      dku code-env create my_env --package pandas --package pdfplumber
      dku code-env create my_env --requirements @requirements.txt
      cat requirements.txt | dku code-env create my_env --requirements -
    """
    try:
        client = get_client_from_ctx(ctx)
        definition = {
            "envLang": lang,
            "envName": name,
            "deploymentMode": deployment_mode,
        }
        client.create_code_env(lang, name, deployment_mode, definition)
        success(f"Created code environment '{name}' ({lang})")

        # If packages were specified, apply them via set_definition + rebuild.
        # This reuses the same path as `dku code-env set-packages` to stay
        # consistent with that command's behavior.
        if requirements or package:
            pkg_lines: list[str] = []
            if requirements:
                pkg_lines.append(read_text_input(requirements).strip())
            if package:
                pkg_lines.extend(p.strip() for p in package if p.strip())
            combined = "\n".join(line for line in pkg_lines if line) + "\n"

            env = client.get_code_env(lang, name)
            env_def = env.get_definition()
            env_def["specPackageList"] = combined
            env.set_definition(env_def)
            info(f"Set {len([p for p in combined.splitlines() if p])} package(s)")

            info("Rebuilding environment...")
            env.update_packages()
            success(f"Rebuild complete for '{name}'")
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
    force_rebuild: bool = typer.Option(
        False, "--force-rebuild", help="Rebuild the env from scratch"
    ),
    version: str | None = typer.Option(
        None, "--version", help="Env version to rebuild (automation nodes only)"
    ),
    wait: bool = typer.Option(True, "--wait/--no-wait", help="Block until complete"),
) -> None:
    """Update packages in a code environment (re-resolve versions, optional rebuild)."""
    try:
        client = get_client_from_ctx(ctx)
        env = client.get_code_env(lang, name)
        info("Updating packages...")
        env.update_packages(force_rebuild_env=force_rebuild, version=version, wait=wait)
        success(f"Updated packages for '{name}'")
    except Exception as e:
        handle_api_error(e)


@app.command()
def jupyter(
    ctx: typer.Context,
    name: str = typer.Argument(help="Code environment name"),
    lang: str = typer.Option("PYTHON", "--lang", "-l", help="Language (PYTHON or R)"),
    enable: bool = typer.Option(
        True,
        "--enable/--disable",
        help="Enable or disable Jupyter support in this env",
    ),
    wait: bool = typer.Option(True, "--wait/--no-wait", help="Block until complete"),
) -> None:
    """Toggle Jupyter support for a code environment.

    Non-destructive — existing recipes keep running; only Jupyter notebooks
    using this env are affected. Disabling frees disk by removing the
    ipykernel install.
    """
    try:
        client = get_client_from_ctx(ctx)
        env = client.get_code_env(lang, name)
        env.set_jupyter_support(active=enable, wait=wait)
        state = "enabled" if enable else "disabled"
        success(f"Jupyter support {state} for '{name}'")
    except Exception as e:
        handle_api_error(e)


@app.command("update-images")
def update_images(
    ctx: typer.Context,
    name: str = typer.Argument(help="Code environment name"),
    lang: str = typer.Option("PYTHON", "--lang", "-l", help="Language (PYTHON or R)"),
    env_version: str | None = typer.Option(
        None, "--env-version", help="Env version to rebuild (versioned envs only)"
    ),
    wait: bool = typer.Option(True, "--wait/--no-wait", help="Block until complete"),
) -> None:
    """Rebuild the Docker image for a code env (container-exec).

    Idempotent — safe to re-run. Required after container-exec base image
    changes or after `codeenv set-packages`. Existing pods keep running the
    old image until they're recycled.
    """
    try:
        client = get_client_from_ctx(ctx)
        env = client.get_code_env(lang, name)
        info(f"Rebuilding container image for '{name}'...")
        env.update_images(env_version=env_version, wait=wait)
        success(f"Rebuilt container image(s) for '{name}'")
    except Exception as e:
        handle_api_error(e)


@app.command("set-packages")
def set_packages(
    ctx: typer.Context,
    name: str = typer.Argument(help="Code environment name"),
    packages: str = typer.Option(
        ...,
        "--packages",
        "-p",
        help="Package spec (literal, @requirements.txt, or - for stdin). One package per line.",
    ),
    lang: str = typer.Option("PYTHON", "--lang", "-l", help="Language (PYTHON or R)"),
    rebuild: bool = typer.Option(
        True, "--rebuild/--no-rebuild", help="Rebuild env after changing packages"
    ),
) -> None:
    """Set the package list for a code environment.

    Replaces the entire package spec list. After setting, triggers a rebuild by default.

    Examples:
      dku code-env set-packages myenv -p "pandas>=2.0\\nnumpy>=1.22"
      dku code-env set-packages myenv -p @requirements.txt
      cat requirements.txt | dku code-env set-packages myenv -p -
    """
    try:
        client = get_client_from_ctx(ctx)
        env = client.get_code_env(lang, name)
        definition = env.get_definition()

        pkg_text = read_text_input(packages)
        definition["specPackageList"] = pkg_text
        env.set_definition(definition)
        success(f"Updated package list for '{name}'")

        if rebuild:
            info("Rebuilding environment...")
            env.update_packages()
            success(f"Rebuild complete for '{name}'")
    except Exception as e:
        handle_api_error(e)


@app.command()
def usages(
    ctx: typer.Context,
    name: str = typer.Argument(help="Code environment name"),
    lang: str = typer.Option("PYTHON", "--lang", "-l", help="Language (PYTHON or R)"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Show what uses a code environment."""
    output = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        env = client.get_code_env(lang, name)
        usage_list = env.list_usages()

        if output == "json":
            render_raw(usage_list, output_format="json")
        else:
            data = []
            for u in usage_list:
                data.append(
                    {
                        "type": u.get("envUsageType", u.get("type", "")),
                        "project": u.get("projectKey", ""),
                        "object": u.get("objectId", u.get("objectRef", "")),
                    }
                )
            render(
                data,
                ["type", "project", "object"],
                output_format=output,
                title=f"Usages: {name}",
            )
    except Exception as e:
        handle_api_error(e)


@app.command()
def logs(
    ctx: typer.Context,
    name: str = typer.Argument(help="Code environment name"),
    lang: str = typer.Option("PYTHON", "--lang", "-l", help="Language (PYTHON or R)"),
    log_name: str | None = typer.Option(
        None, "--log", help="Specific log name (default: list available logs)"
    ),
) -> None:
    """List or read code environment build logs."""
    try:
        client = get_client_from_ctx(ctx)
        env = client.get_code_env(lang, name)

        if log_name:
            log_content = env.get_log(log_name)
            print(log_content)
        else:
            log_list = env.list_logs()
            for log_entry in log_list:
                if isinstance(log_entry, dict):
                    print(log_entry.get("name", str(log_entry)))
                else:
                    print(log_entry)
    except Exception as e:
        handle_api_error(e)
