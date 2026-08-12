"""Dataiku plugin development and lifecycle tools."""

from __future__ import annotations

import json
import os
import re
import tempfile
from typing import Any
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from fastmcp import Context

from .. import mcp
from .utils.async_executor import run_blocking
from .utils.auth import get_dss_client
from .utils.serialization import columnar, compact_json
from .utils.validation import require_non_empty_string

_PLUGIN_ID = re.compile(r"^[A-Za-z0-9_-]+$")
_EXCLUDED_PARTS = {".git", ".venv", "__pycache__", ".pytest_cache", ".DS_Store"}
_CODE_RECIPE_TYPES = {"python", "cpython"}
_COMPONENT_TEMPLATES = {
    "custom-recipes": ("recipe", "recipe.json", "recipe.py"),
    "python-connectors": ("connector", "connector.json", "connector.py"),
    "webapps": ("webapp", "webapp.json", "backend.py"),
    "python-runnables": ("runnable", "runnable.json", "runnable.py"),
    "python-agent-tools": ("tool", "tool.json", "tool.py"),
    "python-agents": ("agent", "agent.json", "agent.py"),
    "python-guardrails": ("guardrail", "guardrail.json", "guardrail.py"),
    "python-structured-agent-blocks": ("block", "block.json", "block.py"),
    "custom-steps": ("processor", "processor.json", "processor.py"),
    "python-formats": ("format", "format.json", "format.py"),
    "python-fs-providers": ("fsprovider", "fsprovider.json", "fsprovider.py"),
    "python-probes": ("probe", "probe.json", "probe.py"),
    "python-checks": ("check", "check.json", "check.py"),
    "python-steps": ("step", "step.json", "step.py"),
    "python-triggers": ("trigger", "trigger.json", "trigger.py"),
    "parameter-sets": ("parameterset", "parameterset.json", None),
}


def _plugin_id(value: str) -> str:
    value = value.strip()
    if not value or not _PLUGIN_ID.fullmatch(value):
        raise ValueError("plugin_id must contain only letters, numbers, '_' or '-'")
    return value


def _meta(value) -> dict:
    if isinstance(value, dict):
        return value
    return {k: getattr(value, k) for k in ("id", "plugin_id", "version", "dev", "isDev") if hasattr(value, k)}


def _plugin_meta(value) -> dict:
    raw = _meta(value)
    return {
        "id": raw.get("id", raw.get("plugin_id", "")),
        "version": raw.get("version", ""),
        "dev": raw.get("dev", raw.get("isDev", False)),
    }


