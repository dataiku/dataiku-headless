"""Unit tests for local plugin development helpers."""

import asyncio
import io
import json
from pathlib import Path
from zipfile import ZipFile

from dataiku_mcp.tools import plugins
from tests.utils.fakes import FakeContext


def _result(coro):
    return json.loads(asyncio.run(coro))


def test_scaffold_validate_and_package_plugin(tmp_path):
    root = tmp_path / "demo"
    result = _result(
        plugins.scaffold_plugin(
            FakeContext(), "demo-plugin", str(root), components=["custom-recipes"]
        )
    )
    assert result["manifest"]["id"] == "demo-plugin"
    assert _result(plugins.validate_plugin(FakeContext(), str(root)))["valid"]

    archive = tmp_path / "demo.zip"
    packaged = _result(plugins.package_plugin(FakeContext(), str(root), str(archive)))
    assert packaged["valid"]
    with ZipFile(archive) as zip_file:
        assert "plugin.json" in zip_file.namelist()
        assert "custom-recipes" not in zip_file.namelist()


def test_local_file_operations_are_root_confined(tmp_path):
    root = tmp_path / "plugin"
    _result(plugins.scaffold_plugin(FakeContext(), "demo", str(root)))
    _result(plugins.write_local_plugin_file(FakeContext(), str(root), "README.md", "hello"))
    assert _result(plugins.read_local_plugin_file(FakeContext(), str(root), "README.md"))["content"] == "hello"
    _result(plugins.move_local_plugin_file(FakeContext(), str(root), "README.md", "docs/README.md"))
    _result(plugins.delete_local_plugin_file(FakeContext(), str(root), "docs/README.md"))


def test_invalid_plugin_id_is_rejected(tmp_path):
    try:
        asyncio.run(plugins.scaffold_plugin(FakeContext(), "bad/id", str(tmp_path / "plugin")))
    except ValueError as exc:
        assert "plugin_id" in str(exc)
    else:
        raise AssertionError("invalid plugin id was accepted")


class _Future:
    def __init__(self, result=None):
        self.result = result
        self.waited = False

    def wait_for_result(self):
        self.waited = True
        return self.result


class _Settings:
    def __init__(self, raw):
        self.raw = raw
        self.saved = False

    def get_raw(self):
        return self.raw

    def set_code_env(self, name):
        self.raw["codeEnvName"] = name

    def save(self):
        self.saved = True


class _Usage:
    def __init__(self, raw):
        self.raw = raw

    def get_raw(self):
        return self.raw


class _Plugin:
    def __init__(self, plugin_id="demo"):
        self.plugin_id = plugin_id
        self.settings = _Settings(
            {"codeEnvName": "", "config": {"apiKey": "secret", "label": "demo"}}
        )
        self.files = {"README.md": b"hello"}
        self.calls = []
        self.usages = _Usage({"usages": [], "missingTypes": []})

    def get_settings(self):
        return self.settings

    def get_project_settings(self, project_key):
        self.calls.append(("project_settings", project_key))
        return self.settings

    def list_files(self):
        return [{"name": "README.md", "path": "README.md"}]

    def get_file(self, path):
        return io.BytesIO(self.files[path])

    def put_file(self, path, file_handle):
        self.files[path] = file_handle.read()
        self.calls.append(("put_file", path))

    def rename_file(self, path, new_name):
        self.files[new_name] = self.files.pop(path)
        self.calls.append(("rename_file", path, new_name))

    def move_file(self, path, new_path):
        self.files[new_path] = self.files.pop(path)
        self.calls.append(("move_file", path, new_path))

    def list_usages(self, project_key=None):
        self.calls.append(("usages", project_key))
        return self.usages

    def create_code_env(self):
        self.calls.append(("create_code_env",))
        return _Future({"envName": "plugin_demo"})

    def update_code_env(self):
        self.calls.append(("update_code_env",))
        return _Future({"updated": True})

    def delete(self, force=False):
        self.calls.append(("delete", force))
        return _Future()

    def update_from_zip(self, file_handle):
        self.calls.append(("update_from_zip", file_handle.read()))

    def update_from_store(self):
        self.calls.append(("update_from_store",))
        return _Future({"updated": True})

    def update_from_git(self, repository_url, checkout, subpath):
        self.calls.append(("update_from_git", repository_url, checkout, subpath))
        return _Future({"updated": True})


class _RecipeSettings:
    def get_recipe_raw_definition(self):
        return {"type": "python"}

    def get_code(self):
        return 'import dataiku\ndataiku.Dataset("input").get_dataframe()\n'

    def get_recipe_inputs(self):
        return {"main": {"items": [{"type": "DATASET", "ref": "input"}]}}

    def get_recipe_outputs(self):
        return {"main": {"items": [{"type": "DATASET", "ref": "output"}]}}


class _Recipe:
    def get_settings(self):
        return _RecipeSettings()


