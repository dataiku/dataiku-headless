"""dku plugin — list, get, push, delete, download, settings, code-env management, usages, file operations (get/put/list/rename/move), install-from-store, install-from-git, update-from-store, update-from-git."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from zipfile import ZipFile

import typer

from dku_cli.errors import exit_with_error, handle_api_error
from dku_cli.helpers import get_client_from_ctx, locked_settings
from dku_cli.output import (
    error,
    info,
    render,
    render_raw,
    resolve_output_format,
    success,
    warn,
)

app = typer.Typer(help="Manage DSS plugins.")


def _zip_directory(dir_path: Path) -> Path:
    """Zip a plugin directory to a temporary file for upload.

    Raises typer.BadParameter if dir_path does not contain plugin.json.
    """
    plugin_json = dir_path / "plugin.json"
    if not plugin_json.exists():
        raise typer.BadParameter(
            f"Directory '{dir_path}' does not contain plugin.json.\n"
            "Expected a plugin root directory with plugin.json, or a .zip archive.\n"
            "Plugin directory structure:\n"
            "  my-plugin/\n"
            "  ├── plugin.json\n"
            "  ├── python-lib/\n"
            "  └── python-structured-agent-blocks/ (or other component dirs)"
        )
    tmp_fd, tmp_name = tempfile.mkstemp(suffix=".zip")
    os.close(tmp_fd)
    tmp = Path(tmp_name)
    with ZipFile(tmp, "w") as zf:
        for file in sorted(dir_path.rglob("*")):
            if file.is_file():
                zf.write(file, file.relative_to(dir_path))
    return tmp


def _find_plugin_json_member(archive: ZipFile) -> str | None:
    """Locate plugin.json inside a plugin archive.

    Returns its member path if it sits at the ZIP root OR exactly one
    directory deep under a single top-level folder (the layout Dataiku
    plugin exports and GitHub "Download ZIP" both produce — e.g.
    ``my-plugin-main/plugin.json``). Returns None when plugin.json is
    absent or the wrapper is ambiguous (loose files beside the folder, or
    more than one top-level entry).
    """
    files = [n for n in archive.namelist() if not n.endswith("/")]
    if "plugin.json" in files:
        return "plugin.json"
    nested = [n for n in files if n.count("/") == 1 and n.endswith("/plugin.json")]
    top_dirs = {n.split("/", 1)[0] for n in files if "/" in n}
    loose_at_root = [n for n in files if "/" not in n]
    # Single wrapper dir, nothing loose at the root → safe to flatten.
    if len(nested) == 1 and len(top_dirs) == 1 and not loose_at_root:
        return nested[0]
    return None


def _repack_flat(zip_path: Path, wrapper: str) -> Path:
    """Repack a wrapped plugin ZIP so its contents sit at the root.

    Strips the single top-level ``wrapper/`` directory from every member.
    Returns the path to a new temp ZIP (caller is responsible for deleting it).
    """
    prefix = wrapper.rstrip("/") + "/"
    out_fd, out_name = tempfile.mkstemp(suffix=".zip")
    os.close(out_fd)
    out = Path(out_name)
    with ZipFile(zip_path) as src, ZipFile(out, "w") as dst:
        for name in src.namelist():
            if name.endswith("/") or not name.startswith(prefix):
                continue
            with src.open(name) as member:
                dst.writestr(name[len(prefix) :], member.read())
    return out


def _read_plugin_id(zip_path: Path) -> str:
    """Read the plugin id from plugin.json in a plugin archive (root or one
    directory deep)."""
    try:
        with ZipFile(zip_path) as archive:
            member = _find_plugin_json_member(archive)
            if member is None:
                raise typer.BadParameter(
                    "Plugin archive must contain plugin.json at the ZIP root "
                    "(or under a single top-level folder).\n"
                    "Dataiku exports and GitHub 'Download ZIP' wrap content under "
                    "a folder — `dku plugin push` auto-flattens that, but only when "
                    "there is exactly ONE top-level folder and nothing loose beside "
                    "it. Repack flat: cd <dir> && zip -r ../flat.zip ."
                )
            with archive.open(member) as plugin_file:
                plugin_meta = json.load(plugin_file)
    except OSError as exc:
        raise typer.BadParameter(f"Could not read plugin archive: {zip_path}") from exc
    except json.JSONDecodeError as exc:
        raise typer.BadParameter("plugin.json is not valid JSON.") from exc

    plugin_id = str(plugin_meta.get("id", "")).strip()
    if not plugin_id:
        raise typer.BadParameter("plugin.json must define a non-empty 'id'.")
    return plugin_id


def _plugin_is_dev(p) -> bool:
    """Whether a list_plugins() item is a dev plugin.

    DSS is inconsistent across versions: some builds expose the flag as ``dev``
    (a STRING ``"True"`` / ``"False"``), others as ``isDev`` (a JSON bool —
    observed live on DSS 14.6, where ``dev`` is absent entirely). Honour
    whichever key is present so both the DEV column and the dev-only
    ``list_files()`` path stay correct across versions.
    """
    if isinstance(p, dict):
        val = p.get("dev")
        if val is None:
            val = p.get("isDev", False)
    else:
        val = getattr(p, "dev", None)
        if val is None:
            val = getattr(p, "isDev", False)
    if isinstance(val, str):
        return val.strip().lower() == "true"
    return bool(val)


@app.command("list")
def list_plugins(
    ctx: typer.Context,
) -> None:
    """List installed plugins."""
    output = resolve_output_format()
    try:
        client = get_client_from_ctx(ctx)
        # dataikuapi quirk: list_plugins() returns dicts, not objects
        plugins = client.list_plugins()

        data = []
        for p in plugins:
            if isinstance(p, dict):
                pid, ver = p.get("id", ""), p.get("version", "")
            else:
                pid, ver = getattr(p, "plugin_id", ""), getattr(p, "version", "")
            data.append({"id": pid, "version": ver, "dev": _plugin_is_dev(p)})

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
    path: Path = typer.Argument(
        help="Plugin directory (containing plugin.json) or .zip archive"
    ),
    update: bool = typer.Option(
        True, "--update/--install", help="Update existing or install new"
    ),
) -> None:
    """Push a plugin to DSS from a directory or ZIP archive.

    If PATH is a directory containing plugin.json, it is automatically
    zipped before upload. If PATH is a .zip file, it is used directly.
    """
    if not path.exists():
        error(f"Not found: {path}")
        raise typer.Exit(1)

    tmp_zip: Path | None = None
    flat_zip: Path | None = None
    if path.is_dir():
        tmp_zip = _zip_directory(path)
        info(f"Zipped plugin directory: {path}")
        zip_path = tmp_zip
    elif path.suffix == ".zip":
        zip_path = path
    else:
        error(
            f"Unsupported file type: {path.suffix}\n"
            "Expected a plugin directory (with plugin.json) or a .zip archive.\n"
            "Example: dku plugin push ./my-plugin/\n"
            "Example: dku plugin push my-plugin.zip"
        )
        raise typer.Exit(1)

    try:
        # Auto-flatten archives that wrap content under a single top-level
        # folder (Dataiku exports + GitHub "Download ZIP" both do this; DSS
        # rejects them with "Plugin archive must contain plugin.json at the
        # ZIP root"). Directory pushes are already flat.
        with ZipFile(zip_path) as _probe:
            member = _find_plugin_json_member(_probe)
        if member is not None and member != "plugin.json":
            wrapper = member.split("/", 1)[0]
            flat_zip = _repack_flat(zip_path, wrapper)
            info(
                f"Archive wrapped content under '{wrapper}/' — repacked flat "
                "for upload."
            )
            zip_path = flat_zip

        plugin_id = _read_plugin_id(zip_path)

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

        warn(
            "The DSS UI plugin catalog is loaded at backend start and does NOT "
            "see types added/updated via API on a running instance."
        )
        info(
            "Recipes of this plugin's types still BUILD and RUN correctly — the "
            "job runner reads plugins from disk per-job. Verify by BUILDING the "
            "recipe (dku recipe run / dku job run), not by opening it in the UI "
            "editor (which may report 'recipe cannot be retrieved / plugin "
            "uninstalled' until DSS is restarted or reloaded)."
        )

    except SystemExit:
        raise
    except Exception as e:
        handle_api_error(e)
    finally:
        for tmp in (tmp_zip, flat_zip):
            if tmp and tmp.exists():
                tmp.unlink()


@app.command()
def settings(
    ctx: typer.Context,
    plugin_id: str = typer.Argument(help="Plugin ID"),
    set_param: list[str] = typer.Option(None, "--set", help="Set parameter: key=value"),
) -> None:
    """View or update plugin settings."""
    output = resolve_output_format()
    try:
        client = get_client_from_ctx(ctx)
        plugin = client.get_plugin(plugin_id)

        if set_param:
            with locked_settings(
                client, "-", "plugin", plugin_id, plugin.get_settings
            ) as plugin_settings:
                raw = plugin_settings.get_raw()
                config = raw.get("config", {})
                for param in set_param:
                    if "=" not in param:
                        error(f"Invalid format: {param} (expected key=value)")
                        raise typer.Exit(1)
                    key, value = param.split("=", 1)
                    config[key] = value
                    info(f"Set {key} = {value}")
                raw["config"] = config
            success(f"Plugin '{plugin_id}' settings updated")
        else:
            plugin_settings = plugin.get_settings()
            raw = plugin_settings.get_raw()
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
) -> None:
    """Show plugin details including version, code env, and dev status."""
    output = resolve_output_format()
    try:
        client = get_client_from_ctx(ctx)
        # dataikuapi quirk: list_plugins() returns dicts — find this plugin's metadata
        plugins = client.list_plugins()
        plugin_meta = None
        for p in plugins:
            pid = (
                p.get("id", "") if isinstance(p, dict) else getattr(p, "plugin_id", "")
            )
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

        config = raw.get("config", {})
        masked_config = {
            k: (
                "****"
                if "password" in k.lower()
                or "secret" in k.lower()
                or "key" in k.lower()
                else v
            )
            for k, v in config.items()
        }
        result = {
            "id": plugin_id,
            "version": plugin_meta.get("version", "")
            if isinstance(plugin_meta, dict)
            else "",
            "dev": _plugin_is_dev(plugin_meta),
            "codeEnvName": code_env,
            "config": masked_config,
        }
        render_raw(result, output_format=output)
    except SystemExit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command()
def delete(
    ctx: typer.Context,
    plugin_id: str = typer.Argument(help="Plugin ID"),
    force: bool = typer.Option(
        False, "--force", help="Force delete even if plugin is in use"
    ),
    yes: bool = typer.Option(
        False, "--yes", "-y", "--confirm", help="Skip safety guard"
    ),
    confirm_name: str = typer.Option(
        None,
        "--confirm-name",
        help="With --force, must match PLUGIN_ID to proceed (tier-3 guard).",
    ),
) -> None:
    """Delete a plugin.

    Without --force: tier-2 guard, requires --yes.
    With --force (overrides in-use check): tier-3 guard, requires --yes + --confirm-name PLUGIN_ID.
    """
    from dku_cli.safety import Tier, guard

    tier = Tier.CASCADE if force else Tier.DELETE
    guard(
        ctx,
        tier=tier,
        action="plugin.delete",
        subject=f"plugin '{plugin_id}'"
        + (" (FORCE — ignoring in-use recipes/agents)" if force else ""),
        yes=yes,
        target_id=plugin_id if force else None,
        confirm_name=confirm_name,
        prompt=(
            f"Delete plugin '{plugin_id}'"
            + (
                " even though it may still be in use by recipes/agents?"
                if force
                else "?"
            )
        ),
    )
    try:
        client = get_client_from_ctx(ctx)
        plugin = client.get_plugin(plugin_id)
        future = plugin.delete(force=force)
        if future is not None:
            future.wait_for_result()
        success(f"Deleted plugin '{plugin_id}'")
    except Exception as e:
        handle_api_error(e)


def _bound_managed_env(plugin) -> str | None:
    """Return the name of the managed code env already bound to a plugin, or None.

    DSS records the bound managed env in the plugin's instance-level settings under
    `codeEnvName` (see dataikuapi DSSPluginSettings.set_code_env / get_raw). Treat
    only a non-empty string as a real binding so a missing/None field means "unbound".
    """
    try:
        raw = plugin.get_settings().get_raw()
    except Exception:
        return None
    bound = raw.get("codeEnvName") if isinstance(raw, dict) else None
    if isinstance(bound, str) and bound.strip():
        return bound
    return None


@app.command("create-code-env")
def create_code_env(
    ctx: typer.Context,
    plugin_id: str = typer.Argument(help="Plugin ID"),
    wait: bool = typer.Option(
        True, "--wait/--no-wait", help="Wait for code env creation"
    ),
    force: bool = typer.Option(
        False,
        "--force",
        help="Create a new managed env even if one is already bound (creates a numbered duplicate)",
    ),
) -> None:
    """Create the managed code environment for a plugin.

    Use after first install: dku plugin push ... --install && dku plugin create-code-env PLUGIN_ID

    Idempotent: if a managed env is already bound, this skips creation (exit 0) and
    points at the rebuild command. Pass --force to create a numbered duplicate anyway.
    """
    output = resolve_output_format()
    try:
        client = get_client_from_ctx(ctx)
        plugin = client.get_plugin(plugin_id)

        # Idempotency guard: don't blindly create a duplicate numbered env
        # (e.g. plugin_<id>_managed_2) when one is already bound.
        if not force:
            existing = _bound_managed_env(plugin)
            if existing is not None:
                if output == "json":
                    render_raw(
                        {
                            "pluginId": plugin_id,
                            "envName": existing,
                            "created": False,
                            "reason": "already-bound",
                        },
                        output_format="json",
                    )
                else:
                    warn(
                        f"Plugin '{plugin_id}' already has managed code env '{existing}' "
                        "bound — skipping creation (idempotent)."
                    )
                    info(f"  Rebuild it:        dku plugin update-code-env {plugin_id}")
                    info(f"  Or update the env: dku code-env update {existing}")
                    info(
                        "  Force a new (duplicate) env: "
                        f"dku plugin create-code-env {plugin_id} --force"
                    )
                return

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
                success(
                    f"Created code environment '{env_name}' for plugin '{plugin_id}'"
                )
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
        with locked_settings(
            client, "-", "plugin", plugin_id, plugin.get_settings
        ) as plugin_settings:
            plugin_settings.set_code_env(env_name)
        success(f"Assigned code environment '{env_name}' to plugin '{plugin_id}'")
    except Exception as e:
        handle_api_error(e)


@app.command("update-code-env")
def update_code_env(
    ctx: typer.Context,
    plugin_id: str = typer.Argument(help="Plugin ID"),
    wait: bool = typer.Option(
        True, "--wait/--no-wait", help="Wait for update to complete"
    ),
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
    project: str | None = typer.Option(
        None, "--project", "-P", help="Filter by project key"
    ),
) -> None:
    """Show where a plugin's components are used across projects."""
    output = resolve_output_format()
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


