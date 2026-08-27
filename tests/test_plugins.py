"""Unit tests for the instance plugin tools.

No live Dataiku instance is involved: ``get_dss_client`` is replaced with the fakes
below. Three Dataiku behaviours drive most of these cases and are asserted explicitly —
a failed plugin action is answered with HTTP 200 and ``success: false``; a code-env
action reports through a nested ``messages`` block whose own ``success`` field is false
even on success; and some actions complete inline with no future id at all.
"""

import asyncio
import io
import json
import zipfile
from unittest.mock import patch

import pytest

from dataiku_mcp.tools import plugins as tools
from tests.utils.fakes import FakeContext, incrementing_monotonic

_MANIFEST = "plugin.json"
_UNRESOLVED = (
    "com.dataiku.dip.exceptions.CodedException: Types were missing when looking for "
    "usages of the plugin geocoder; its deletion may be forced"
)


def _load(coro):
    return json.loads(asyncio.run(coro))


def _listing_entry(plugin_id, version="1.0.0", dev=False, **meta):
    return {
        "id": plugin_id,
        "version": version,
        "isDev": dev,
        "meta": {"label": plugin_id.replace("-", " ").title(), **meta},
    }


def _alive():
    return {"alive": True, "hasResult": False}


def _done(success=True, **result):
    """An install/update/delete future result, which has a top-level success flag."""
    return {
        "alive": False,
        "aborted": False,
        "hasResult": True,
        "result": {"success": success, **result},
    }


def _code_env_done(env_name, error=None):
    """A code-environment future result: no top-level success flag, ever.

    Dataiku nests the outcome under ``messages``, and the success payload below is
    verbatim from a real successful creation — ``messages.success`` is false even
    though nothing failed, which is why only ``error``/``fatal`` may be trusted.
    """
    if error is None:
        messages = {
            "maxSeverity": "INFO",
            "anyMessage": True,
            "success": False,
            "warning": False,
            "error": False,
            "fatal": False,
            "messages": [
                {
                    "severity": "INFO",
                    "isFatal": False,
                    "code": "INFO_CODEENV_IMPORT_OK",
                    "message": "Import succeeded",
                }
            ],
        }
    else:
        messages = {
            "maxSeverity": "ERROR",
            "anyMessage": True,
            "success": False,
            "warning": False,
            "error": True,
            "fatal": True,
            "messages": [
                {
                    "severity": "ERROR",
                    "isFatal": True,
                    "code": "ERR_CODEENV_UPDATE_FAILED",
                    "message": error,
                }
            ],
        }
    return {
        "alive": False,
        "aborted": False,
        "hasResult": True,
        "result": {"envName": env_name, "messages": messages},
    }


class FakeFuture:
    """A DSSFuture stand-in walking a scripted sequence of states."""

    def __init__(self, job_id, states):
        self.job_id = job_id
        self.state = states[0]
        self._pending = list(states[1:])

    def get_state(self):
        if self._pending:
            self.state = self._pending.pop(0)
        return self.state


class FakePluginSettings:
    def __init__(self, raw):
        self.raw = raw
        self.saves = 0

    def get_raw(self):
        return self.raw

    def set_code_env(self, code_env_name):
        self.raw["codeEnvName"] = code_env_name

    def save(self):
        self.saves += 1


class FakeUsages:
    def __init__(self, raw):
        self.raw = raw

    def get_raw(self):
        return self.raw


class FakePlugin:
    def __init__(self, plugin_id, settings_raw=None, usages_raw=None):
        self.plugin_id = plugin_id
        self.settings = FakePluginSettings(settings_raw or {})
        self.usages_raw = usages_raw or {"usages": [], "missingTypes": []}
        self.usages_error = None
        self.delete_error = None
        self.futures = {}
        self.uploaded = None
        self.delete_calls = []
        self.created_interpreter = None
        # Set by FakeClient so an update makes the new version visible in the listing.
        self.on_change = lambda: None

    def get_settings(self):
        return self.settings

    def list_usages(self, project_key=None):
        if self.usages_error is not None:
            raise self.usages_error
        return FakeUsages(self.usages_raw)

    def update_from_store(self):
        self.on_change()
        return self.futures["update"]

    def start_update_from_zip(self, fp):
        self.uploaded = fp.read()
        self.on_change()
        return self.futures["update"]

    def create_code_env(self, python_interpreter=None):
        self.created_interpreter = python_interpreter
        return self.futures["create_code_env"]

    def update_code_env(self):
        return self.futures["update_code_env"]

    def delete(self, force=False):
        self.delete_calls.append(force)
        if self.delete_error is not None and not force:
            raise self.delete_error
        return self.futures["delete"]


