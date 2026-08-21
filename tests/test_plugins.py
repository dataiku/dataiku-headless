"""Unit tests for Dataiku plugin management tools."""

import asyncio
import json
from copy import deepcopy
from unittest.mock import MagicMock
from zipfile import ZipFile, ZipInfo

import pytest
from dataikuapi.utils import DataikuException

from dataiku_mcp.tools import plugins
from tests.utils.fakes import FakeContext


class FakeFuture:
    """A DSSFuture stand-in.

    ``job_id=None`` models DSS answering with the result already in the state, which
    it does when the operation finished before it replied; ``DSSFuture.from_resp``
    leaves ``job_id`` unset in that case. Otherwise the tools poll ``get_state`` and
    then read ``get_result``, so both are implemented here as the SDK does.
    """

    def __init__(self, job_id="future-1", result=None, on_wait=None):
        self.job_id = job_id
        self.result = result if result is not None else {"done": True}
        self.on_wait = on_wait
        self.wait_count = 0

    def _finish(self):
        self.wait_count += 1
        if self.on_wait is not None:
            self.on_wait()

    def get_state(self):
        self._finish()
        return {"hasResult": True, "result": self.result}

    def get_result(self):
        return self.result

    def wait_for_result(self):
        self._finish()
        return self.result


def _load(coroutine):
    return json.loads(asyncio.run(coroutine))


def _plugin_mock(raw_settings=None):
    plugin = MagicMock()
    raw = raw_settings or {"codeEnvName": None, "config": {}}
    settings = MagicMock()
    settings.get_raw.side_effect = lambda: raw
    plugin.get_settings.return_value = settings
    return plugin, settings, raw


def _client_with_plugin(plugin_id="my-plugin", *, version="1.0.0", dev=True):
    client = MagicMock()
    metadata = {"id": plugin_id, "version": version, "dev": str(dev)}
    plugin, settings, raw = _plugin_mock()
    client.list_plugins.return_value = [metadata]
    client.get_plugin.return_value = plugin
    return client, plugin, settings, raw


def _capturing_install_client(plugin_id, version="1"):
    """Client whose archive upload records the uploaded names and makes the plugin appear."""
    metadata = []
    client = MagicMock()
    plugin, _, _ = _plugin_mock()
    client.list_plugins.side_effect = lambda: deepcopy(metadata)
    client.get_plugin.return_value = plugin
    uploaded = {}

    def _install(archive):
        with ZipFile(archive) as uploaded_archive:
            uploaded["names"] = uploaded_archive.namelist()
        metadata.append({"id": plugin_id, "version": version, "isDev": False})

    client.install_plugin_from_archive.side_effect = _install
    return client, uploaded


def test_list_plugins_filters_sorts_and_normalizes_dev(monkeypatch):
    client = MagicMock()
    client.list_plugins.return_value = [
        {"id": "zeta", "version": "2", "dev": "False"},
        {"id": "Alpha-dev", "version": "1", "isDev": True},
        {"id": "beta-dev", "version": "3", "dev": "True"},
    ]
    monkeypatch.setattr(plugins, "get_dss_client", lambda: client)

    result = _load(plugins.list_plugins(FakeContext(), search="DEV", dev=True, limit=1))

    assert result["matched_plugins"] == 2
    assert result["next_offset"] == 1
    assert result["plugins"] == {
        "columns": ["id", "version", "dev"],
        "rows": [["Alpha-dev", "1", True]],
    }


def test_get_plugin_returns_configured_keys_without_values(monkeypatch):
    client, _, _, raw = _client_with_plugin(dev=False)
    raw.update(
        {
            "codeEnvName": "plugin-env",
            "config": {
                "endpoint": "https://example.invalid",
                "apiKey": "top-secret",
                "nested": {"password": "hidden", "region": "eu"},
            },
        },
    )
    monkeypatch.setattr(plugins, "get_dss_client", lambda: client)

    result = _load(plugins.get_plugin("my-plugin", FakeContext()))["plugin"]

    assert result == {
        "id": "my-plugin",
        "version": "1.0.0",
        "dev": False,
        "code_env_name": "plugin-env",
        "configured_keys": ["apiKey", "endpoint", "nested"],
    }


def test_get_plugin_fails_for_unknown_id(monkeypatch):
    client = MagicMock()
    client.list_plugins.return_value = []
    monkeypatch.setattr(plugins, "get_dss_client", lambda: client)

    with pytest.raises(ValueError, match="not installed"):
        _load(plugins.get_plugin("missing", FakeContext()))


def test_get_plugin_tolerates_settings_without_a_config_section(monkeypatch):
    client, plugin, settings, _ = _client_with_plugin()
    settings.get_raw.side_effect = lambda: {"codeEnvName": "plugin-env"}
    plugin.get_settings.return_value = settings
    monkeypatch.setattr(plugins, "get_dss_client", lambda: client)

    result = _load(plugins.get_plugin("my-plugin", FakeContext()))["plugin"]

    assert result["code_env_name"] == "plugin-env"
    assert result["configured_keys"] == []