@app.command()
def recipes(
    ctx: typer.Context,
    plugin_id: str | None = typer.Argument(
        None, help="Plugin ID (optional — lists recipes from all plugins if omitted)"
    ),
) -> None:
    """List plugin recipe types available for use with 'dku recipe create'.

    Shows the full type string needed for --type, e.g.:
      dku recipe create my_step -t CustomCode_my-recipe -i in --output-ds out -P PROJ

    IMPORTANT: Plugin recipe type format is CustomCode_<recipeComponentId>.
    The plugin ID is NOT part of the type string. The recipeComponentId comes
    from the directory name in custom-recipes/ inside the plugin.
    """
    output_fmt = resolve_output_format()
    try:
        client = get_client_from_ctx(ctx)
        plugins = client.list_plugins()

        data = []
        matched = False
        opaque = []  # installed (non-dev) plugins we can't enumerate via API
        for p in plugins:
            pid = p.get("id", "") if isinstance(p, dict) else getattr(p, "id", "")
            if plugin_id and pid != plugin_id:
                continue
            matched = True

            # Only dev plugins expose list_files(); installed plugins raise
            # "is not a dev plugin", so introspection is dev-only.
            recipe_ids = []
            introspected = False
            if _plugin_is_dev(p):
                try:
                    file_tree = client.get_plugin(pid).list_files()
                    for item in file_tree:
                        if (
                            isinstance(item, dict)
                            and item.get("name") == "custom-recipes"
                        ):
                            for child in item.get("children", []):
                                if isinstance(child, dict) and "children" in child:
                                    recipe_ids.append(child["name"])
                    introspected = True
                except Exception:
                    pass

            if recipe_ids:
                for rid in recipe_ids:
                    data.append(
                        {
                            "plugin": pid,
                            "recipe_id": rid,
                            "label": rid,
                            "type": f"CustomCode_{rid}",
                        }
                    )
            elif introspected:
                # Dev plugin, file tree readable, but no custom-recipes/ dir —
                # this plugin contributes no recipe types. Skip silently.
                continue
            else:
                # Installed (non-dev) plugin: the public API cannot enumerate
                # its custom-recipes components. Record for an honest footer.
                opaque.append(pid)

        if plugin_id and not matched:
            error(f"Plugin '{plugin_id}' not found.")
            info("Run: dku plugin list")
            raise typer.Exit(3)

        if not plugins:
            info("No plugins installed. Install one: dku plugin push <path>")
            return

        if data:
            render(
                data,
                ["plugin", "recipe_id", "label", "type"],
                output_format=output_fmt,
                title="Plugin Recipes",
                headers={
                    "plugin": "PLUGIN",
                    "recipe_id": "RECIPE ID",
                    "label": "LABEL",
                    "type": "TYPE (use with --type)",
                },
            )
        elif output_fmt == "json":
            # Keep JSON consumers happy: emit an empty array rather than prose.
            render([], ["plugin", "recipe_id", "label", "type"], output_format="json")

        if opaque and output_fmt != "json":
            info(
                "The public API cannot enumerate recipe components of installed "
                "(non-dev) plugins: " + ", ".join(sorted(opaque))
            )
            info(
                "Their recipe type is CustomCode_<recipeComponentId>, where "
                "<recipeComponentId> is the directory name under custom-recipes/ "
                "in the plugin (see the plugin's store page or its source ZIP)."
            )
    except (SystemExit, typer.Exit):
        raise
    except Exception as e:
        handle_api_error(e)


