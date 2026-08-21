"""Unit tests for Dataiku Plugin Store tools."""

import asyncio
import json
from unittest.mock import MagicMock

import pytest

from dataiku_mcp.tools import plugins
from tests.utils.fakes import FakeContext


class FakeFuture:
    def __init__(self, job_id="future-1", result=None):
        self.job_id = job_id
        self.result = result if result is not None else {"done": True}
        self.wait_count = 0

    def get_state(self):
        self.wait_count += 1
        return {"hasResult": True}

    def get_result(self):
        return self.result

    def wait_for_result(self):
        self.wait_count += 1
        return self.result


def _load(coroutine):
    return json.loads(asyncio.run(coroutine))


def _client_with_plugin(plugin_id="my-plugin", *, version="1.0.0", dev=True):
    client = MagicMock()
    client.list_plugins.return_value = [
        {"id": plugin_id, "version": version, "dev": str(dev)}
    ]
    return client, client.get_plugin.return_value


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
    future = FakeFuture("install-1", {"installed": True})
    client.install_plugin_from_store.return_value = future
    monkeypatch.setattr(plugins, "get_dss_client", lambda: client)

    result = _load(
        plugins.install_plugin_from_store(
            "store-plugin", FakeContext(), wait_for_completion=True
        )
    )

    assert result["status"] == "plugin_install_completed"
    assert result["plugin"] == {"id": "store-plugin", "version": "2.0", "dev": False}
    assert result["result"] == {"installed": True}


def test_install_plugin_from_store_rejects_installed_plugin(monkeypatch):
    client, _ = _client_with_plugin("store-plugin")
    monkeypatch.setattr(plugins, "get_dss_client", lambda: client)

    with pytest.raises(ValueError, match="update_plugin_from_store"):
        _load(plugins.install_plugin_from_store("store-plugin", FakeContext()))

    client.install_plugin_from_store.assert_not_called()


def test_update_plugin_from_store_returns_future(monkeypatch):
    client, plugin = _client_with_plugin()
    plugin.update_from_store.return_value = FakeFuture("store-update")
    monkeypatch.setattr(plugins, "get_dss_client", lambda: client)

    result = _load(plugins.update_plugin_from_store("my-plugin", FakeContext()))

    plugin.update_from_store.assert_called_once_with()
    assert result["status"] == "plugin_update_started"
    assert result["future_id"] == "store-update"


def test_store_operation_completes_when_dss_answers_inline(monkeypatch):
    client, plugin = _client_with_plugin()
    plugin.update_from_store.return_value = FakeFuture(job_id=None, result={"ok": True})
    monkeypatch.setattr(plugins, "get_dss_client", lambda: client)

    result = _load(plugins.update_plugin_from_store("my-plugin", FakeContext()))

    assert result["status"] == "plugin_update_completed"
    assert result["plugin"]["id"] == "my-plugin"


def test_failed_store_operation_does_not_report_success(monkeypatch):
    client, plugin = _client_with_plugin()
    plugin.update_from_store.return_value = FakeFuture(
        job_id=None,
        result={
            "success": False,
            "installationError": {
                "message": "Plugin has been removed from the Store.",
                "stackTraceStr": "java...",
                "code": "ERR_PLUGIN_NOT_INSTALLED",
            },
        },
    )
    monkeypatch.setattr(plugins, "get_dss_client", lambda: client)

    with pytest.raises(RuntimeError) as failure:
        _load(plugins.update_plugin_from_store("my-plugin", FakeContext()))

    message = str(failure.value)
    assert "Plugin has been removed from the Store." in message
    assert "ERR_PLUGIN_NOT_INSTALLED" in message
    assert "stackTraceStr" not in message


def test_successful_store_result_drops_noisy_diagnostics(monkeypatch):
    client, plugin = _client_with_plugin()
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