def test_list_plugin_usages_returns_normalized_rows(monkeypatch):
    client, plugin, _, _ = _client_with_plugin()
    usages = MagicMock()
    usages.get_raw.return_value = {
        "usages": [
            {
                "projectKey": "PROJ",
                "objectType": "RECIPE",
                "objectId": "prepare",
                "elementKind": "custom-recipes",
                "elementType": "CustomCode_prepare",
            }
        ],
        "missingTypes": [
            {
                "missingType": "Formula",
                "objectType": "recipe",
                "projectKey": "OTHER",
                "objectId": "unrelated",
                "pluginId": "unknown",
            }
        ],
    }
    plugin.list_usages.return_value = usages
    monkeypatch.setattr(plugins, "get_dss_client", lambda: client)

    result = _load(
        plugins.list_plugin_usages("my-plugin", FakeContext(), project_key="PROJ")
    )

    plugin.list_usages.assert_called_once_with(project_key="PROJ")
    assert result["usage_count"] == 1
    assert result["usages"]["rows"] == [
        ["PROJ", "RECIPE", "prepare", "custom-recipes", "CustomCode_prepare"]
    ]
    # DSS reports missing types for the whole instance, not for this plugin.
    assert result["instance_missing_types"] == {"count": 1, "types": ["Formula"]}


def test_update_plugin_settings_merges_saves_and_verifies(monkeypatch):
    client, _, settings, raw = _client_with_plugin()
    raw["config"] = {"existing": "kept", "apiKey": "old"}
    monkeypatch.setattr(plugins, "get_dss_client", lambda: client)

    result = _load(
        plugins.update_plugin_settings(
            "my-plugin", {"region": "eu", "apiKey": "new"}, FakeContext()
        )
    )

    settings.save.assert_called_once_with()
    assert raw["config"] == {
        "existing": "kept",
        "region": "eu",
        "apiKey": "new",
    }
    assert result["updated_keys"] == ["apiKey", "region"]
    assert result["configured_keys"] == ["apiKey", "existing", "region"]
    assert "config" not in result


def test_update_plugin_settings_fails_when_reread_drops_value(monkeypatch):
    client, plugin, settings, _ = _client_with_plugin()
    before = {"codeEnvName": None, "config": {"existing": "kept"}}
    after = {"codeEnvName": None, "config": {"existing": "kept"}}
    settings.get_raw.return_value = before
    reread_settings = MagicMock()
    reread_settings.get_raw.return_value = after
    plugin.get_settings.side_effect = [settings, reread_settings]
    monkeypatch.setattr(plugins, "get_dss_client", lambda: client)

    with pytest.raises(RuntimeError, match=r"did not persist.*\['region'\]") as failure:
        _load(
            plugins.update_plugin_settings("my-plugin", {"region": "eu"}, FakeContext())
        )
    assert "eu" not in str(failure.value)


def test_install_plugin_from_store_returns_future_id(monkeypatch):
    client = MagicMock()
    client.list_plugins.return_value = []
    future = FakeFuture("install-1")
    client.install_plugin_from_store.return_value = future
    monkeypatch.setattr(plugins, "get_dss_client", lambda: client)

    result = _load(plugins.install_plugin_from_store("store-plugin", FakeContext()))

    assert result["status"] == "plugin_install_started"
    assert result["plugin_id"] == "store-plugin"
    assert result["future_id"] == "install-1"
    assert future.wait_count == 0


def test_install_plugin_from_store_waits_and_rereads(monkeypatch):
    client = MagicMock()
    metadata = {"id": "store-plugin", "version": "2.0", "isDev": False}
    client.list_plugins.side_effect = [[], [metadata]]
    plugin, _, _ = _plugin_mock()
    client.get_plugin.return_value = plugin
    future = FakeFuture("install-1", {"installed": True})
    client.install_plugin_from_store.return_value = future
    monkeypatch.setattr(plugins, "get_dss_client", lambda: client)

    result = _load(
        plugins.install_plugin_from_store(
            "store-plugin", FakeContext(), wait_for_completion=True
        )
    )

    assert future.wait_count == 1
    assert result["status"] == "plugin_install_completed"
    assert result["plugin"]["id"] == "store-plugin"
    assert result["result"] == {"installed": True}


def test_install_plugin_from_store_rejects_installed_plugin(monkeypatch):
    client, _, _, _ = _client_with_plugin("store-plugin")
    monkeypatch.setattr(plugins, "get_dss_client", lambda: client)

    with pytest.raises(ValueError, match="Use an update tool"):
        _load(plugins.install_plugin_from_store("store-plugin", FakeContext()))

    client.install_plugin_from_store.assert_not_called()