# Plugin component dirs we can enumerate via the dev-plugin file tree, mapped to
# the (kind, type-string-template) the agent needs to actually USE the component.
# {plugin} and {id} are filled per component. Recipe + agent-tool type formats are
# live-verified; dataset (custom connector) type is <pluginId>_<connectorId>.
_COMPONENT_DIRS = {
    "custom-recipes": ("recipe", "CustomCode_{id}"),
    "python-agent-tools": ("agent-tool", "Custom_agent_tool_{plugin}_{id}"),
    "python-connectors": ("dataset", "{plugin}_{id}"),
    "python-steps": ("scenario-step", "pystep_{plugin}_{id}"),
    "python-triggers": ("trigger", "pytrigger_{plugin}_{id}"),
    "python-runnables": ("runnable", "pyrunnable_{plugin}_{id}"),
}


@app.command()
def components(
    ctx: typer.Context,
    plugin_id: str | None = typer.Argument(
        None, help="Plugin ID (optional — lists components from all plugins if omitted)"
    ),
) -> None:
    """List a plugin's usable components (recipes, agent-tools, datasets,
    scenario-steps, triggers, runnables).

    Surfaces the full type string each component needs:
      recipe        → dku recipe create ... -t CustomCode_<id>
      agent-tool    → dku agent-tool create ... -t Custom_agent_tool_<plugin>_<id>
      dataset       → custom connector type <plugin>_<id>
      scenario-step → dku scenario add-step ... --type pystep_<plugin>_<id>
      trigger       → trigger type pytrigger_<plugin>_<id>
      runnable      → dku macro run pyrunnable_<plugin>_<id>

    Only DEV plugins can be enumerated via the public API (they expose
    list_files()); installed (non-dev) plugins are reported as an honest footer.
    """
    output_fmt = resolve_output_format()
    try:
        client = get_client_from_ctx(ctx)
        plugins = client.list_plugins()

        data: list[dict] = []
        matched = False
        opaque: list[str] = []
        for p in plugins:
            pid = p.get("id", "") if isinstance(p, dict) else ""
            if plugin_id and pid != plugin_id:
                continue
            matched = True

            if not _plugin_is_dev(p):
                opaque.append(pid)
                continue
            try:
                file_tree = client.get_plugin(pid).list_files()
            except Exception:
                opaque.append(pid)
                continue

            roots = file_tree if isinstance(file_tree, list) else [file_tree]
            for item in roots:
                if not isinstance(item, dict):
                    continue
                spec = _COMPONENT_DIRS.get(item.get("name", ""))
                if spec is None:
                    continue
                kind, type_tmpl = spec
                for child in item.get("children", []) or []:
                    if isinstance(child, dict) and child.get("children") is not None:
                        cid = child.get("name", "")
                        data.append(
                            {
                                "plugin": pid,
                                "kind": kind,
                                "id": cid,
                                "type": type_tmpl.format(plugin=pid, id=cid),
                            }
                        )

        if plugin_id and not matched:
            error(f"Plugin '{plugin_id}' not found.")
            info("Run: dku plugin list")
            raise typer.Exit(3)

        if not plugins:
            info("No plugins installed. Install one: dku plugin push <path>")
            return

        if data:
            render(
                data,
                ["plugin", "kind", "id", "type"],
                output_format=output_fmt,
                title="Plugin Components",
                headers={
                    "plugin": "PLUGIN",
                    "kind": "KIND",
                    "id": "ID",
                    "type": "TYPE (use to create)",
                },
            )
        elif output_fmt == "json":
            render([], ["plugin", "kind", "id", "type"], output_format="json")

        if opaque and output_fmt != "json":
            info(
                "The public API cannot enumerate components of installed "
                "(non-dev) plugins: " + ", ".join(sorted(set(opaque)))
            )
            info(
                "Inspect their source to find component ids: dku plugin download "
                "<plugin-id> (component dirs: custom-recipes/, python-agent-tools/, "
                "python-connectors/, python-steps/, python-triggers/, "
                "python-runnables/)."
            )
    except (SystemExit, typer.Exit):
        raise
    except Exception as e:
        handle_api_error(e)