class _WebAppSettings:
    def get_raw(self):
        return {
            "name": "Demo WebApp",
            "type": "STANDARD",
            "params": {"files": {"body.html": "<h1>demo</h1>", "app.js": "console.log('demo')"}},
        }


class _WebApp:
    def get_settings(self):
        return _WebAppSettings()


class _Client:
    def __init__(self):
        self.plugin = _Plugin()
        self.calls = []

    def list_plugins(self):
        return [{"id": "demo", "version": "1.0.0", "isDev": True}]

    def get_plugin(self, plugin_id):
        assert plugin_id == "demo"
        return self.plugin

    def install_plugin_from_archive(self, file_handle):
        self.calls.append(("install_archive", file_handle.read()))

    def install_plugin_from_store(self, plugin_id):
        self.calls.append(("install_store", plugin_id))
        return _Future({"installed": True})

    def install_plugin_from_git(self, repository_url, checkout, subpath):
        self.calls.append(("install_git", repository_url, checkout, subpath))
        return _Future({"installed": True})

    def download_plugin_to_file(self, plugin_id, path):
        Path(path).write_bytes(b"plugin archive")
        self.calls.append(("download", plugin_id, path))

    def get_project(self, project_key):
        assert project_key == "P"

        class Project:
            def get_recipe(self, name):
                assert name == "recipe"
                return _Recipe()

            def get_webapp(self, webapp_id):
                assert webapp_id == "webapp"
                return _WebApp()

        return Project()


def test_dss_plugin_file_settings_and_download_tools(monkeypatch, tmp_path):
    client = _Client()
    monkeypatch.setattr(plugins, "get_dss_client", lambda: client)
    assert _result(plugins.list_plugins(FakeContext()))["rows"] == [["demo", "1.0.0", True]]
    assert _result(plugins.get_plugin(FakeContext(), "demo"))["config"]["apiKey"] == "****"
    assert _result(plugins.list_plugin_files(FakeContext(), "demo"))[0]["name"] == "README.md"
    assert _result(plugins.get_plugin_file(FakeContext(), "demo", "README.md"))["content"] == "hello"
    _result(plugins.put_plugin_file(FakeContext(), "demo", "new.txt", "new"))
    _result(plugins.rename_plugin_file(FakeContext(), "demo", "new.txt", "renamed.txt"))
    _result(plugins.move_plugin_file(FakeContext(), "demo", "renamed.txt", "dir/renamed.txt"))
    settings = _result(plugins.get_plugin_settings(FakeContext(), "demo"))
    assert settings["config"]["apiKey"] == "****"
    settings["config"]["label"] = "changed"
    _result(plugins.set_plugin_settings(FakeContext(), "demo", settings))
    archive = tmp_path / "download.zip"
    _result(plugins.download_plugin(FakeContext(), "demo", str(archive)))
    assert archive.read_bytes() == b"plugin archive"


def test_plugin_sources_code_env_usages_and_delete(monkeypatch, tmp_path):
    client = _Client()
    monkeypatch.setattr(plugins, "get_dss_client", lambda: client)
    root = tmp_path / "plugin"
    _result(plugins.scaffold_plugin(FakeContext(), "demo", str(root)))
    _result(plugins.package_plugin(FakeContext(), str(root), str(tmp_path / "plugin.zip")))
    _result(plugins.install_plugin(FakeContext(), str(tmp_path / "plugin.zip")))
    _result(plugins.install_plugin_from_store(FakeContext(), "demo"))
    _result(plugins.install_plugin_from_git(FakeContext(), "https://example/repo", "main", "plugin"))
    _result(plugins.update_plugin_from_store(FakeContext(), "demo"))
    _result(plugins.update_plugin_from_git(FakeContext(), "demo", "https://example/repo", "main", "plugin"))
    _result(plugins.create_plugin_code_env(FakeContext(), "demo"))
    _result(plugins.set_plugin_code_env(FakeContext(), "demo", "env"))
    _result(plugins.update_plugin_code_env(FakeContext(), "demo"))
    assert _result(plugins.get_plugin_usages(FakeContext(), "demo"))["usages"] == []
    assert _result(plugins.delete_plugin(FakeContext(), "demo"))["deleted"]


def test_python_recipe_and_webapp_conversion(monkeypatch, tmp_path):
    client = _Client()
    monkeypatch.setattr(plugins, "get_dss_client", lambda: client)
    root = tmp_path / "converted"
    converted = _result(
        plugins.convert_python_recipe_to_plugin(
            FakeContext(), "P", "recipe", str(root), "converted-plugin"
        )
    )
    assert converted["recipeId"] == "recipe"
    assert (root / "custom-recipes" / "recipe" / "recipe.json").exists()
    assert any("explicit dataiku.Dataset" in warning for warning in converted["warnings"])
    webapp = _result(
        plugins.convert_webapp_to_plugin(
            FakeContext(), "P", "webapp", str(root), "converted-plugin"
        )
    )
    assert webapp["files"] == ["app.js", "body.html"]
    assert (root / "webapps" / "webapp" / "webapp.json").exists()