def test_update_plugin_from_store_returns_future(monkeypatch):
    client, plugin, _, _ = _client_with_plugin()
    plugin.update_from_store.return_value = FakeFuture("store-update")
    monkeypatch.setattr(plugins, "get_dss_client", lambda: client)

    result = _load(plugins.update_plugin_from_store("my-plugin", FakeContext()))

    plugin.update_from_store.assert_called_once_with()
    assert result["status"] == "plugin_update_started"
    assert result["future_id"] == "store-update"


def test_delete_plugin_inspects_usages_waits_and_verifies(monkeypatch):
    client, plugin, _, _ = _client_with_plugin()
    client.list_plugins.side_effect = [
        [{"id": "my-plugin", "version": "1.0", "dev": "True"}],
        [],
    ]
    usages = MagicMock()
    usages.get_raw.return_value = {
        "usages": [{"projectKey": "PROJ"}],
        "missingTypes": [],
    }
    plugin.list_usages.return_value = usages
    future = FakeFuture("delete-1")
    plugin.delete.return_value = future
    monkeypatch.setattr(plugins, "get_dss_client", lambda: client)

    result = _load(plugins.delete_plugin("my-plugin", FakeContext()))

    plugin.list_usages.assert_called_once_with()
    plugin.delete.assert_called_once_with(force=False)
    assert future.wait_count == 1
    assert result["deleted"] is True
    assert result["usage_count_before_delete"] == 1


def test_force_delete_expresses_destructive_intent_to_sdk(monkeypatch):
    client, plugin, _, _ = _client_with_plugin()
    client.list_plugins.side_effect = [
        [{"id": "my-plugin", "version": "1.0", "dev": "True"}],
        [],
    ]
    usages = MagicMock()
    usages.get_raw.return_value = {"usages": [], "missingTypes": []}
    plugin.list_usages.return_value = usages
    plugin.delete.return_value = FakeFuture("delete-force")
    monkeypatch.setattr(plugins, "get_dss_client", lambda: client)

    result = _load(plugins.delete_plugin("my-plugin", FakeContext(), force=True))

    plugin.delete.assert_called_once_with(force=True)
    assert result["force"] is True


def test_install_plugin_from_local_directory_uploads_flat_archive(
    monkeypatch, tmp_path
):
    plugin_dir = tmp_path / "plugin"
    plugin_dir.mkdir()
    (plugin_dir / "plugin.json").write_text(
        json.dumps({"id": "local-plugin", "version": "1.0"})
    )
    (plugin_dir / "python-lib").mkdir()
    (plugin_dir / "python-lib" / "library.py").write_text("VALUE = 1")
    client, uploaded = _capturing_install_client("local-plugin", version="1.0")
    monkeypatch.setattr(plugins, "get_dss_client", lambda: client)

    result = _load(
        plugins.install_plugin_from_local_path(str(plugin_dir), FakeContext())
    )

    assert uploaded["names"] == ["plugin.json", "python-lib/library.py"]
    assert result["status"] == "plugin_install_completed"
    assert result["plugin"]["id"] == "local-plugin"


def test_install_plugin_from_local_directory_rejects_symbolic_links(
    monkeypatch, tmp_path
):
    plugin_dir = tmp_path / "plugin"
    plugin_dir.mkdir()
    (plugin_dir / "plugin.json").write_text(json.dumps({"id": "local-plugin"}))
    outside = tmp_path / "outside.txt"
    outside.write_text("must not upload")
    (plugin_dir / "linked-secret").symlink_to(outside)
    client = MagicMock()
    monkeypatch.setattr(plugins, "get_dss_client", lambda: client)

    with pytest.raises(ValueError, match="contains a symbolic link"):
        _load(plugins.install_plugin_from_local_path(str(plugin_dir), FakeContext()))

    client.install_plugin_from_archive.assert_not_called()


def test_install_plugin_from_local_path_rejects_symbolic_link_root(
    monkeypatch, tmp_path
):
    plugin_dir = tmp_path / "plugin"
    plugin_dir.mkdir()
    (plugin_dir / "plugin.json").write_text(json.dumps({"id": "local-plugin"}))
    plugin_link = tmp_path / "plugin-link"
    plugin_link.symlink_to(plugin_dir, target_is_directory=True)
    client = MagicMock()
    monkeypatch.setattr(plugins, "get_dss_client", lambda: client)

    with pytest.raises(ValueError, match="must not be a symbolic link"):
        _load(plugins.install_plugin_from_local_path(str(plugin_link), FakeContext()))

    client.install_plugin_from_archive.assert_not_called()