class FakeClient:
    def __init__(
        self, listing=None, plugins=None, code_envs=None, listing_after_change=None
    ):
        self.listing = listing or []
        self.plugins = plugins or {}
        self.code_envs = code_envs or []
        self.listing_after_change = listing_after_change
        self.futures = {}
        self.uploaded = None
        self.store_install_id = None
        for plugin in self.plugins.values():
            plugin.on_change = self._apply_change

    def _apply_change(self):
        """Model Dataiku: after a successful action the listing reflects it."""
        if self.listing_after_change is not None:
            self.listing = self.listing_after_change

    def list_plugins(self):
        return [dict(entry) for entry in self.listing]

    def get_plugin(self, plugin_id):
        return self.plugins[plugin_id]

    def list_code_envs(self):
        return list(self.code_envs)

    def install_plugin_from_store(self, plugin_id):
        self.store_install_id = plugin_id
        self._apply_change()
        return self.futures["install"]

    def start_install_plugin_from_archive(self, fp):
        self.uploaded = fp.read()
        self._apply_change()
        return self.futures["install"]


def _installed(plugin_id="geocoder", version="1.0.0", **kwargs):
    """A client where ``plugin_id`` is already installed."""
    plugin = FakePlugin(
        plugin_id,
        settings_raw=kwargs.pop("settings", None),
        usages_raw=kwargs.pop("usages", None),
    )
    plugin.futures.update(kwargs.pop("futures", {}))
    client = FakeClient(
        listing=[_listing_entry(plugin_id, version)],
        plugins={plugin_id: plugin},
        **kwargs,
    )
    return plugin, client


def _absent(plugin_id="geocoder", version="1.0.0", **futures):
    """A client where ``plugin_id`` is absent until the action makes it appear."""
    plugin = FakePlugin(plugin_id)
    client = FakeClient(
        listing=[],
        plugins={plugin_id: plugin},
        listing_after_change=[_listing_entry(plugin_id, version)],
    )
    client.futures.update(futures)
    return plugin, client


@pytest.fixture(autouse=True)
def _no_real_sleeping(monkeypatch):
    monkeypatch.setattr(tools, "_MIN_POLL_INTERVAL_SECONDS", 0)
    monkeypatch.setattr(tools, "_MAX_POLL_INTERVAL_SECONDS", 0)


def _patch_client(client):
    return patch("dataiku_mcp.tools.plugins.get_dss_client", return_value=client)


def _exhausted_clock():
    return patch("dataiku_mcp.tools.plugins.time")


def _plugin_directory(tmp_path, plugin_id="my-plugin"):
    directory = tmp_path / plugin_id
    (directory / "python-lib").mkdir(parents=True)
    (directory / _MANIFEST).write_text(
        json.dumps({"id": plugin_id, "version": "0.1.0"})
    )
    (directory / "python-lib" / "core.py").write_text("VALUE = 1\n")
    (directory / ".git").mkdir()
    (directory / ".git" / "config").write_text("[core]\n")
    return directory


def _members(payload):
    return sorted(zipfile.ZipFile(io.BytesIO(payload)).namelist())


# --------------------------------------------------------------------------- #
# list_plugins
# --------------------------------------------------------------------------- #


def test_list_plugins_returns_catalog_metadata_with_summary_columns():
    client = FakeClient(
        listing=[
            _listing_entry("geocoder", version="1.3.1", tags=["Geo"]),
            _listing_entry("api-connect", version="1.2.1", deprecated=True),
        ]
    )

    with _patch_client(client):
        res = _load(tools.list_plugins(FakeContext()))

    assert res["total_plugins"] == 2
    assert res["plugins"]["columns"] == ["id", "version", "dev", "label", "deprecated"]
    assert res["plugins"]["rows"] == [
        ["api-connect", "1.2.1", False, "Api Connect", True],
        ["geocoder", "1.3.1", False, "Geocoder", False],
    ]


def test_list_plugins_partial_search_matches_label_and_tags_not_only_id():
    client = FakeClient(
        listing=[
            _listing_entry("document-question-answering", label="Answers"),
            _listing_entry("geocoder", tags=["Geography", "Enrichment"]),
            _listing_entry("salesforce"),
        ]
    )

    with _patch_client(client):
        by_label = _load(tools.list_plugins(FakeContext(), search="answers"))
        by_tag = _load(tools.list_plugins(FakeContext(), search="geography"))

    assert [row[0] for row in by_label["plugins"]["rows"]] == [
        "document-question-answering"
    ]
    assert [row[0] for row in by_tag["plugins"]["rows"]] == ["geocoder"]


