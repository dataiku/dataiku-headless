"""dku code-env — list, get, create, delete, update, set-packages, usages, logs."""

from __future__ import annotations

import json

import typer

from dku_cli.errors import exit_with_error, handle_api_error
from dku_cli.helpers import get_client_from_ctx, read_text_input
from dku_cli.output import (
    hint,
    info,
    render,
    render_raw,
    resolve_output_format,
    success,
)

app = typer.Typer(help="Manage DSS code environments.")


_PY_INTERPRETERS = frozenset(
    {"PYTHON39", "PYTHON310", "PYTHON311", "PYTHON312", "PYTHON313"}
)


def _normalize_python_interpreter(value: str) -> str | None:
    """Map '3.11' or 'PYTHON311' → 'PYTHON311'. Returns None for unrecognized input."""
    if not value:
        return None
    candidate = value.strip().upper().replace(".", "")
    if not candidate.startswith("PYTHON"):
        candidate = "PYTHON" + candidate
    if candidate in _PY_INTERPRETERS:
        return candidate
    return None


@app.command("list")
def list_envs(
    ctx: typer.Context,
) -> None:
    """List all code environments."""
    output = resolve_output_format()
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
) -> None:
    """Show code environment details."""
    output = resolve_output_format()
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
            # `corePackagesSet` is just the SELECTED set name (a dropdown value
            # that persists whether or not core packages are installed). The
            # authoritative install indicator is `installCorePackages`. Show
            # both so the display does not falsely imply core packages are
            # present after a `--no-core-packages` create.
            core_set = desc.get("corePackagesSet") or "(none)"
            if desc.get("installCorePackages"):
                core_display = core_set
            else:
                core_display = f"disabled (selected set: {core_set})"
            data = [
                {"field": "Name", "value": definition.get("envName", name)},
                {"field": "Language", "value": definition.get("envLang", lang)},
                {"field": "Type", "value": definition.get("deploymentMode", "")},
                {"field": "Interpreter", "value": desc.get("pythonInterpreter", "")},
                {
                    "field": "Core packages",
                    "value": core_display,
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
    python_version: str | None = typer.Option(
        None,
        "--python-version",
        help="Python interpreter to bind to the env. Accepts '3.11' or 'PYTHON311' "
        "(maps to params.pythonInterpreter). DSS supports PYTHON39 through PYTHON313.",
    ),
    core_packages: bool = typer.Option(
        True,
        "--core-packages/--no-core-packages",
        help="(Python) install DSS core packages (requests, python-dateutil, ...) so the "
        "`dataiku` API imports inside recipes. A fresh env created without these fails at "
        "recipe runtime with `ModuleNotFoundError: No module named 'requests'`. Ignored for R.",
    ),
) -> None:
    """Create a new code environment.

    For PYTHON envs, core packages are installed by default so the env can run
    recipes (the `dataiku` API needs requests/python-dateutil/...). Pass
    --no-core-packages for a bare env (e.g. when you will only run it as a
    standalone interpreter).

    Examples:
      dku code-env create my_env
      dku code-env create my_env --python-version 3.11
      dku code-env create my_env --package pandas --package pdfplumber
      dku code-env create my_env --requirements @requirements.txt
      dku code-env create my_env --no-core-packages
      cat requirements.txt | dku code-env create my_env --requirements -
    """
    interpreter = None
    if python_version:
        interpreter = _normalize_python_interpreter(python_version)
        if interpreter is None:
            exit_with_error(
                f"Unrecognized Python version: '{python_version}'.",
                details=[
                    "Accepted forms: '3.9', '3.10', '3.11', '3.12', '3.13',",
                    "or 'PYTHON39' / 'PYTHON310' / 'PYTHON311' / 'PYTHON312' / 'PYTHON313'.",
                ],
            )
    try:
        client = get_client_from_ctx(ctx)
        definition = {
            "envLang": lang,
            "envName": name,
            "deploymentMode": deployment_mode,
        }
        if interpreter:
            definition["pythonInterpreter"] = interpreter
            definition["desiredPythonInterpreter"] = interpreter
        client.create_code_env(lang, name, deployment_mode, definition)
        success(f"Created code environment '{name}' ({lang})")

        # Apply packages and/or core-package install via set_definition + rebuild.
        # The package path reuses the same logic as `dku code-env set-packages`.
        # Core packages are enabled by default for PYTHON: without them a fresh
        # env cannot run recipes (the injected `dataiku` module imports requests
        # et al.), failing with ModuleNotFoundError at recipe runtime. DSS also
        # defaults installCorePackages to True server-side, so --no-core-packages
        # must be written back EXPLICITLY (False) — otherwise the flag is a no-op
        # and `code-env get` still shows core packages (e.g. PANDAS23) installed.
        is_python = lang.upper() == "PYTHON"
        if requirements or package or is_python:
            env = client.get_code_env(lang, name)
            env_def = env.get_definition()

            if requirements or package:
                pkg_lines: list[str] = []
                if requirements:
                    pkg_lines.append(read_text_input(requirements).strip())
                if package:
                    pkg_lines.extend(p.strip() for p in package if p.strip())
                combined = "\n".join(line for line in pkg_lines if line) + "\n"
                env_def["specPackageList"] = combined
                info(f"Set {len([p for p in combined.splitlines() if p])} package(s)")

            if is_python:
                env_def.setdefault("desc", {})["installCorePackages"] = core_packages
                if core_packages:
                    info("Enabling DSS core packages (requests, python-dateutil, ...)")
                else:
                    info("Disabling DSS core packages (--no-core-packages)")

            env.set_definition(env_def)
            info("Rebuilding environment...")
            env.update_packages()
            success(f"Rebuild complete for '{name}'")
        hint(f"dku code-env get {name} --lang {lang}")
    except Exception as e:
        handle_api_error(e)


@app.command()
def delete(
    ctx: typer.Context,
    name: str = typer.Argument(help="Code environment name"),
    lang: str = typer.Option("PYTHON", "--lang", "-l", help="Language (PYTHON or R)"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip safety guard"),
) -> None:
    """Delete a code environment."""
    from dku_cli.safety import Tier, guard

    guard(
        ctx,
        tier=Tier.DELETE,
        action="codeenv.delete",
        subject=f"{lang} code environment '{name}'",
        yes=yes,
        prompt=f"Delete {lang} code environment '{name}'?",
    )
    try:
        client = get_client_from_ctx(ctx)
        env = client.get_code_env(lang, name)
        env.delete()
        success(f"Deleted code environment '{name}'")
    except typer.Exit:
        raise
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
) -> None:
    """Show what uses a code environment."""
    output = resolve_output_format()
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