def test_install_plugin_from_local_directory_rejects_hidden_files(
    monkeypatch, tmp_path
):
    plugin_dir = tmp_path / "plugin"
    plugin_dir.mkdir()
    (plugin_dir / "plugin.json").write_text(json.dumps({"id": "local-plugin"}))
    (plugin_dir / ".env").write_text("TOKEN=must-not-upload")
    client = MagicMock()
    monkeypatch.setattr(plugins, "get_dss_client", lambda: client)

    with pytest.raises(ValueError, match="contains a hidden path component"):
        _load(plugins.install_plugin_from_local_path(str(plugin_dir), FakeContext()))

    client.install_plugin_from_archive.assert_not_called()


def test_install_plugin_from_wrapped_zip_flattens_archive(monkeypatch, tmp_path):
    zip_path = tmp_path / "wrapped.zip"
    with ZipFile(zip_path, "w") as archive:
        archive.writestr("wrapper/plugin.json", json.dumps({"id": "wrapped"}))
        archive.writestr("wrapper/python-lib/code.py", "VALUE = 1")
    client, uploaded = _capturing_install_client("wrapped")
    monkeypatch.setattr(plugins, "get_dss_client", lambda: client)

    _load(plugins.install_plugin_from_local_path(str(zip_path), FakeContext()))

    assert uploaded["names"] == ["plugin.json", "python-lib/code.py"]


def test_install_plugin_from_local_path_rejects_missing_path(monkeypatch, tmp_path):
    monkeypatch.setattr(plugins, "get_dss_client", lambda: MagicMock())

    with pytest.raises(ValueError, match="does not exist"):
        _load(
            plugins.install_plugin_from_local_path(
                str(tmp_path / "missing"), FakeContext()
            )
        )


def test_install_plugin_from_local_path_rejects_non_zip_file(monkeypatch, tmp_path):
    text_file = tmp_path / "notes.txt"
    text_file.write_text("not a plugin")
    monkeypatch.setattr(plugins, "get_dss_client", lambda: MagicMock())

    with pytest.raises(ValueError, match="must be a plugin directory or ZIP archive"):
        _load(plugins.install_plugin_from_local_path(str(text_file), FakeContext()))


def test_install_plugin_from_local_path_rejects_directory_without_plugin_json(
    monkeypatch, tmp_path
):
    plugin_dir = tmp_path / "plugin"
    plugin_dir.mkdir()
    (plugin_dir / "python-lib").mkdir()
    monkeypatch.setattr(plugins, "get_dss_client", lambda: MagicMock())

    with pytest.raises(ValueError, match="does not contain plugin.json"):
        _load(plugins.install_plugin_from_local_path(str(plugin_dir), FakeContext()))


def test_install_plugin_from_local_path_rejects_zip_without_plugin_json(
    monkeypatch, tmp_path
):
    zip_path = tmp_path / "empty.zip"
    with ZipFile(zip_path, "w") as archive:
        archive.writestr("README.md", "no plugin.json here")
    monkeypatch.setattr(plugins, "get_dss_client", lambda: MagicMock())

    with pytest.raises(ValueError, match="must contain plugin.json"):
        _load(plugins.install_plugin_from_local_path(str(zip_path), FakeContext()))


def test_install_plugin_from_local_path_rejects_ambiguous_zip_layout(
    monkeypatch, tmp_path
):
    zip_path = tmp_path / "ambiguous.zip"
    with ZipFile(zip_path, "w") as archive:
        archive.writestr("one/plugin.json", json.dumps({"id": "one"}))
        archive.writestr("two/plugin.json", json.dumps({"id": "two"}))
    monkeypatch.setattr(plugins, "get_dss_client", lambda: MagicMock())

    with pytest.raises(ValueError, match="must contain plugin.json"):
        _load(plugins.install_plugin_from_local_path(str(zip_path), FakeContext()))


def test_install_plugin_from_local_path_rejects_unsafe_zip_path(monkeypatch, tmp_path):
    zip_path = tmp_path / "unsafe.zip"
    with ZipFile(zip_path, "w") as archive:
        archive.writestr("plugin.json", json.dumps({"id": "unsafe"}))
        archive.writestr("../outside.txt", "must not upload")
    client = MagicMock()
    monkeypatch.setattr(plugins, "get_dss_client", lambda: client)

    with pytest.raises(ValueError, match="contains an unsafe path"):
        _load(plugins.install_plugin_from_local_path(str(zip_path), FakeContext()))

    client.install_plugin_from_archive.assert_not_called()


def test_install_plugin_from_local_path_rejects_zip_symbolic_link(
    monkeypatch, tmp_path
):
    zip_path = tmp_path / "symlink.zip"
    symlink = ZipInfo("linked-secret")
    symlink.create_system = 3
    symlink.external_attr = 0o120777 << 16
    with ZipFile(zip_path, "w") as archive:
        archive.writestr("plugin.json", json.dumps({"id": "unsafe"}))
        archive.writestr(symlink, "outside.txt")
    client = MagicMock()
    monkeypatch.setattr(plugins, "get_dss_client", lambda: client)

    with pytest.raises(ValueError, match="contains a symbolic link"):
        _load(plugins.install_plugin_from_local_path(str(zip_path), FakeContext()))

    client.install_plugin_from_archive.assert_not_called()