def test_list_plugins_exact_search_returns_the_single_plugin():
    client = FakeClient(
        listing=[_listing_entry("geocoder"), _listing_entry("geocoder-extras")]
    )

    with _patch_client(client):
        res = _load(
            tools.list_plugins(FakeContext(), search="geocoder", search_mode="exact")
        )

    assert res["matched_plugins"] == 1
    assert res["plugins"]["rows"][0][0] == "geocoder"


def test_list_plugins_filters_dev_and_deprecated_and_pages():
    client = FakeClient(
        listing=[
            _listing_entry("a-dev", dev=True),
            _listing_entry("b-old", deprecated=True),
            _listing_entry("c-current"),
            _listing_entry("d-current"),
        ]
    )

    with _patch_client(client):
        dev_only = _load(tools.list_plugins(FakeContext(), dev=True))
        current = _load(tools.list_plugins(FakeContext(), deprecated=False, limit=2))
        page_two = _load(
            tools.list_plugins(FakeContext(), deprecated=False, limit=2, offset=2)
        )

    assert [row[0] for row in dev_only["plugins"]["rows"]] == ["a-dev"]
    assert [row[0] for row in current["plugins"]["rows"]] == ["a-dev", "c-current"]
    assert current["next_offset"] == 2
    assert [row[0] for row in page_two["plugins"]["rows"]] == ["d-current"]
    assert page_two["next_offset"] is None


def test_list_plugins_details_report_code_env_but_never_plugin_config():
    plugin = FakePlugin(
        "api-connect",
        settings_raw={
            "codeEnvName": "plugin_api-connect_managed",
            "config": {"api_key": "s3cret"},
            "presets": [{"name": "prod", "config": {"token": "s3cret"}}],
        },
    )
    client = FakeClient(
        listing=[
            _listing_entry(
                "api-connect",
                description="Call REST APIs",
                author="Dataiku",
                supportLevel="TIER2_SUPPORT",
                licenseInfo="Apache Software License",
            )
        ],
        plugins={"api-connect": plugin},
    )

    with _patch_client(client):
        res = _load(tools.list_plugins(FakeContext(), include_details=True))

    row = dict(zip(res["plugins"]["columns"], res["plugins"]["rows"][0]))
    assert row["code_env_name"] == "plugin_api-connect_managed"
    assert row["support_level"] == "TIER2_SUPPORT"
    assert "s3cret" not in json.dumps(res)
    assert "presets" not in json.dumps(res)


def test_list_plugins_reads_settings_only_for_the_returned_page():
    """The free meta columns come from the listing; only code_env_name costs a call."""
    reads = []

    class CountingPlugin(FakePlugin):
        def get_settings(self):
            reads.append(self.plugin_id)
            return self.settings

    plugins = {f"p{i}": CountingPlugin(f"p{i}") for i in range(5)}
    client = FakeClient(
        listing=[_listing_entry(f"p{i}") for i in range(5)], plugins=plugins
    )

    with _patch_client(client):
        _load(tools.list_plugins(FakeContext(), include_details=True, limit=2))

    assert reads == ["p0", "p1"]


# --------------------------------------------------------------------------- #
# install_plugin
# --------------------------------------------------------------------------- #


def test_install_plugin_from_store_reports_completion_and_restart_need():
    _, client = _absent(
        version="1.3.1",
        install=FakeFuture(
            "F1", [_alive(), _done(needsRestart=True, needsReload=True)]
        ),
    )

    with _patch_client(client):
        res = _load(tools.install_plugin("store", FakeContext(), plugin_id="geocoder"))

    assert res["status"] == "completed"
    assert res["operation"] == "install"
    assert res["source"] == "store"
    assert res["needs_restart"] is True
    assert res["needs_reload"] is True
    assert res["plugin"]["version"] == "1.3.1"
    assert client.store_install_id == "geocoder"


def test_install_plugin_reports_failure_reported_as_a_successful_response():
    """Dataiku answers a failed store install with HTTP 200 and success=false."""
    _, client = _absent(
        plugin_id="nope",
        install=FakeFuture(
            None,
            [
                _done(
                    success=False,
                    installationError={
                        "message": "Plugin has since been removed from the store.",
                        "stackTraceStr": "com.dataiku.dip.exceptions.CodedException: …",
                    },
                )
            ],
        ),
    )

    with _patch_client(client), pytest.raises(RuntimeError) as excinfo:
        asyncio.run(tools.install_plugin("store", FakeContext(), plugin_id="nope"))

    message = str(excinfo.value)
    assert "removed from the store" in message
    assert "github.com/dataiku/dss-plugin-" in message
    assert "CodedException" not in message