def _read_manifest(root: Path) -> dict:
    manifest = root / "plugin.json"
    if not manifest.is_file():
        raise ValueError(f"Plugin root does not contain plugin.json: {root}")
    try:
        value = json.loads(manifest.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"plugin.json is not valid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError("plugin.json must contain a JSON object")
    return value


def _validate_root(root: Path) -> list[dict]:
    findings: list[dict] = []
    try:
        manifest = _read_manifest(root)
    except ValueError as exc:
        return [{"severity": "error", "path": "plugin.json", "message": str(exc)}]
    plugin_id = manifest.get("id")
    if not isinstance(plugin_id, str) or not _PLUGIN_ID.fullmatch(plugin_id):
        findings.append({"severity": "error", "path": "plugin.json", "message": "id must match [A-Za-z0-9_-]+"})
    if not isinstance(manifest.get("version"), str) or not manifest["version"].strip():
        findings.append({"severity": "error", "path": "plugin.json", "message": "version must be a non-empty string"})
    for component_dir, (_, descriptor, implementation) in _COMPONENT_TEMPLATES.items():
        folder = root / component_dir
        if not folder.is_dir():
            continue
        for component in folder.iterdir():
            if component.is_dir():
                if not (component / descriptor).is_file():
                    findings.append({"severity": "error", "path": str((component / descriptor).relative_to(root)), "message": f"missing {descriptor}"})
                if implementation and not (component / implementation).is_file():
                    findings.append({"severity": "error", "path": str((component / implementation).relative_to(root)), "message": f"missing {implementation}"})
    for path in root.rglob("*"):
        if path.is_file() and any(part in _EXCLUDED_PARTS for part in path.parts):
            findings.append({"severity": "warning", "path": str(path.relative_to(root)), "message": "excluded build artifact or cache"})
    return findings


def _zip_plugin(root: Path, destination: Path) -> dict:
    findings = _validate_root(root)
    if any(f["severity"] == "error" for f in findings):
        raise ValueError(compact_json({"valid": False, "findings": findings}))
    destination.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(destination, "w", ZIP_DEFLATED) as archive:
        for path in sorted(root.rglob("*")):
            if not path.is_file() or any(part in _EXCLUDED_PARTS for part in path.parts):
                continue
            archive.write(path, path.relative_to(root).as_posix())
    return {"valid": True, "plugin": _read_manifest(root), "archive": str(destination), "findings": findings}


def _local_path(root: Path, relative_path: str) -> Path:
    relative = Path(require_non_empty_string(relative_path, "path"))
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("path must be relative and cannot escape the plugin root")
    return (root / relative).resolve()


def _recipe_roles(raw_roles: dict | None, direction: str) -> list[dict[str, Any]]:
    roles = []
    for role_name, role in (raw_roles or {}).items():
        items = role.get("items", []) if isinstance(role, dict) else []
        types = {
            item.get("type")
            for item in items
            if isinstance(item, dict) and item.get("type")
        }
        roles.append(
            {
                "name": role_name,
                "label": role_name,
                "description": f"{direction.title()} role from the converted Python recipe",
                "arity": "NARY" if len(items) != 1 else "UNARY",
                "required": bool(items),
                "acceptsDataset": "DATASET" in types or not types,
                "acceptsManagedFolder": "MANAGED_FOLDER" in types,
                "acceptsSavedModel": "SAVED_MODEL" in types,
            }
        )
    return roles


def _conversion_files(
    manifest: dict,
    recipe_id: str,
    recipe_label: str,
    code: str,
    inputs: dict,
    outputs: dict,
    parameters: list[dict] | None,
) -> tuple[dict, str, list[str]]:
    warnings = []
    if 'dataiku.Dataset("' in code or "dataiku.Dataset('" in code:
        warnings.append("Python source contains explicit dataiku.Dataset names; review it and use customrecipe role helpers for reusable inputs and outputs.")
    if not parameters:
        warnings.append("No plugin parameters were supplied; the converted recipe exposes no configurable parameters.")
    descriptor = {
        "meta": {"label": recipe_label, "description": f"Converted from Python recipe {recipe_id}"},
        "kind": "PYTHON",
        "inputRoles": _recipe_roles(inputs, "input"),
        "outputRoles": _recipe_roles(outputs, "output"),
        "params": parameters or [],
    }
    recipe_code = (
        "# Converted from Dataiku Python recipe: " + recipe_id + "\n"
        "# Review input/output references before distributing this plugin.\n\n"
        + code
    )
    return descriptor, recipe_code, warnings


@mcp.tool()
async def list_plugins(ctx: Context) -> str:
    """List installed Dataiku plugins."""
    items = await run_blocking(lambda: get_dss_client().list_plugins())
    rows = [_plugin_meta(item) for item in items]
    return compact_json(columnar(rows, ["id", "version", "dev"]))


@mcp.tool()
async def get_plugin(ctx: Context, plugin_id: str) -> str:
    """Get installed plugin metadata, settings, and code-environment binding."""
    plugin_id = _plugin_id(plugin_id)

    def _run():
        client = get_dss_client()
        found = next((p for p in client.list_plugins() if _plugin_meta(p)["id"] == plugin_id), None)
        if found is None:
            raise ValueError(f"Plugin '{plugin_id}' is not installed")
        plugin = client.get_plugin(plugin_id)
        result = _plugin_meta(found)
        try:
            raw = plugin.get_settings().get_raw()
            result["codeEnvName"] = raw.get("codeEnvName", "")
            result["config"] = {k: ("****" if any(s in k.lower() for s in ("password", "secret", "key")) else v) for k, v in raw.get("config", {}).items()}
        except Exception:
            result["settings"] = "unavailable"
        return result

    return compact_json(await run_blocking(_run))


@mcp.tool()
async def list_plugin_files(ctx: Context, plugin_id: str) -> str:
    """List files in a DSS development plugin."""
    plugin_id = _plugin_id(plugin_id)
    tree = await run_blocking(lambda: get_dss_client().get_plugin(plugin_id).list_files())
    return compact_json(tree)


@mcp.tool()
async def get_plugin_file(ctx: Context, plugin_id: str, path: str) -> str:
    """Read a text file from a DSS development plugin."""
    plugin_id = _plugin_id(plugin_id)
    path = Path(require_non_empty_string(path, "path"))
    if path.is_absolute() or ".." in path.parts or not path.as_posix():
        raise ValueError("path must be a relative plugin path")
    plugin = await run_blocking(lambda: get_dss_client().get_plugin(plugin_id))
    def _read():
        with plugin.get_file(path.as_posix()) as file_handle:
            return file_handle.read().decode("utf-8")

    content = await run_blocking(_read)
    return compact_json({"pluginId": plugin_id, "path": path.as_posix(), "content": content})


@mcp.tool()
async def put_plugin_file(ctx: Context, plugin_id: str, path: str, content: str) -> str:
    """Write a UTF-8 file in a DSS development plugin."""
    plugin_id = _plugin_id(plugin_id)
    path = Path(require_non_empty_string(path, "path"))
    if path.is_absolute() or ".." in path.parts:
        raise ValueError("path must be a relative plugin path")

    def _run():
        import io

        get_dss_client().get_plugin(plugin_id).put_file(
            path.as_posix(), io.BytesIO(content.encode("utf-8"))
        )

    await run_blocking(_run)
    return compact_json({"pluginId": plugin_id, "path": path.as_posix(), "written": True})


@mcp.tool()
async def rename_plugin_file(ctx: Context, plugin_id: str, path: str, new_name: str) -> str:
    """Rename a file or directory in a DSS development plugin."""
    plugin_id = _plugin_id(plugin_id)
    path = require_non_empty_string(path, "path")
    new_name = require_non_empty_string(new_name, "new_name")
    if Path(path).is_absolute() or ".." in Path(path).parts or "/" in new_name:
        raise ValueError("path must be relative and new_name must be a single component")
    await run_blocking(lambda: get_dss_client().get_plugin(plugin_id).rename_file(path, new_name))
    return compact_json({"pluginId": plugin_id, "path": path, "newName": new_name, "renamed": True})


@mcp.tool()
async def move_plugin_file(ctx: Context, plugin_id: str, path: str, new_path: str) -> str:
    """Move a file or directory in a DSS development plugin."""
    plugin_id = _plugin_id(plugin_id)
    path = require_non_empty_string(path, "path")
    new_path = require_non_empty_string(new_path, "new_path")
    for candidate in (path, new_path):
        if Path(candidate).is_absolute() or ".." in Path(candidate).parts:
            raise ValueError("plugin paths must be relative and cannot escape the plugin root")
    await run_blocking(lambda: get_dss_client().get_plugin(plugin_id).move_file(path, new_path))
    return compact_json({"pluginId": plugin_id, "path": path, "newPath": new_path, "moved": True})


@mcp.tool()
async def download_plugin(ctx: Context, plugin_id: str, output_path: str) -> str:
    """Download an installed plugin as a ZIP archive."""
    plugin_id = _plugin_id(plugin_id)
    output = Path(require_non_empty_string(output_path, "output_path")).expanduser().resolve()
    await run_blocking(lambda: get_dss_client().download_plugin_to_file(plugin_id, str(output)))
    return compact_json({"pluginId": plugin_id, "archive": str(output)})


@mcp.tool()
async def get_plugin_settings(ctx: Context, plugin_id: str, project_key: str | None = None) -> str:
    """Get instance-level or project-level plugin settings with secrets masked."""
    plugin_id = _plugin_id(plugin_id)

    def _run():
        plugin = get_dss_client().get_plugin(plugin_id)
        settings = plugin.get_project_settings(project_key) if project_key else plugin.get_settings()
        raw = dict(settings.get_raw())
        raw["config"] = {k: ("****" if any(s in k.lower() for s in ("password", "secret", "key", "token")) else v) for k, v in raw.get("config", {}).items()}
        return raw

    return compact_json(await run_blocking(_run))


@mcp.tool()
async def set_plugin_settings(ctx: Context, plugin_id: str, settings: dict, project_key: str | None = None) -> str:
    """Replace plugin settings with a caller-supplied settings object."""
    plugin_id = _plugin_id(plugin_id)
    if not isinstance(settings, dict):
        raise ValueError("settings must be an object returned by get_plugin_settings")

    def _run():
        plugin = get_dss_client().get_plugin(plugin_id)
        target = plugin.get_project_settings(project_key) if project_key else plugin.get_settings()
        current = target.get_raw()
        current.clear()
        current.update(settings)
        target.save()

    await run_blocking(_run)
    return compact_json({"pluginId": plugin_id, "projectKey": project_key, "saved": True})


@mcp.tool()
async def scaffold_plugin(ctx: Context, plugin_id: str, path: str, version: str = "0.1.0", components: list[str] | None = None) -> str:
    """Create a canonical local Dataiku plugin skeleton."""
    plugin_id = _plugin_id(plugin_id)
    root = Path(require_non_empty_string(path, "path")).expanduser().resolve()
    components = components or []
    allowed_components = set(_COMPONENT_TEMPLATES)
    invalid_components = sorted(set(components) - allowed_components)
    if invalid_components:
        raise ValueError(f"Unsupported component directory: {invalid_components}")
    def _run():
        if root.exists() and any(root.iterdir()):
            raise ValueError(f"Refusing to scaffold into a non-empty directory: {root}")
        root.mkdir(parents=True, exist_ok=True)
        manifest = {"id": plugin_id, "version": version, "meta": {"label": plugin_id, "description": ""}}
        (root / "plugin.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        (root / "python-lib" / plugin_id.replace("-", "_")).mkdir(parents=True)
        (root / "code-env" / "python" / "spec").mkdir(parents=True)
        (root / "code-env" / "python" / "desc.json").write_text(json.dumps({"acceptedPythonInterpreters": ["PYTHON3"], "installCorePackages": True}, indent=2) + "\n", encoding="utf-8")
        (root / "code-env" / "python" / "spec" / "requirements.txt").write_text("", encoding="utf-8")
        for component in components:
            (root / component).mkdir(parents=True, exist_ok=True)
        return manifest

    manifest = await run_blocking(_run)
    return compact_json({"path": str(root), "manifest": manifest, "components": components or []})


@mcp.tool()
async def validate_plugin(ctx: Context, path: str) -> str:
    """Validate a local Dataiku plugin directory."""
    root = Path(require_non_empty_string(path, "path")).expanduser().resolve()
    findings = await run_blocking(lambda: _validate_root(root))
    return compact_json({"valid": not any(f["severity"] == "error" for f in findings), "path": str(root), "findings": findings})


@mcp.tool()
async def package_plugin(ctx: Context, path: str, output_path: str) -> str:
    """Validate and package a local plugin with plugin.json at ZIP root."""
    root = Path(require_non_empty_string(path, "path")).expanduser().resolve()
    destination = Path(require_non_empty_string(output_path, "output_path")).expanduser().resolve()
    result = await run_blocking(_zip_plugin, root, destination)
    return compact_json(result)


def _archive_for_source(source: Path) -> tuple[Path, bool]:
    if source.is_dir():
        descriptor, name = tempfile.mkstemp(suffix=".zip")
        os.close(descriptor)
        temp = Path(name)
        _zip_plugin(source, temp)
        return temp, True
    if source.is_file() and source.suffix.lower() == ".zip":
        return source, False
    raise ValueError("source must be a plugin directory or .zip archive")


@mcp.tool()
async def install_plugin(ctx: Context, source: str, update_existing: bool = True) -> str:
    """Install a local plugin directory/ZIP, or update it when already installed."""
    source_path = Path(require_non_empty_string(source, "source")).expanduser().resolve()

    def _run():
        archive, temporary = _archive_for_source(source_path)
        try:
            with ZipFile(archive) as zf:
                if "plugin.json" not in zf.namelist():
                    raise ValueError("plugin archive must contain plugin.json at its root")
                manifest = json.loads(zf.read("plugin.json"))
            plugin_id = _plugin_id(str(manifest.get("id", "")))
            client = get_dss_client()
            installed = { _plugin_meta(p)["id"] for p in client.list_plugins() }
            with archive.open("rb") as fp:
                if update_existing and plugin_id in installed:
                    client.get_plugin(plugin_id).update_from_zip(fp)
                    action = "updated"
                else:
                    client.install_plugin_from_archive(fp)
                    action = "installed"
            return {"pluginId": plugin_id, "version": manifest.get("version", ""), "action": action}
        finally:
            if temporary:
                archive.unlink(missing_ok=True)

    return compact_json(await run_blocking(_run))


def _wait_future(result):
    if hasattr(result, "wait_for_result"):
        return result.wait_for_result()
    return result


@mcp.tool()
async def install_plugin_from_store(ctx: Context, plugin_id: str) -> str:
    """Install a plugin from the Dataiku Plugin Store."""
    plugin_id = _plugin_id(plugin_id)
    result = await run_blocking(lambda: _wait_future(get_dss_client().install_plugin_from_store(plugin_id)))
    return compact_json({"pluginId": plugin_id, "source": "store", "result": result})


@mcp.tool()
async def install_plugin_from_git(ctx: Context, repository_url: str, checkout: str = "master", subpath: str | None = None) -> str:
    """Install a plugin from a Git repository configured for DSS access."""
    repository_url = require_non_empty_string(repository_url, "repository_url")
    checkout = require_non_empty_string(checkout, "checkout")
    result = await run_blocking(lambda: _wait_future(get_dss_client().install_plugin_from_git(repository_url, checkout, subpath)))
    return compact_json({"repositoryUrl": repository_url, "checkout": checkout, "subpath": subpath, "source": "git", "result": result})


@mcp.tool()
async def update_plugin_from_store(ctx: Context, plugin_id: str) -> str:
    """Update an installed Plugin Store plugin."""
    plugin_id = _plugin_id(plugin_id)
    result = await run_blocking(lambda: _wait_future(get_dss_client().get_plugin(plugin_id).update_from_store()))
    return compact_json({"pluginId": plugin_id, "source": "store", "result": result})


@mcp.tool()
async def update_plugin_from_git(ctx: Context, plugin_id: str, repository_url: str, checkout: str = "master", subpath: str | None = None) -> str:
    """Update an installed Git-backed plugin."""
    plugin_id = _plugin_id(plugin_id)
    repository_url = require_non_empty_string(repository_url, "repository_url")
    checkout = require_non_empty_string(checkout, "checkout")
    result = await run_blocking(lambda: _wait_future(get_dss_client().get_plugin(plugin_id).update_from_git(repository_url, checkout, subpath)))
    return compact_json({"pluginId": plugin_id, "repositoryUrl": repository_url, "checkout": checkout, "subpath": subpath, "source": "git", "result": result})


@mcp.tool()
async def get_plugin_usages(ctx: Context, plugin_id: str, project_key: str | None = None) -> str:
    """List project assets using a plugin."""
    plugin_id = _plugin_id(plugin_id)
    plugin = await run_blocking(lambda: get_dss_client().get_plugin(plugin_id))
    usage = await run_blocking(lambda: plugin.list_usages(project_key=project_key))
    return compact_json(usage.get_raw() if hasattr(usage, "get_raw") else usage)


@mcp.tool()
async def create_plugin_code_env(ctx: Context, plugin_id: str) -> str:
    """Create the managed code environment for an installed plugin."""
    plugin_id = _plugin_id(plugin_id)
    result = await run_blocking(lambda: get_dss_client().get_plugin(plugin_id).create_code_env())
    if hasattr(result, "wait_for_result"):
        result = await run_blocking(result.wait_for_result)
    return compact_json({"pluginId": plugin_id, "result": result})


@mcp.tool()
async def set_plugin_code_env(ctx: Context, plugin_id: str, env_name: str) -> str:
    """Assign an existing code environment to an installed plugin."""
    plugin_id = _plugin_id(plugin_id)
    def _run():
        settings = get_dss_client().get_plugin(plugin_id).get_settings()
        settings.set_code_env(require_non_empty_string(env_name, "env_name"))
        settings.save()

    await run_blocking(_run)
    return compact_json({"pluginId": plugin_id, "codeEnvName": env_name})


@mcp.tool()
async def update_plugin_code_env(ctx: Context, plugin_id: str) -> str:
    """Rebuild an installed plugin's managed code environment."""
    plugin_id = _plugin_id(plugin_id)
    result = await run_blocking(lambda: get_dss_client().get_plugin(plugin_id).update_code_env())
    if hasattr(result, "wait_for_result"):
        result = await run_blocking(result.wait_for_result)
    return compact_json({"pluginId": plugin_id, "result": result})


@mcp.tool()
async def delete_plugin(ctx: Context, plugin_id: str, force: bool = False) -> str:
    """Delete an installed plugin after the caller's confirmation step."""
    plugin_id = _plugin_id(plugin_id)
    plugin = await run_blocking(lambda: get_dss_client().get_plugin(plugin_id))
    usages = await run_blocking(lambda: plugin.list_usages())
    raw = usages.get_raw() if hasattr(usages, "get_raw") else {}
    if raw.get("usages") and not force:
        raise ValueError("Plugin is in use; inspect get_plugin_usages or set force=true")
    result = await run_blocking(lambda: plugin.delete(force=force))
    if hasattr(result, "wait_for_result"):
        await run_blocking(result.wait_for_result)
    return compact_json({"pluginId": plugin_id, "deleted": True, "force": force})


@mcp.tool()
async def read_local_plugin_file(ctx: Context, plugin_root: str, path: str) -> str:
    """Read a UTF-8 text file from a local plugin directory."""
    root = Path(require_non_empty_string(plugin_root, "plugin_root")).expanduser().resolve()
    file_path = _local_path(root, path)
    content = await run_blocking(lambda: file_path.read_text(encoding="utf-8"))
    return compact_json({"path": str(file_path), "content": content})


@mcp.tool()
async def write_local_plugin_file(ctx: Context, plugin_root: str, path: str, content: str, overwrite: bool = False) -> str:
    """Write a UTF-8 text file inside a local plugin directory."""
    root = Path(require_non_empty_string(plugin_root, "plugin_root")).expanduser().resolve()
    file_path = _local_path(root, path)

    def _run():
        if file_path.exists() and not overwrite:
            raise ValueError(f"File already exists; set overwrite=true: {file_path}")
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")

    await run_blocking(_run)
    return compact_json({"path": str(file_path), "written": True})


@mcp.tool()
async def move_local_plugin_file(ctx: Context, plugin_root: str, source_path: str, destination_path: str, overwrite: bool = False) -> str:
    """Move a file within a local plugin directory."""
    root = Path(require_non_empty_string(plugin_root, "plugin_root")).expanduser().resolve()
    source = _local_path(root, source_path)
    destination = _local_path(root, destination_path)

    def _run():
        if not source.is_file():
            raise ValueError(f"Source file does not exist: {source}")
        if destination.exists() and not overwrite:
            raise ValueError(f"Destination exists; set overwrite=true: {destination}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        source.replace(destination)

    await run_blocking(_run)
    return compact_json({"source": str(source), "destination": str(destination), "moved": True})


@mcp.tool()
async def delete_local_plugin_file(ctx: Context, plugin_root: str, path: str) -> str:
    """Delete one file from a local plugin directory."""
    root = Path(require_non_empty_string(plugin_root, "plugin_root")).expanduser().resolve()
    file_path = _local_path(root, path)
    await run_blocking(lambda: file_path.unlink())
    return compact_json({"path": str(file_path), "deleted": True})


@mcp.tool()
async def convert_python_recipe_to_plugin(
    ctx: Context,
    project_key: str,
    recipe_name: str,
    plugin_root: str,
    plugin_id: str,
    plugin_recipe_id: str | None = None,
    plugin_version: str = "0.1.0",
    parameters: list[dict] | None = None,
    overwrite: bool = False,
) -> str:
    """Convert a live Python recipe into a local plugin recipe component.

    This mirrors DSS's native conversion layout while leaving the source recipe
    unchanged. The generated component must be reviewed before packaging.
    """
    plugin_id = _plugin_id(plugin_id)
    project_key = require_non_empty_string(project_key, "project_key")
    recipe_name = require_non_empty_string(recipe_name, "recipe_name")
    root = Path(require_non_empty_string(plugin_root, "plugin_root")).expanduser().resolve()
    recipe_id = _plugin_id(plugin_recipe_id or recipe_name.replace(" ", "-").lower())

    def _run():
        settings = get_dss_client().get_project(project_key).get_recipe(recipe_name).get_settings()
        raw_type = settings.get_recipe_raw_definition().get("type", "")
        if raw_type not in _CODE_RECIPE_TYPES:
            raise ValueError(f"Recipe '{recipe_name}' is type '{raw_type}', not a Python recipe")
        code = settings.get_code()
        descriptor, recipe_code, warnings = _conversion_files(
            {"id": plugin_id, "version": plugin_version},
            recipe_name,
            recipe_name,
            code,
            settings.get_recipe_inputs(),
            settings.get_recipe_outputs(),
            parameters,
        )
        manifest_path = root / "plugin.json"
        if manifest_path.exists():
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            if manifest.get("id") != plugin_id:
                raise ValueError(f"Existing plugin.json has id '{manifest.get('id')}', expected '{plugin_id}'")
        else:
            if root.exists() and any(root.iterdir()) and not overwrite:
                raise ValueError(f"Plugin root is non-empty and has no plugin.json: {root}")
            root.mkdir(parents=True, exist_ok=True)
            manifest = {"id": plugin_id, "version": plugin_version, "meta": {"label": plugin_id, "description": ""}}
            manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        component = root / "custom-recipes" / recipe_id
        if component.exists() and not overwrite:
            raise ValueError(f"Plugin recipe component already exists: {component}")
        component.mkdir(parents=True, exist_ok=True)
        (component / "recipe.json").write_text(json.dumps(descriptor, indent=2) + "\n", encoding="utf-8")
        (component / "recipe.py").write_text(recipe_code, encoding="utf-8")
        return {"pluginId": plugin_id, "recipeId": recipe_id, "root": str(root), "descriptor": descriptor, "warnings": warnings}

    return compact_json(await run_blocking(_run))


@mcp.tool()
async def convert_webapp_to_plugin(
    ctx: Context,
    project_key: str,
    webapp_id: str,
    plugin_root: str,
    plugin_id: str,
    component_id: str | None = None,
    overwrite: bool = False,
) -> str:
    """Export a live WebApp into a local plugin webapp component."""
    plugin_id = _plugin_id(plugin_id)
    project_key = require_non_empty_string(project_key, "project_key")
    webapp_id = require_non_empty_string(webapp_id, "webapp_id")
    root = Path(require_non_empty_string(plugin_root, "plugin_root")).expanduser().resolve()
    component_id = _plugin_id(component_id or webapp_id.replace(" ", "-").lower())

    def _run():
        settings = get_dss_client().get_project(project_key).get_webapp(webapp_id).get_settings().get_raw()
        webapp_type = settings.get("type", "STANDARD")
        params = settings.get("params", {}) or {}
        component = root / "webapps" / component_id
        if component.exists() and not overwrite:
            raise ValueError(f"Plugin webapp component already exists: {component}")
        root.mkdir(parents=True, exist_ok=True)
        manifest_path = root / "plugin.json"
        if not manifest_path.exists():
            manifest_path.write_text(json.dumps({"id": plugin_id, "version": "0.1.0", "meta": {"label": plugin_id, "description": ""}}, indent=2) + "\n", encoding="utf-8")
        elif json.loads(manifest_path.read_text(encoding="utf-8")).get("id") != plugin_id:
            raise ValueError("Existing plugin.json belongs to a different plugin")
        component.mkdir(parents=True, exist_ok=True)
        descriptor = {"meta": {"label": settings.get("name", webapp_id), "description": "Converted from a Dataiku WebApp"}, "kind": webapp_type, "params": params.get("params", []) if isinstance(params, dict) else []}
        (component / "webapp.json").write_text(json.dumps(descriptor, indent=2) + "\n", encoding="utf-8")
        files = params.get("files", {}) if isinstance(params, dict) else {}
        if not files and isinstance(params, dict):
            files = {name: params[name] for name in ("app.js", "body.html", "style.css", "backend.py", "server.R", "ui.R") if isinstance(params.get(name), str)}
        if not files and isinstance(params, dict):
            source = params.get("python")
            if isinstance(source, str):
                files = {"backend.py": source}
        for name, content in files.items():
            relative = _local_path(component, str(name))
            if relative != component and not str(relative).startswith(str(component) + "/"):
                raise ValueError("WebApp file path escapes the component directory")
            relative.parent.mkdir(parents=True, exist_ok=True)
            relative.write_text(str(content), encoding="utf-8")
        return {"pluginId": plugin_id, "componentId": component_id, "webappType": webapp_type, "root": str(root), "files": sorted(files)}

    return compact_json(await run_blocking(_run))