def test_install_plugin_from_local_path_rejects_hidden_zip_directory(
    monkeypatch, tmp_path
):
    zip_path = tmp_path / "plugin.zip"
    with ZipFile(zip_path, "w") as archive:
        archive.writestr("plugin.json", json.dumps({"id": "unsafe"}))
        archive.writestr(".aws/credentials", "access_key = secret")
    client = MagicMock()
    monkeypatch.setattr(plugins, "get_dss_client", lambda: client)

    with pytest.raises(ValueError, match="contains a hidden path component"):
        _load(plugins.install_plugin_from_local_path(str(zip_path), FakeContext()))

    client.install_plugin_from_archive.assert_not_called()


def test_update_plugin_from_local_path_rejects_mismatched_id(monkeypatch, tmp_path):
    zip_path = tmp_path / "other.zip"
    with ZipFile(zip_path, "w") as archive:
        archive.writestr("plugin.json", json.dumps({"id": "other-plugin"}))
    client, plugin, _, _ = _client_with_plugin()
    monkeypatch.setattr(plugins, "get_dss_client", lambda: client)

    with pytest.raises(ValueError, match="does not match"):
        _load(
            plugins.update_plugin_from_local_path(
                "my-plugin", str(zip_path), FakeContext()
            )
        )

    plugin.update_from_zip.assert_not_called()


def test_update_plugin_from_local_path_uploads_and_rereads(monkeypatch, tmp_path):
    zip_path = tmp_path / "plugin.zip"
    with ZipFile(zip_path, "w") as archive:
        archive.writestr("plugin.json", json.dumps({"id": "my-plugin"}))
        archive.writestr("python-lib/code.py", "VALUE = 2")
    client, plugin, _, _ = _client_with_plugin(version="2.0")
    uploaded = {}

    def _update(archive):
        with ZipFile(archive) as uploaded_archive:
            uploaded["names"] = uploaded_archive.namelist()

    plugin.update_from_zip.side_effect = _update
    monkeypatch.setattr(plugins, "get_dss_client", lambda: client)

    result = _load(
        plugins.update_plugin_from_local_path("my-plugin", str(zip_path), FakeContext())
    )

    assert uploaded["names"] == ["plugin.json", "python-lib/code.py"]
    assert result["status"] == "plugin_update_completed"
    assert result["plugin"]["version"] == "2.0"


def test_create_plugin_code_env_skips_existing_binding(monkeypatch):
    client, plugin, _, raw = _client_with_plugin()
    raw["codeEnvName"] = "plugin-managed"
    monkeypatch.setattr(plugins, "get_dss_client", lambda: client)

    result = _load(plugins.create_plugin_code_env("my-plugin", FakeContext()))

    assert result["status"] == "plugin_code_env_already_bound"
    assert result["bound_code_env_name"] == "plugin-managed"
    plugin.create_code_env.assert_not_called()


def test_create_plugin_code_env_starts_future_with_sdk_options(monkeypatch):
    client, plugin, _, _ = _client_with_plugin()
    plugin.create_code_env.return_value = FakeFuture("env-create")
    monkeypatch.setattr(plugins, "get_dss_client", lambda: client)

    result = _load(
        plugins.create_plugin_code_env(
            "my-plugin",
            FakeContext(),
            python_interpreter="PYTHON311",
            conda=True,
        )
    )

    plugin.create_code_env.assert_called_once_with(
        python_interpreter="PYTHON311", conda=True
    )
    assert result["future_id"] == "env-create"


def test_create_plugin_code_env_force_overrides_existing_binding(monkeypatch):
    client, plugin, _, raw = _client_with_plugin()
    raw["codeEnvName"] = "plugin-managed"
    plugin.create_code_env.return_value = FakeFuture("env-create-forced")
    monkeypatch.setattr(plugins, "get_dss_client", lambda: client)

    result = _load(
        plugins.create_plugin_code_env("my-plugin", FakeContext(), force=True)
    )

    plugin.create_code_env.assert_called_once_with(python_interpreter=None, conda=False)
    assert result["status"] == "plugin_code_env_creation_started"
    assert result["future_id"] == "env-create-forced"