def test_install_plugin_from_local_path_omits_the_store_id_hint(tmp_path):
    directory = _plugin_directory(tmp_path)
    _, client = _absent(
        plugin_id="my-plugin",
        install=FakeFuture(
            None, [_done(success=False, installationError={"message": "bad archive"})]
        ),
    )

    with _patch_client(client), pytest.raises(RuntimeError) as excinfo:
        asyncio.run(
            tools.install_plugin("local_path", FakeContext(), local_path=str(directory))
        )

    assert "bad archive" in str(excinfo.value)
    assert "plugin store" not in str(excinfo.value)


def test_install_plugin_completes_inline_when_dataiku_returns_no_future_id():
    _, client = _absent(install=FakeFuture(None, [_done()]))

    with _patch_client(client):
        res = _load(
            tools.install_plugin(
                "store", FakeContext(), plugin_id="geocoder", wait_for_completion=False
            )
        )

    assert res["status"] == "completed"


def test_install_plugin_without_waiting_returns_a_followable_future():
    _, client = _absent(install=FakeFuture("F9", [_alive()]))

    with _patch_client(client):
        res = _load(
            tools.install_plugin(
                "store", FakeContext(), plugin_id="geocoder", wait_for_completion=False
            )
        )

    assert res["status"] == "started"
    assert res["operation"] == "install"
    assert res["future_id"] == "F9"
    assert "get_future_status" in res["hint"]


def test_install_plugin_timeout_reports_still_running_without_the_raw_state():
    _, client = _absent(install=FakeFuture("F5", [_alive(), _alive()]))

    with _patch_client(client), _exhausted_clock() as mock_time:
        mock_time.monotonic.side_effect = incrementing_monotonic()
        res = _load(tools.install_plugin("store", FakeContext(), plugin_id="geocoder"))

    assert res["status"] == "still_running"
    assert res["future_id"] == "F5"
    assert "state" not in res
    assert "Do not start a duplicate operation" in res["hint"]


def test_install_plugin_refuses_an_already_installed_plugin():
    _, client = _installed(version="1.3.1")

    with _patch_client(client), pytest.raises(ValueError) as excinfo:
        asyncio.run(tools.install_plugin("store", FakeContext(), plugin_id="geocoder"))

    assert "update_plugin" in str(excinfo.value)


def test_install_plugin_rejects_arguments_that_do_not_match_the_source():
    with pytest.raises(ValueError, match="local_path"):
        asyncio.run(
            tools.install_plugin(
                "store", FakeContext(), plugin_id="x", local_path="/tmp/x"
            )
        )
    with pytest.raises(ValueError, match="plugin_id"):
        asyncio.run(tools.install_plugin("store", FakeContext()))
    with pytest.raises(ValueError, match="local_path"):
        asyncio.run(tools.install_plugin("local_path", FakeContext()))
    with pytest.raises(ValueError, match="source"):
        asyncio.run(tools.install_plugin("git", FakeContext(), plugin_id="x"))


def test_install_plugin_zips_a_directory_and_omits_version_control_files(tmp_path):
    directory = _plugin_directory(tmp_path)
    _, client = _absent(plugin_id="my-plugin", install=FakeFuture(None, [_done()]))

    with _patch_client(client):
        res = _load(
            tools.install_plugin("local_path", FakeContext(), local_path=str(directory))
        )

    assert res["status"] == "completed"
    assert res["source"] == "local_path"
    assert _members(client.uploaded) == [_MANIFEST, "python-lib/core.py"]


def test_install_plugin_flattens_a_zip_wrapped_in_one_directory(tmp_path):
    archive_path = tmp_path / "download.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr(
            "dss-plugin-my-plugin/plugin.json", json.dumps({"id": "my-plugin"})
        )
        archive.writestr("dss-plugin-my-plugin/python-lib/core.py", "VALUE = 1\n")
    _, client = _absent(plugin_id="my-plugin", install=FakeFuture(None, [_done()]))

    with _patch_client(client):
        res = _load(
            tools.install_plugin(
                "local_path", FakeContext(), local_path=str(archive_path)
            )
        )

    assert res["status"] == "completed"
    assert _members(client.uploaded) == [_MANIFEST, "python-lib/core.py"]


def test_install_plugin_rejects_a_directory_without_a_manifest(tmp_path):
    (tmp_path / "empty").mkdir()

    with pytest.raises(ValueError, match="plugin.json"):
        asyncio.run(
            tools.install_plugin(
                "local_path", FakeContext(), local_path=str(tmp_path / "empty")
            )
        )


