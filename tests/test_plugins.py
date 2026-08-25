"""Unit tests for Dataiku Plugin Store tools."""

import asyncio
import json
from unittest.mock import MagicMock

import pytest

from dataiku_mcp.tools import plugins
from tests.utils.fakes import FakeContext


class FakeFuture:
    """Stand-in for a DSSFuture. ``job_id=None`` models an inline Dataiku answer."""

    def __init__(self, job_id="future-1", result=None, polls_before_result=0):
        self.job_id = job_id
        self.result = result if result is not None else {"done": True}
        self.polls_before_result = polls_before_result
        self.poll_count = 0

    def peek_state(self):
        self.poll_count += 1
        return {"hasResult": self.poll_count > self.polls_before_result}

    def get_result(self):
        return self.result

    def wait_for_result(self):
        self.poll_count += 1
        return self.result


def _load(coroutine):
    return json.loads(asyncio.run(coroutine))


def _client_with_plugin(plugin_id="my-plugin", *, version="1.0.0", dev=False):
    client = MagicMock()
    client.list_plugins.return_value = [
        {"id": plugin_id, "version": version, "isDev": dev}
    ]
    return client, client.get_plugin.return_value


@pytest.fixture
def instant_clock(monkeypatch):
    """Advance the poll clock one second per reading and skip the real sleeps."""
    ticks = iter(range(10_000))

    async def _sleep(_seconds):
        return None

    monkeypatch.setattr(plugins.time, "monotonic", lambda: float(next(ticks)))
    monkeypatch.setattr(plugins.asyncio, "sleep", _sleep)


def test_list_plugins_filters_sorts_and_counts(monkeypatch):
    client = MagicMock()
    client.list_plugins.return_value = [
        {"id": "zeta", "version": "2", "isDev": False},
        {"id": "Alpha-dev", "version": "1", "isDev": True},
        {"id": "beta-dev", "version": "3", "dev": True},
    ]
    monkeypatch.setattr(plugins, "get_dss_client", lambda: client)

    result = _load(plugins.list_plugins(FakeContext(), search="DEV", dev=True, limit=1))

    assert result["total_plugins"] == 3
    assert result["matched_plugins"] == 2
    assert result["returned_plugins"] == 1
    assert result["next_offset"] == 1
    assert result["plugins"] == {
        "columns": ["id", "version", "dev"],
        "rows": [["Alpha-dev", "1", True]],
    }


def test_list_plugins_exhausted_page_reports_no_next_offset(monkeypatch):
    client, _ = _client_with_plugin()
    monkeypatch.setattr(plugins, "get_dss_client", lambda: client)

    result = _load(plugins.list_plugins(FakeContext()))

    assert result["next_offset"] is None
    assert result["plugins"]["rows"] == [["my-plugin", "1.0.0", False]]


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
    assert future.poll_count == 0


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


def test_update_plugin_from_store_rejects_absent_plugin(monkeypatch):
    client = MagicMock()
    client.list_plugins.return_value = []
    monkeypatch.setattr(plugins, "get_dss_client", lambda: client)

    with pytest.raises(ValueError, match="is not installed"):
        _load(plugins.update_plugin_from_store("store-plugin", FakeContext()))

    client.get_plugin.return_value.update_from_store.assert_not_called()


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


def test_inline_wait_times_out_and_keeps_future_id(monkeypatch, instant_clock):
    client, plugin = _client_with_plugin()
    plugin.update_from_store.return_value = FakeFuture(
        "slow-update", polls_before_result=10_000
    )
    monkeypatch.setattr(plugins, "get_dss_client", lambda: client)

    result = _load(
        plugins.update_plugin_from_store(
            "my-plugin", FakeContext(), wait_for_completion=True, timeout_seconds=3
        )
    )

    assert result["status"] == "plugin_update_still_running"
    assert result["future_id"] == "slow-update"
    assert "not a failure" in result["hint"]


def test_inline_wait_rejects_timeout_over_the_cap(monkeypatch):
    client, _ = _client_with_plugin()
    monkeypatch.setattr(plugins, "get_dss_client", lambda: client)

    with pytest.raises(ValueError, match="timeout_seconds"):
        _load(
            plugins.update_plugin_from_store(
                "my-plugin",
                FakeContext(),
                timeout_seconds=plugins.MAX_INLINE_WAIT_SECONDS + 1,
            )
        )


def test_poll_failure_preserves_future_id_for_recovery(monkeypatch, instant_clock):
    client, plugin = _client_with_plugin()
    future = FakeFuture("update-9")
    future.peek_state = MagicMock(side_effect=OSError("connection reset"))
    plugin.update_from_store.return_value = future
    monkeypatch.setattr(plugins, "get_dss_client", lambda: client)

    result = _load(
        plugins.update_plugin_from_store(
            "my-plugin", FakeContext(), wait_for_completion=True
        )
    )

    assert result["status"] == "plugin_update_poll_failed"
    assert result["future_id"] == "update-9"
    assert result["error_type"] == "OSError"
    assert "do not start a replacement" in result["hint"]


def test_success_is_reported_even_when_the_plugin_is_not_listed_yet(monkeypatch):
    client = MagicMock()
    client.list_plugins.return_value = []
    client.install_plugin_from_store.return_value = FakeFuture(
        "install-2", {"success": True, "needsRestart": True}
    )
    monkeypatch.setattr(plugins, "get_dss_client", lambda: client)

    result = _load(
        plugins.install_plugin_from_store(
            "store-plugin", FakeContext(), wait_for_completion=True
        )
    )

    assert result["status"] == "plugin_install_completed"
    assert result["result"] == {"success": True, "needsRestart": True}
    assert "plugin" not in result
    assert "instance restart" in result["hint"]


def test_start_failure_tells_the_caller_the_request_may_have_landed(monkeypatch):
    client, plugin = _client_with_plugin()
    plugin.update_from_store.side_effect = OSError("connection reset")
    monkeypatch.setattr(plugins, "get_dss_client", lambda: client)

    with pytest.raises(RuntimeError, match="may have reached Dataiku"):
        _load(plugins.update_plugin_from_store("my-plugin", FakeContext()))


@pytest.mark.parametrize(
    "result",
    [
        {
            "success": False,
            "installationError": {
                "message": "Plugin has been removed from the Store.",
                "stackTraceStr": "java...",
                "code": "ERR_PLUGIN_NOT_INSTALLED",
            },
        },
        # No explicit success flag: the error alone must still fail the operation.
        {
            "installationError": {
                "message": "Plugin has been removed from the Store.",
                "stackTraceStr": "java...",
                "code": "ERR_PLUGIN_NOT_INSTALLED",
            },
        },
    ],
)
def test_failed_store_operation_does_not_report_success(monkeypatch, result):
    client, plugin = _client_with_plugin()
    plugin.update_from_store.return_value = FakeFuture(job_id=None, result=result)
    monkeypatch.setattr(plugins, "get_dss_client", lambda: client)

    with pytest.raises(RuntimeError) as failure:
        _load(plugins.update_plugin_from_store("my-plugin", FakeContext()))

    message = str(failure.value)
    assert "Plugin has been removed from the Store." in message
    assert "ERR_PLUGIN_NOT_INSTALLED" in message
    assert "stackTraceStr" not in message
    assert "java" not in message


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