def test_create_plugin_code_env_waits_and_rereads_binding(monkeypatch):
    client, plugin, _, raw = _client_with_plugin()

    def _bind_created_env():
        raw["codeEnvName"] = "plugin-managed"

    future = FakeFuture(
        "env-create", {"envName": "plugin-managed"}, on_wait=_bind_created_env
    )
    plugin.create_code_env.return_value = future
    monkeypatch.setattr(plugins, "get_dss_client", lambda: client)

    result = _load(
        plugins.create_plugin_code_env(
            "my-plugin", FakeContext(), wait_for_completion=True
        )
    )

    assert future.wait_count == 1
    assert result["status"] == "plugin_code_env_creation_completed"
    assert result["created_code_env_name"] == "plugin-managed"
    assert result["bound_code_env_name"] == "plugin-managed"
    assert "hint" not in result


def test_set_plugin_code_env_saves_and_verifies(monkeypatch):
    client, _, settings, raw = _client_with_plugin()

    def _set_code_env(name):
        raw["codeEnvName"] = name

    settings.set_code_env.side_effect = _set_code_env
    monkeypatch.setattr(plugins, "get_dss_client", lambda: client)

    result = _load(
        plugins.set_plugin_code_env("my-plugin", "shared-env", FakeContext())
    )

    settings.set_code_env.assert_called_once_with("shared-env")
    settings.save.assert_called_once_with()
    assert result == {"plugin_id": "my-plugin", "code_env_name": "shared-env"}


def test_update_plugin_code_env_requires_bound_environment(monkeypatch):
    client, plugin, _, _ = _client_with_plugin()
    monkeypatch.setattr(plugins, "get_dss_client", lambda: client)

    with pytest.raises(ValueError, match="no bound code environment"):
        _load(plugins.update_plugin_code_env("my-plugin", FakeContext()))

    plugin.update_code_env.assert_not_called()


def test_update_plugin_code_env_returns_future_for_bound_environment(monkeypatch):
    client, plugin, _, raw = _client_with_plugin()
    raw["codeEnvName"] = "plugin-managed"
    plugin.update_code_env.return_value = FakeFuture("env-update")
    monkeypatch.setattr(plugins, "get_dss_client", lambda: client)

    result = _load(plugins.update_plugin_code_env("my-plugin", FakeContext()))

    plugin.update_code_env.assert_called_once_with()
    assert result["status"] == "plugin_code_env_update_started"
    assert result["future_id"] == "env-update"
    assert result["code_env_name"] == "plugin-managed"


def test_install_plugin_from_store_completes_when_dss_answers_inline(monkeypatch):
    client = MagicMock()
    metadata = {"id": "store-plugin", "version": "2.0", "isDev": False}
    client.list_plugins.side_effect = [[], [metadata]]
    plugin, _, _ = _plugin_mock()
    client.get_plugin.return_value = plugin
    future = FakeFuture(job_id=None, result={"installed": True})
    client.install_plugin_from_store.return_value = future
    monkeypatch.setattr(plugins, "get_dss_client", lambda: client)

    result = _load(plugins.install_plugin_from_store("store-plugin", FakeContext()))

    assert result["status"] == "plugin_install_completed"
    assert result["plugin"]["id"] == "store-plugin"
    assert result["result"] == {"installed": True}
    assert future.wait_count == 1


def test_update_plugin_from_store_completes_when_dss_answers_inline(monkeypatch):
    client, plugin, _, _ = _client_with_plugin()
    plugin.update_from_store.return_value = FakeFuture(job_id=None, result={"ok": True})
    monkeypatch.setattr(plugins, "get_dss_client", lambda: client)

    result = _load(plugins.update_plugin_from_store("my-plugin", FakeContext()))

    assert result["status"] == "plugin_update_completed"
    assert result["plugin"]["id"] == "my-plugin"


def test_create_plugin_code_env_completes_when_dss_answers_inline(monkeypatch):
    client, plugin, _, raw = _client_with_plugin()
    plugin.create_code_env.return_value = FakeFuture(
        job_id=None,
        result={"envName": "plugin_my-plugin_managed"},
        on_wait=lambda: raw.update({"codeEnvName": "plugin_my-plugin_managed"}),
    )
    monkeypatch.setattr(plugins, "get_dss_client", lambda: client)

    result = _load(plugins.create_plugin_code_env("my-plugin", FakeContext()))

    assert result["status"] == "plugin_code_env_creation_completed"
    assert result["created_code_env_name"] == "plugin_my-plugin_managed"


def test_update_plugin_code_env_completes_when_dss_answers_inline(monkeypatch):
    client, plugin, _, raw = _client_with_plugin()
    raw["codeEnvName"] = "plugin-env"
    plugin.update_code_env.return_value = FakeFuture(job_id=None, result={"ok": True})
    monkeypatch.setattr(plugins, "get_dss_client", lambda: client)

    result = _load(plugins.update_plugin_code_env("my-plugin", FakeContext()))

    assert result["status"] == "plugin_code_env_update_completed"
    assert result["code_env_name"] == "plugin-env"