def test_install_plugin_rejects_a_manifest_that_is_not_a_json_object(tmp_path):
    directory = tmp_path / "broken"
    directory.mkdir()
    (directory / _MANIFEST).write_text('["not", "an", "object"]')

    with pytest.raises(ValueError, match="must be a JSON object"):
        asyncio.run(
            tools.install_plugin("local_path", FakeContext(), local_path=str(directory))
        )


def test_install_plugin_rejects_a_plugin_id_that_contradicts_the_manifest(tmp_path):
    directory = _plugin_directory(tmp_path)

    with _patch_client(FakeClient()), pytest.raises(ValueError) as excinfo:
        asyncio.run(
            tools.install_plugin(
                "local_path",
                FakeContext(),
                plugin_id="other-plugin",
                local_path=str(directory),
            )
        )

    assert "my-plugin" in str(excinfo.value)


def test_install_plugin_rejects_a_missing_local_path():
    with pytest.raises(ValueError, match="does not exist"):
        asyncio.run(
            tools.install_plugin(
                "local_path", FakeContext(), local_path="/nonexistent/plugin"
            )
        )


# --------------------------------------------------------------------------- #
# update_plugin
# --------------------------------------------------------------------------- #


def test_update_plugin_from_store_reports_the_resulting_version():
    _, client = _installed(
        version="1.3.1",
        futures={"update": FakeFuture("F2", [_alive(), _done()])},
        listing_after_change=[_listing_entry("geocoder", version="1.4.0")],
    )

    with _patch_client(client):
        res = _load(tools.update_plugin("store", FakeContext(), plugin_id="geocoder"))

    assert res["status"] == "completed"
    assert res["operation"] == "update"
    assert res["plugin"]["version"] == "1.4.0"


def test_update_plugin_refuses_a_plugin_that_is_not_installed():
    client = FakeClient(listing=[_listing_entry("geocoder-extras")])

    with _patch_client(client), pytest.raises(ValueError) as excinfo:
        asyncio.run(tools.update_plugin("store", FakeContext(), plugin_id="geocoder"))

    message = str(excinfo.value)
    assert "not installed" in message
    assert "geocoder-extras" in message


def test_update_plugin_rebuilds_the_bound_code_env():
    _, client = _installed(
        settings={"codeEnvName": "plugin_geocoder"},
        futures={
            "update": FakeFuture("F2", [_done()]),
            "update_code_env": FakeFuture(
                "F3", [_alive(), _code_env_done("plugin_geocoder")]
            ),
        },
    )

    with _patch_client(client):
        res = _load(
            tools.update_plugin(
                "store", FakeContext(), plugin_id="geocoder", rebuild_code_env=True
            )
        )

    assert res["status"] == "completed"
    assert res["code_env_rebuild"] == {
        "status": "completed",
        "code_env_name": "plugin_geocoder",
    }


def test_update_plugin_reports_an_unbound_code_env_instead_of_failing():
    _, client = _installed(futures={"update": FakeFuture("F2", [_done()])})

    with _patch_client(client):
        res = _load(
            tools.update_plugin(
                "store", FakeContext(), plugin_id="geocoder", rebuild_code_env=True
            )
        )

    assert res["status"] == "completed"
    assert res["code_env_rebuild"]["status"] == "skipped"
    assert "create_plugin_code_env" in res["code_env_rebuild"]["hint"]


def test_update_plugin_keeps_a_landed_update_when_the_rebuild_fails():
    _, client = _installed(
        settings={"codeEnvName": "plugin_geocoder"},
        futures={
            "update": FakeFuture("F2", [_done()]),
            "update_code_env": FakeFuture(
                "F3", [_code_env_done("plugin_geocoder", error="pip resolution failed")]
            ),
        },
    )

    with _patch_client(client):
        res = _load(
            tools.update_plugin(
                "store", FakeContext(), plugin_id="geocoder", rebuild_code_env=True
            )
        )

    assert res["status"] == "completed"
    assert res["code_env_rebuild"]["status"] == "failed"
    assert "pip resolution failed" in res["code_env_rebuild"]["error"]


def test_update_plugin_from_local_path_targets_the_manifest_id(tmp_path):
    directory = _plugin_directory(tmp_path)
    plugin, client = _installed(
        plugin_id="my-plugin",
        version="0.1.0",
        futures={"update": FakeFuture(None, [_done()])},
    )

    with _patch_client(client):
        res = _load(
            tools.update_plugin("local_path", FakeContext(), local_path=str(directory))
        )

    assert res["status"] == "completed"
    assert _members(plugin.uploaded) == [_MANIFEST, "python-lib/core.py"]