@app.command("list-files")
def list_files(
    ctx: typer.Context,
    plugin_id: str = typer.Argument(help="Plugin ID"),
) -> None:
    """List files in a dev plugin (hierarchical tree)."""
    output = resolve_output_format()
    try:
        client = get_client_from_ctx(ctx)
        plugin = client.get_plugin(plugin_id)
        tree = plugin.list_files()

        # Flatten the tree into a list of paths
        data = []

        def _flatten(node, prefix=""):
            path = node.get("path", prefix + node.get("name", ""))
            children = node.get("children")
            if children:
                for child in children:
                    _flatten(child, path + "/" if path else "")
            else:
                data.append({"path": path, "name": node.get("name", "")})

        if isinstance(tree, list):
            for item in tree:
                _flatten(item)
        elif isinstance(tree, dict):
            _flatten(tree)

        render(
            data,
            ["path"],
            output_format=output,
            title=f"Files ({plugin_id})",
        )
    except Exception as e:
        handle_api_error(e)


@app.command("get-file")
def get_file(
    ctx: typer.Context,
    plugin_id: str = typer.Argument(help="Plugin ID"),
    path: str = typer.Option(..., "--path", help="File path within plugin"),
    output_file: str | None = typer.Option(
        None,
        "--output-file",
        "-O",
        help="Write raw bytes to this path (use for binary files like .zip/.gz/.png)",
    ),
) -> None:
    """Get the contents of a file in a dev plugin.

    Text files are printed to stdout. Binary files (.zip, .gz, .png, …) require
    --output-file PATH so bytes are written verbatim instead of decoded as UTF-8.
    """
    try:
        client = get_client_from_ctx(ctx)
        plugin = client.get_plugin(plugin_id)
        with plugin.get_file(path) as fp:
            content = fp.read()
        if output_file:
            from pathlib import Path

            data = content if isinstance(content, bytes) else content.encode("utf-8")
            Path(output_file).write_bytes(data)
            success(f"Wrote {len(data)} bytes to {output_file}")
            return
        if isinstance(content, bytes):
            try:
                print(content.decode("utf-8"))
            except UnicodeDecodeError:
                exit_with_error(
                    f"File is binary (UTF-8 decode failed at byte {content[:64].hex()}…).",
                    details=[
                        f"Re-run with: dku plugin get-file {plugin_id} --path {path} --output-file <local-path>",
                    ],
                )
        else:
            print(content)
    except Exception as e:
        handle_api_error(e)