def test_dash_webapp_python_source_becomes_backend(monkeypatch, tmp_path):
    client = _Client()
    monkeypatch.setattr(plugins, "get_dss_client", lambda: client)
    root = tmp_path / "dash-plugin"

    class DashSettings:
        def get_raw(self):
            return {"name": "Dash", "type": "DASH", "params": {"python": "app.layout = html.Div()"}}

    class DashProject:
        def get_webapp(self, _):
            return type("WebApp", (), {"get_settings": lambda self: DashSettings()})()

    client.get_project = lambda _: DashProject()
    result = _result(plugins.convert_webapp_to_plugin(FakeContext(), "P", "webapp", str(root), "dash-plugin"))
    assert result["files"] == ["backend.py"]
    assert (root / "webapps" / "webapp" / "backend.py").read_text() == "app.layout = html.Div()"


def test_all_supported_component_layouts_validate(tmp_path):
    root = tmp_path / "all-components"
    _result(plugins.scaffold_plugin(FakeContext(), "all-components", str(root), components=list(plugins._COMPONENT_TEMPLATES)))
    for component_dir, (_, descriptor, implementation) in plugins._COMPONENT_TEMPLATES.items():
        component = root / component_dir / "demo"
        component.mkdir(parents=True, exist_ok=True)
        (component / descriptor).write_text("{}", encoding="utf-8")
        if implementation:
            (component / implementation).write_text("# demo\n", encoding="utf-8")
    result = _result(plugins.validate_plugin(FakeContext(), str(root)))
    assert result["valid"] is True
    assert result["findings"] == []


def test_component_validation_reports_missing_files(tmp_path):
    root = tmp_path / "invalid-components"
    _result(plugins.scaffold_plugin(FakeContext(), "invalid-components", str(root), components=["python-connectors", "webapps"]))
    (root / "python-connectors" / "connector").mkdir()
    (root / "python-connectors" / "connector" / "connector.json").write_text("{}")
    (root / "webapps" / "dashboard").mkdir()
    result = _result(plugins.validate_plugin(FakeContext(), str(root)))
    assert result["valid"] is False
    paths = {finding["path"] for finding in result["findings"]}
    assert "python-connectors/connector/connector.py" in paths
    assert "webapps/dashboard/webapp.json" in paths
    assert "webapps/dashboard/backend.py" in paths


def test_archive_excludes_build_artifacts_and_rejects_unsafe_local_paths(tmp_path):
    root = tmp_path / "plugin"
    _result(plugins.scaffold_plugin(FakeContext(), "plugin", str(root)))
    (root / ".git").mkdir()
    (root / ".git" / "config").write_text("secret", encoding="utf-8")
    (root / "__pycache__").mkdir()
    (root / "__pycache__" / "module.pyc").write_bytes(b"cache")
    archive = tmp_path / "plugin.zip"
    _result(plugins.package_plugin(FakeContext(), str(root), str(archive)))
    with ZipFile(archive) as zip_file:
        names = set(zip_file.namelist())
        assert ".git/config" not in names
        assert "__pycache__/module.pyc" not in names
    for operation in (
        plugins.read_local_plugin_file(FakeContext(), str(root), "../escape"),
        plugins.write_local_plugin_file(FakeContext(), str(root), "../escape", "x"),
        plugins.move_local_plugin_file(FakeContext(), str(root), "plugin.json", "../escape"),
    ):
        try:
            asyncio.run(operation)
        except ValueError:
            pass
        else:
            raise AssertionError("unsafe local path was accepted")


def test_conversion_rejects_non_python_recipe(monkeypatch, tmp_path):
    client = _Client()
    monkeypatch.setattr(plugins, "get_dss_client", lambda: client)

    class NonPythonSettings(_RecipeSettings):
        def get_recipe_raw_definition(self):
            return {"type": "sql_query"}

    class Project:
        def get_recipe(self, _):
            return type("Recipe", (), {"get_settings": lambda self: NonPythonSettings()})()

    client.get_project = lambda _: Project()
    try:
        asyncio.run(plugins.convert_python_recipe_to_plugin(FakeContext(), "P", "recipe", str(tmp_path / "plugin"), "plugin"))
    except ValueError as exc:
        assert "not a Python recipe" in str(exc)
    else:
        raise AssertionError("non-Python recipe was converted")


def test_delete_requires_force_when_plugin_has_usages(monkeypatch):
    client = _Client()
    client.plugin.usages = _Usage({"usages": [{"projectKey": "P", "objectId": "recipe"}]})
    monkeypatch.setattr(plugins, "get_dss_client", lambda: client)
    try:
        asyncio.run(plugins.delete_plugin(FakeContext(), "demo"))
    except ValueError as exc:
        assert "in use" in str(exc)
    else:
        raise AssertionError("in-use plugin was deleted without force")
    result = _result(plugins.delete_plugin(FakeContext(), "demo", force=True))
    assert result["force"] is True