def test_update_plugin_settings_adds_a_missing_config_section(monkeypatch):
    client, _, settings, raw = _client_with_plugin()
    raw.pop("config")
    monkeypatch.setattr(plugins, "get_dss_client", lambda: client)

    result = _load(
        plugins.update_plugin_settings("my-plugin", {"region": "eu"}, FakeContext())
    )

    settings.save.assert_called_once_with()
    assert raw["config"] == {"region": "eu"}
    assert result["configured_keys"] == ["region"]


def test_install_plugin_from_zip_keeps_development_metadata(monkeypatch, tmp_path):
    zip_path = tmp_path / "plugin.zip"
    with ZipFile(zip_path, "w") as archive:
        archive.writestr("plugin.json", json.dumps({"id": "zipped"}))
        archive.writestr("python-lib/__pycache__/code.cpython-311.pyc", b"\x00")
    client, _ = _capturing_install_client("zipped")
    monkeypatch.setattr(plugins, "get_dss_client", lambda: client)

    result = _load(plugins.install_plugin_from_local_path(str(zip_path), FakeContext()))

    client.install_plugin_from_archive.assert_called_once()
    assert result["plugin"]["id"] == "zipped"


def test_install_plugin_from_zip_rejects_hidden_path_component(monkeypatch, tmp_path):
    zip_path = tmp_path / "plugin.zip"
    with ZipFile(zip_path, "w") as archive:
        archive.writestr("plugin.json", json.dumps({"id": "zipped"}))
        archive.writestr(".git/config", "url = https://token@example.invalid/repo")
    client = MagicMock()
    monkeypatch.setattr(plugins, "get_dss_client", lambda: client)

    with pytest.raises(ValueError, match="hidden path component"):
        _load(plugins.install_plugin_from_local_path(str(zip_path), FakeContext()))

    client.install_plugin_from_archive.assert_not_called()


def test_install_plugin_from_local_directory_rejects_hidden_directory(
    monkeypatch, tmp_path
):
    plugin_dir = tmp_path / "plugin"
    plugin_dir.mkdir()
    (plugin_dir / "plugin.json").write_text(json.dumps({"id": "local-plugin"}))
    (plugin_dir / ".aws").mkdir()
    (plugin_dir / ".aws" / "credentials").write_text("access_key = secret")
    client = MagicMock()
    monkeypatch.setattr(plugins, "get_dss_client", lambda: client)

    with pytest.raises(ValueError, match="hidden path component"):
        _load(plugins.install_plugin_from_local_path(str(plugin_dir), FakeContext()))

    client.install_plugin_from_archive.assert_not_called()


def test_flattening_a_wrapped_zip_preserves_file_modes(tmp_path):
    zip_path = tmp_path / "wrapped.zip"
    executable = ZipInfo("wrapper/scripts/build.sh")
    executable.external_attr = 0o755 << 16
    with ZipFile(zip_path, "w") as archive:
        archive.writestr("wrapper/plugin.json", json.dumps({"id": "wrapped"}))
        archive.writestr(executable, "#!/bin/sh\n")

    flattened = plugins._flatten_archive(zip_path, "wrapper")
    try:
        with ZipFile(flattened) as result:
            modes = {
                info.filename: info.external_attr >> 16 for info in result.infolist()
            }
    finally:
        flattened.unlink()

    assert modes["scripts/build.sh"] & 0o111


def test_install_plugin_from_zip_rejects_plugin_json_without_an_id(
    monkeypatch, tmp_path
):
    zip_path = tmp_path / "plugin.zip"
    with ZipFile(zip_path, "w") as archive:
        archive.writestr("plugin.json", json.dumps({"version": "1"}))
    monkeypatch.setattr(plugins, "get_dss_client", lambda: MagicMock())

    with pytest.raises(ValueError, match="does not declare a plugin 'id'"):
        _load(plugins.install_plugin_from_local_path(str(zip_path), FakeContext()))


def _refusing_client(usages, missing_types):
    client, plugin, _, _ = _client_with_plugin()
    usage = MagicMock()
    usage.get_raw.return_value = {"usages": usages, "missingTypes": missing_types}
    plugin.list_usages.return_value = usage
    plugin.delete.side_effect = DataikuException(
        "CodedException: Types were missing when looking for usages"
    )
    return client, plugin


def test_delete_plugin_refusal_names_instance_wide_missing_types(monkeypatch):
    # DSS also refuses force=False when types are unresolvable anywhere on the
    # instance, which says nothing about the plugin being deleted.
    client, _ = _refusing_client([], [{"missingType": "Formula"}, {"missingType": "X"}])
    monkeypatch.setattr(plugins, "get_dss_client", lambda: client)

    with pytest.raises(ValueError) as failure:
        _load(plugins.delete_plugin("my-plugin", FakeContext()))

    message = str(failure.value)
    assert "no usage of this plugin" in message
    assert "2 component type(s) are unresolvable elsewhere" in message
    assert "force=true" in message