@app.command("put-file")
def put_file(
    ctx: typer.Context,
    plugin_id: str = typer.Argument(help="Plugin ID"),
    path: str = typer.Option(..., "--path", help="File path within plugin"),
    content: str = typer.Option(
        ...,
        "--content",
        help="File content: literal string, @file.txt, or '-' for stdin",
    ),
) -> None:
    """Write content to a file in a dev plugin."""
    import io

    from dku_cli.helpers import read_text_input

    try:
        client = get_client_from_ctx(ctx)
        plugin = client.get_plugin(plugin_id)
        text = read_text_input(content)
        plugin.put_file(path, io.BytesIO(text.encode("utf-8")))
        success(f"Wrote {len(text)} bytes to {path} in plugin {plugin_id}")
    except Exception as e:
        handle_api_error(e)


@app.command("rename-file")
def rename_file(
    ctx: typer.Context,
    plugin_id: str = typer.Argument(help="Plugin ID (dev plugins only)"),
    path: str = typer.Option(
        ..., "--path", help="Current file/folder path within plugin"
    ),
    name: str = typer.Option(..., "--name", help="New name for the file/folder"),
) -> None:
    """Rename a file or folder in a dev plugin.

    Example:
      dku plugin rename-file my-plugin --path python-lib/old.py --name new.py
    """
    try:
        client = get_client_from_ctx(ctx)
        plugin = client.get_plugin(plugin_id)
        plugin.rename_file(path, name)
        success(f"Renamed '{path}' to '{name}' in plugin {plugin_id}")
    except Exception as e:
        handle_api_error(e)