# --------------------------------------------------------------------------- #
# create_plugin_code_env
# --------------------------------------------------------------------------- #


def test_create_plugin_code_env_creates_then_binds():
    plugin, client = _installed(
        futures={
            "create_code_env": FakeFuture(
                "F4", [_alive(), _code_env_done("plugin_geocoder_managed")]
            )
        }
    )

    with _patch_client(client):
        res = _load(
            tools.create_plugin_code_env(
                "geocoder", FakeContext(), python_interpreter="PYTHON311"
            )
        )

    assert res["status"] == "completed"
    assert res["operation"] == "create_plugin_code_env"
    assert res["created"] is True
    assert res["code_env_name"] == "plugin_geocoder_managed"
    assert res["build"]["status"] == "completed"
    assert plugin.created_interpreter == "PYTHON311"
    assert plugin.settings.saves == 1


def test_create_plugin_code_env_reports_a_failed_build_and_still_binds():
    """The nested messages report is the only failure signal a code env gives."""
    plugin, client = _installed(
        futures={
            "create_code_env": FakeFuture(
                "F4",
                [
                    _code_env_done(
                        "plugin_geocoder_managed",
                        error="Environment update failed: Failed to install pip packages",
                    )
                ],
            )
        }
    )

    with _patch_client(client):
        res = _load(tools.create_plugin_code_env("geocoder", FakeContext()))

    assert res["status"] == "completed"
    assert res["created"] is True
    assert res["code_env_name"] == "plugin_geocoder_managed"
    assert res["build"]["status"] == "failed"
    assert "install pip packages" in res["build"]["error"]
    assert "rebuild_code_env" in res["build"]["hint"]
    assert plugin.settings.saves == 1


def test_code_env_success_reported_with_messages_success_false_is_not_a_failure():
    """A real successful creation returns messages.success=false with no error/fatal."""
    _, client = _installed(
        futures={
            "create_code_env": FakeFuture(
                None, [_code_env_done("plugin_geocoder_managed")]
            )
        }
    )

    with _patch_client(client):
        res = _load(tools.create_plugin_code_env("geocoder", FakeContext()))

    assert res["build"] == {
        "status": "completed",
        "code_env_name": "plugin_geocoder_managed",
    }


def test_create_plugin_code_env_is_a_no_op_when_one_is_already_bound():
    plugin, client = _installed(settings={"codeEnvName": "plugin_geocoder"})

    with _patch_client(client):
        res = _load(tools.create_plugin_code_env("geocoder", FakeContext()))

    assert res["status"] == "completed"
    assert res["created"] is False
    assert res["code_env_name"] == "plugin_geocoder"
    assert plugin.settings.saves == 0


def test_create_plugin_code_env_binds_an_orphan_instead_of_duplicating_it():
    """Re-running after a timed-out creation must not leave a numbered duplicate."""
    plugin, client = _installed(
        code_envs=[
            {"envName": "shared-python", "deploymentMode": "DESIGN_MANAGED"},
            {"envName": "plugin_geocoder_managed", "deploymentMode": "PLUGIN_MANAGED"},
        ]
    )

    with _patch_client(client):
        res = _load(tools.create_plugin_code_env("geocoder", FakeContext()))

    assert res["status"] == "completed"
    assert res["created"] is False
    assert res["code_env_name"] == "plugin_geocoder_managed"
    assert "build" not in res
    assert "create_code_env" not in plugin.futures


def test_create_plugin_code_env_ignores_another_plugins_environment():
    _, client = _installed(
        plugin_id="agent-hub",
        futures={
            "create_code_env": FakeFuture(
                None, [_code_env_done("plugin_agent-hub_managed")]
            )
        },
        code_envs=[
            {
                "envName": "plugin_agent-hub-extras_managed",
                "deploymentMode": "PLUGIN_MANAGED",
            }
        ],
    )

    with _patch_client(client):
        res = _load(tools.create_plugin_code_env("agent-hub", FakeContext()))

    assert res["created"] is True
    assert res["code_env_name"] == "plugin_agent-hub_managed"


def test_create_plugin_code_env_timeout_explains_the_recovery_path():
    plugin, client = _installed(
        futures={"create_code_env": FakeFuture("F4", [_alive(), _alive()])}
    )

    with _patch_client(client), _exhausted_clock() as mock_time:
        mock_time.monotonic.side_effect = incrementing_monotonic()
        res = _load(tools.create_plugin_code_env("geocoder", FakeContext()))

    assert res["status"] == "still_running"
    assert res["operation"] == "create_plugin_code_env"
    assert res["future_id"] == "F4"
    assert "re-run create_plugin_code_env" in res["hint"]
    assert plugin.settings.saves == 0