def test_delete_plugin_refusal_names_real_usages(monkeypatch):
    client, _ = _refusing_client([{"projectKey": "PROJ"}], [])
    monkeypatch.setattr(plugins, "get_dss_client", lambda: client)

    with pytest.raises(ValueError, match="1 usage\\(s\\) of this plugin"):
        _load(plugins.delete_plugin("my-plugin", FakeContext()))


def test_delete_plugin_reports_a_refusal_that_force_did_not_override(monkeypatch):
    client, _ = _refusing_client([], [])
    monkeypatch.setattr(plugins, "get_dss_client", lambda: client)

    with pytest.raises(ValueError, match="even with force=true"):
        _load(plugins.delete_plugin("my-plugin", FakeContext(), force=True))


# Captured from DSS 15.0.0-beta3: a completed future whose result reports failure.
DSS_FAILED_RESULT = {
    "success": False,
    "needsReload": False,
    "needsRestart": False,
    "installationError": {
        "errorType": "com.dataiku.dip.exceptions.CodedException",
        "message": "Plugin has since been removed from the store.",
        "stackTraceStr": "com.dataiku.dip.exceptions.CodedException: ...",
        "code": "ERR_PLUGIN_NOT_INSTALLED",
    },
    "errorMessage": "Could not fetch the plugin",
}


def test_completed_future_reporting_failure_is_not_reported_as_success(monkeypatch):
    client, plugin, _, _ = _client_with_plugin()
    plugin.update_from_store.return_value = FakeFuture(
        job_id=None, result=DSS_FAILED_RESULT
    )
    monkeypatch.setattr(plugins, "get_dss_client", lambda: client)

    with pytest.raises(RuntimeError) as failure:
        _load(plugins.update_plugin_from_store("my-plugin", FakeContext()))

    message = str(failure.value)
    assert "Plugin has since been removed from the store." in message
    assert "ERR_PLUGIN_NOT_INSTALLED" in message
    assert "stackTraceStr" not in message
    assert "com.dataiku.dip" not in message


def test_successful_future_result_drops_stack_traces_and_rendered_html(monkeypatch):
    client, plugin, _, _ = _client_with_plugin()
    plugin.update_from_store.return_value = FakeFuture(
        "update-1",
        result={
            "success": True,
            "needsRestart": False,
            "stackTraceStr": "java...",
            "detailedMessageHTML": "<span>...</span>",
            "messages": {"messages": []},
        },
    )
    monkeypatch.setattr(plugins, "get_dss_client", lambda: client)

    result = _load(
        plugins.update_plugin_from_store(
            "my-plugin", FakeContext(), wait_for_completion=True
        )
    )

    assert result["result"] == {"success": True, "needsRestart": False}


def test_failed_deletion_future_does_not_report_the_plugin_as_deleted(monkeypatch):
    client, plugin, _, _ = _client_with_plugin()
    usage = MagicMock()
    usage.get_raw.return_value = {"usages": [], "missingTypes": []}
    plugin.list_usages.return_value = usage
    plugin.delete.return_value = FakeFuture("del-1", result=DSS_FAILED_RESULT)
    monkeypatch.setattr(plugins, "get_dss_client", lambda: client)

    with pytest.raises(RuntimeError, match="plugin_deletion as failed"):
        _load(plugins.delete_plugin("my-plugin", FakeContext()))


def test_create_plugin_code_env_says_the_new_environment_is_unbound(monkeypatch):
    # Dataiku creates a plugin code environment without binding it, so a further
    # call would create a second one rather than report the first.
    client, plugin, _, _ = _client_with_plugin()
    plugin.create_code_env.return_value = FakeFuture(
        "env-create", {"envName": "plugin_my-plugin_managed"}
    )
    monkeypatch.setattr(plugins, "get_dss_client", lambda: client)

    result = _load(
        plugins.create_plugin_code_env(
            "my-plugin", FakeContext(), wait_for_completion=True
        )
    )

    assert result["created_code_env_name"] == "plugin_my-plugin_managed"
    assert result["bound_code_env_name"] is None
    assert "set_plugin_code_env" in result["hint"]


def test_code_env_creation_messages_envelope_is_not_read_as_failure():
    # Captured from DSS 15.0.0-beta3: a successful build whose messages envelope
    # carries success=false, meaning "no success-level message was emitted".
    result = {
        "envName": "plugin_x_managed",
        "messages": {
            "messages": [{"severity": "INFO", "code": "INFO_CODEENV_IMPORT_OK"}],
            "maxSeverity": "INFO",
            "success": False,
            "error": False,
            "fatal": False,
        },
    }

    assert plugins._plugin_operation_result("plugin_code_env_creation", result) == {
        "envName": "plugin_x_managed"
    }