@app.command("move-file")
def move_file(
    ctx: typer.Context,
    plugin_id: str = typer.Argument(help="Plugin ID (dev plugins only)"),
    path: str = typer.Option(
        ..., "--path", help="Current file/folder path within plugin"
    ),
    new_path: str = typer.Option(..., "--to", help="New path within plugin"),
) -> None:
    """Move a file or folder within a dev plugin.

    Example:
      dku plugin move-file my-plugin --path python-lib/utils.py --to python-lib/helpers/utils.py
    """
    try:
        client = get_client_from_ctx(ctx)
        plugin = client.get_plugin(plugin_id)
        plugin.move_file(path, new_path)
        success(f"Moved '{path}' to '{new_path}' in plugin {plugin_id}")
    except Exception as e:
        handle_api_error(e)


@app.command("install-from-store")
def install_from_store(
    ctx: typer.Context,
    plugin_id: str = typer.Argument(help="Plugin ID from the Dataiku plugin store"),
    wait: bool = typer.Option(
        True, "--wait/--no-wait", help="Wait for installation to complete"
    ),
) -> None:
    """Install a plugin from the Dataiku plugin store.

    After install, create a code environment if needed:
      dku plugin install-from-store my-plugin
      dku plugin create-code-env my-plugin

    Example:
      dku plugin install-from-store timeseries-preparation
    """
    try:
        client = get_client_from_ctx(ctx)
        info(f"Installing plugin '{plugin_id}' from store...")
        future = client.install_plugin_from_store(plugin_id)

        if wait:
            future.wait_for_result()
            success(f"Installed plugin '{plugin_id}' from store")
            info(f"Create code env if needed: dku plugin create-code-env {plugin_id}")
        else:
            success(f"Installation started for plugin '{plugin_id}'")
    except Exception as e:
        handle_api_error(e)