# --------------------------------------------------------------------------- #
# delete_plugin
# --------------------------------------------------------------------------- #


def test_delete_plugin_refuses_while_components_are_in_use():
    plugin, client = _installed(
        usages={
            "usages": [
                {
                    "elementKind": "custom-recipes",
                    "elementType": "CustomCode_geocode",
                    "objectType": "RECIPE",
                    "objectId": "geocode",
                    "projectKey": "PROJ",
                }
            ],
            "missingTypes": [],
        }
    )

    with _patch_client(client):
        res = _load(tools.delete_plugin("geocoder", FakeContext()))

    assert res["status"] == "refused"
    assert res["deleted"] is False
    assert res["usage_count"] == 1
    assert res["usages"]["columns"][:3] == ["projectKey", "objectType", "objectId"]
    assert res["usages"]["rows"][0][:3] == ["PROJ", "RECIPE", "geocode"]
    assert plugin.delete_calls == []


def test_delete_plugin_caps_the_reported_usages_but_not_the_count():
    usages = [
        {"projectKey": f"P{i}", "objectType": "RECIPE", "objectId": f"r{i}"}
        for i in range(120)
    ]
    _, client = _installed(usages={"usages": usages, "missingTypes": []})

    with _patch_client(client):
        res = _load(tools.delete_plugin("geocoder", FakeContext()))

    assert res["usage_count"] == 120
    assert len(res["usages"]["rows"]) == tools._MAX_REPORTED_USAGES


def test_delete_plugin_ignores_instance_wide_unresolvable_component_noise():
    """Dataiku reports missingTypes for the whole instance, not for this plugin."""
    _, client = _installed(
        usages={
            "usages": [],
            "missingTypes": [
                {"missingType": "Formula", "pluginId": "unknown", "objectId": "r1"},
                {"missingType": "geocode", "pluginId": "geocoder", "objectId": "r2"},
            ],
        }
    )

    with _patch_client(client):
        blocked = _load(tools.delete_plugin("geocoder", FakeContext()))

    assert blocked["deleted"] is False
    assert [item["objectId"] for item in blocked["unresolvable_components"]] == ["r2"]


def test_delete_plugin_refuses_legibly_when_the_usage_analysis_raises():
    """Dataiku raises here for a plugin installed since the last backend reload."""
    plugin, client = _installed()
    plugin.usages_error = RuntimeError(_UNRESOLVED)

    with _patch_client(client):
        res = _load(tools.delete_plugin("geocoder", FakeContext()))

    assert res["status"] == "refused"
    assert res["deleted"] is False
    assert res["reason"].startswith("Types were missing")
    assert "com.dataiku" not in json.dumps(res)
    assert "force=true" in res["hint"]
    assert plugin.delete_calls == []


def test_delete_plugin_refuses_legibly_when_the_delete_endpoint_raises():
    """The same check runs server-side on delete, so a clean analysis is not enough."""
    plugin, client = _installed(futures={"delete": FakeFuture(None, [_done()])})
    plugin.delete_error = RuntimeError(_UNRESOLVED)

    with _patch_client(client):
        refused = _load(tools.delete_plugin("geocoder", FakeContext()))
        forced = _load(tools.delete_plugin("geocoder", FakeContext(), force=True))

    assert refused["status"] == "refused"
    assert "com.dataiku" not in json.dumps(refused)
    assert forced["deleted"] is True
    assert plugin.delete_calls == [False, True]


@pytest.mark.parametrize("failing_step", ["usages", "delete"])
def test_delete_plugin_does_not_offer_force_for_an_unrelated_failure(failing_step):
    """A permission error is not a force candidate, from either pre-delete step."""
    plugin, client = _installed()
    setattr(
        plugin,
        f"{failing_step}_error",
        RuntimeError("Forbidden: you may not manage plugins"),
    )

    with _patch_client(client), pytest.raises(RuntimeError, match="Forbidden"):
        asyncio.run(tools.delete_plugin("geocoder", FakeContext()))


def test_delete_plugin_deletes_when_nothing_uses_it():
    plugin, client = _installed(
        futures={"delete": FakeFuture("F6", [_alive(), _done(needsRestart=True)])}
    )

    with _patch_client(client):
        res = _load(tools.delete_plugin("geocoder", FakeContext()))

    assert res == {
        "status": "completed",
        "operation": "delete",
        "plugin_id": "geocoder",
        "deleted": True,
        "forced": False,
        "needs_reload": False,
        "needs_restart": True,
    }
    assert plugin.delete_calls == [False]