@app.command("install-from-git")
def install_from_git(
    ctx: typer.Context,
    repository_url: str = typer.Argument(help="Git repository URL"),
    checkout: str = typer.Option(
        "master", "--checkout", "-b", help="Branch, tag, or SHA1 to checkout"
    ),
    subpath: str | None = typer.Option(
        None,
        "--subpath",
        help="Path within the repo to use as plugin root (must contain plugin.json)",
    ),
    wait: bool = typer.Option(
        True, "--wait/--no-wait", help="Wait for installation to complete"
    ),
) -> None:
    """Install a plugin from a Git repository.

    DSS must be configured to allow access to the repository.

    Example:
      dku plugin install-from-git https://github.com/dataiku/dss-plugin-example.git
      dku plugin install-from-git git@github.com:org/repo.git --checkout v2.0
      dku plugin install-from-git https://github.com/org/monorepo.git --subpath plugins/my-plugin
    """
    try:
        client = get_client_from_ctx(ctx)
        info(f"Installing plugin from {repository_url} (checkout: {checkout})...")
        future = client.install_plugin_from_git(
            repository_url, checkout=checkout, subpath=subpath
        )

        if wait:
            future.wait_for_result()
            success(f"Installed plugin from {repository_url}")
            info("Check plugin ID: dku plugin list")
        else:
            success(f"Installation started from {repository_url}")
    except Exception as e:
        handle_api_error(e)