def test_delete_plugin_force_deletes_despite_usages():
    plugin, client = _installed(
        usages={
            "usages": [{"objectId": "geocode", "projectKey": "PROJ"}],
            "missingTypes": [],
        },
        futures={"delete": FakeFuture(None, [_done()])},
    )

    with _patch_client(client):
        res = _load(tools.delete_plugin("geocoder", FakeContext(), force=True))

    assert res["deleted"] is True
    assert res["forced"] is True
    assert plugin.delete_calls == [True]


def test_delete_plugin_does_not_claim_deletion_on_a_failed_result():
    _, client = _installed(
        futures={
            "delete": FakeFuture(
                None, [_done(success=False, error={"message": "plugin is locked"})]
            )
        }
    )

    with _patch_client(client), pytest.raises(RuntimeError, match="plugin is locked"):
        asyncio.run(tools.delete_plugin("geocoder", FakeContext()))


def test_delete_plugin_timeout_does_not_claim_deletion():
    _, client = _installed(futures={"delete": FakeFuture("F7", [_alive(), _alive()])})

    with _patch_client(client), _exhausted_clock() as mock_time:
        mock_time.monotonic.side_effect = incrementing_monotonic()
        res = _load(tools.delete_plugin("geocoder", FakeContext()))

    assert res["status"] == "still_running"
    assert res["deleted"] is False
    assert res["future_id"] == "F7"


# --------------------------------------------------------------------------- #
# Shared future and boundary behaviour
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "call",
    [
        lambda: tools.install_plugin(
            "store", FakeContext(), plugin_id="x", timeout_seconds=0
        ),
        lambda: tools.update_plugin(
            "store", FakeContext(), plugin_id="x", timeout_seconds=7200
        ),
        lambda: tools.create_plugin_code_env("x", FakeContext(), timeout_seconds=7200),
        lambda: tools.delete_plugin("x", FakeContext(), timeout_seconds=0),
    ],
)
def test_timeout_bounds_are_validated(call):
    with pytest.raises(ValueError, match="timeout_seconds"):
        asyncio.run(call())


def test_start_response_without_a_liveness_flag_is_polled_not_trusted():
    """A bare {"jobId": ...} start response must not read as a completed install."""
    _, client = _absent(
        install=FakeFuture("F10", [{"jobId": "F10"}, _done(needsRestart=True)])
    )

    with _patch_client(client):
        res = _load(tools.install_plugin("store", FakeContext(), plugin_id="geocoder"))

    assert res["status"] == "completed"
    assert res["needs_restart"] is True


def test_future_that_stops_without_a_result_is_not_reported_as_success():
    _, client = _absent(
        install=FakeFuture(
            "F11",
            [{"alive": True, "hasResult": False}, {"alive": False, "hasResult": False}],
        )
    )

    with _patch_client(client), pytest.raises(RuntimeError, match="without reporting"):
        asyncio.run(tools.install_plugin("store", FakeContext(), plugin_id="geocoder"))


def test_aborted_future_is_not_reported_as_success():
    _, client = _absent(
        install=FakeFuture(
            "F8", [{"alive": False, "aborted": True, "hasResult": False}]
        )
    )

    with _patch_client(client), pytest.raises(RuntimeError, match="aborted"):
        asyncio.run(tools.install_plugin("store", FakeContext(), plugin_id="geocoder"))


@pytest.mark.parametrize(
    ("operation", "expected"),
    [
        ("install", "aborted the installation of plugin"),
        ("update", "aborted the update of plugin"),
        ("delete", "aborted the deletion of plugin"),
        ("create_plugin_code_env", "aborted the code environment build of plugin"),
    ],
)
def test_error_prose_reads_grammatically_for_every_operation(operation, expected):
    with pytest.raises(RuntimeError, match=expected):
        tools._terminal_result(operation, "geo", {"aborted": True})


def test_poll_interval_scales_with_the_wait_budget(monkeypatch):
    """A ten-minute code-env budget must not be polled every two seconds."""
    monkeypatch.setattr(tools, "_MIN_POLL_INTERVAL_SECONDS", 2)
    monkeypatch.setattr(tools, "_MAX_POLL_INTERVAL_SECONDS", 30)
    slept = []

    async def _record(seconds):
        slept.append(seconds)

    monkeypatch.setattr(tools.asyncio, "sleep", _record)
    future = FakeFuture("F1", [_alive(), _alive(), _done()])
    asyncio.run(tools._wait_for_future(future, 600))

    assert slept and all(interval == 10 for interval in slept)