@app.command("update-from-store")
def update_from_store(
    ctx: typer.Context,
    plugin_id: str = typer.Argument(help="Plugin ID to update"),
    wait: bool = typer.Option(
        True, "--wait/--no-wait", help="Wait for update to complete"
    ),
) -> None:
    """Update an installed plugin from the Dataiku plugin store.

    The plugin must have been originally installed from the store.

    Example:
      dku plugin update-from-store timeseries-preparation
    """
    try:
        client = get_client_from_ctx(ctx)
        plugin = client.get_plugin(plugin_id)
        info(f"Updating plugin '{plugin_id}' from store...")
        future = plugin.update_from_store()

        if wait:
            future.wait_for_result()
            success(f"Updated plugin '{plugin_id}' from store")
        else:
            success(f"Update started for plugin '{plugin_id}'")
    except Exception as e:
        handle_api_error(e)


@app.command("update-from-git")
def update_from_git(
    ctx: typer.Context,
    plugin_id: str = typer.Argument(help="Plugin ID to update"),
    repository_url: str = typer.Argument(help="Git repository URL"),
    checkout: str = typer.Option(
        "master", "--checkout", "-b", help="Branch, tag, or SHA1 to checkout"
    ),
    subpath: str | None = typer.Option(
        None,
        "--subpath",
        help="Path within the repo to use as plugin root (must contain plugin.json)",
    ),
    wait: bool = typer.Option(
        True, "--wait/--no-wait", help="Wait for update to complete"
    ),
) -> None:
    """Update an installed plugin from a Git repository.

    Example:
      dku plugin update-from-git my-plugin https://github.com/org/repo.git
      dku plugin update-from-git my-plugin git@github.com:org/repo.git --checkout v2.1
    """
    try:
        client = get_client_from_ctx(ctx)
        plugin = client.get_plugin(plugin_id)
        info(
            f"Updating plugin '{plugin_id}' from {repository_url} (checkout: {checkout})..."
        )
        future = plugin.update_from_git(
            repository_url, checkout=checkout, subpath=subpath
        )

        if wait:
            future.wait_for_result()
            success(f"Updated plugin '{plugin_id}' from {repository_url}")
        else:
            success(f"Update started for plugin '{plugin_id}'")
    except Exception as e:
        handle_api_error(e)


@app.command()
def download(
    ctx: typer.Context,
    plugin_id: str = typer.Argument(help="Plugin ID to download"),
    dest: str = typer.Option(
        None,
        "--dest",
        "-d",
        help="Destination file path (default: <plugin_id>.zip)",
    ),
) -> None:
    """Download a plugin as a ZIP archive.

    Useful for backup, migration, or local inspection.

    Example:
      dku plugin download my-plugin
      dku plugin download my-plugin --dest ./backup/my-plugin-v2.zip
    """
    from pathlib import Path

    output_path = dest or f"{plugin_id}.zip"
    try:
        client = get_client_from_ctx(ctx)
        client.download_plugin_to_file(plugin_id, output_path)
        file_size = Path(output_path).stat().st_size
        size_kb = file_size / 1024
        success(f"Downloaded plugin '{plugin_id}' to {output_path} ({size_kb:.1f} KB)")
    except Exception as e:
        handle_api_error(e)
