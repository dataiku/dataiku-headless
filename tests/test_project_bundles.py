# Copyright 2026 Dataiku SAS
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Bundle SDK contracts, lifecycle guards, instance pinning and safe receipts."""

import asyncio
import copy
import json
import threading
from types import SimpleNamespace

import pytest
from dataikuapi.dss.project import DSSProject
from dataikuapi.utils import DataikuException
from fastmcp import Client
from requests import Timeout

from dataiku_mcp import mcp
from dataiku_mcp.config import request, stdio
from dataiku_mcp.tools import project_bundles
from tests.test_instance_policy import _instance

SECRET = "DO_NOT_RETURN_BUNDLE_SECRET"


class Backend:
    def __init__(self):
        self.calls = []
        self.owner_thread = threading.get_ident()
        self.bundles = []
        self.fail_method = None
        self.exception = Timeout
        self.fail_after_export = False
        self.settings = {
            "settings": {"codeEnvs": {"python": {"envName": "environment"}}},
            "bundleExporterSettings": {
                "exportOptions": {
                    "includedDatasetsData": [{"name": "previous_input"}],
                    "includedSavedModels": [{"id": "existing_model"}],
                    "exportNotebooks": True,
                }
            },
            "unrelated": {"secret": SECRET},
        }
        self.exported_options = []

    def _perform_json(self, method, path, **kwargs):
        assert threading.get_ident() != self.owner_thread, "SDK called on event loop"
        self.calls.append((method, path, copy.deepcopy(kwargs)))
        if method == self.fail_method:
            raise self.exception(SECRET)
        if method == "GET" and path.endswith("/settings"):
            return copy.deepcopy(self.settings)
        if method == "GET":
            return {"bundles": copy.deepcopy(self.bundles), "secret": SECRET}
        if method == "PUT":
            self.exported_options.append(
                copy.deepcopy(
                    (self.settings.get("bundleExporterSettings") or {}).get(
                        "exportOptions", {}
                    )
                )
            )
            self.bundles.append({"bundleId": "v1", "state": "BUILT"})
            if self.fail_after_export:
                raise Timeout(SECRET)
            return {"message": "Created Bundle", "secret": SECRET}
        if method == "POST":
            return {
                "publishedProjectKey": (kwargs.get("params") or {}).get(
                    "publishedProjectKey", "SOURCE"
                ),
                "publishedOn": 123,
                "publishedBy": "user",
                "secret": SECRET,
            }
        raise AssertionError((method, path, kwargs))

    def _perform_empty(self, method, path, **kwargs):
        assert threading.get_ident() != self.owner_thread, "SDK called on event loop"
        assert method == "PUT" and path == "/projects/SOURCE/settings"
        self.calls.append((method, path, copy.deepcopy(kwargs)))
        if method == self.fail_method:
            raise self.exception(SECRET)
        self.settings = copy.deepcopy(kwargs["body"])


@pytest.fixture
def backend(monkeypatch):
    backend = Backend()
    monkeypatch.setattr(stdio, "_current_instance", _instance("design"))

    def get_client():
        assert threading.get_ident() != backend.owner_thread
        assert request.get_pinned_instance().name == "design"
        return SimpleNamespace(get_project=lambda key: DSSProject(backend, key))

    monkeypatch.setattr(project_bundles, "get_dss_client", get_client)
    return backend


async def _call(tool, **arguments):
    async with Client(mcp) as client:
        result = await client.call_tool(tool, arguments)
        return json.loads(result.content[0].text)


def call(tool, **arguments):
    return asyncio.run(_call(tool, **arguments))


def test_list_allowlists_nested_receipts_and_recovery_ids(backend):
    backend.bundles = [
        {
            "bundleId": "v1",
            "state": "FAILED",
            "sizeInBytes": 42,
            "projectStandardsSkipped": False,
            "exportManifest": {"credentials": SECRET},
            "projectStandardsRunReport": {"diagnostics": SECRET},
            "futureItem": {
                "jobId": "future",
                "storedError": SECRET,
                "lastResponse": {"log": SECRET},
            },
            "publishedBundleState": {
                "publishedProjectKey": "TARGET",
                "publishedOn": 123,
                "publishedBy": "user",
                "secret": SECRET,
            },
        }
    ]
    result = call("list_project_bundles", project_key="SOURCE")
    assert result["instance_name"] == "design"
    table = result["bundles"]
    assert dict(zip(table["columns"], table["rows"][0])) == {
        "bundle_id": "v1",
        "state": "FAILED",
        "size_bytes": 42,
        "project_standards_skipped": False,
        "future_id": "future",
        "published_project_key": "TARGET",
        "published_on": 123,
        "published_by": "user",
    }
    assert SECRET not in json.dumps(result)
    assert (
        result["export_options"]
        == backend.settings["bundleExporterSettings"]["exportOptions"]
    )
    assert backend.calls == [
        ("GET", "/projects/SOURCE/bundles/exported", {}),
        ("GET", "/projects/SOURCE/settings", {}),
    ]


def test_create_waits_for_sdk_and_preserves_standards_checks(backend):
    result = call(
        "create_project_bundle",
        project_key=" SOURCE ",
        bundle_id=" v1 ",
        release_notes="Release 1",
    )
    assert result == {
        "instance_name": "design",
        "project_key": "SOURCE",
        "bundle_id": "v1",
        "status": "created",
        "published": False,
    }
    assert backend.calls == [
        ("GET", "/projects/SOURCE/bundles/exported", {}),
        (
            "PUT",
            "/projects/SOURCE/bundles/exported/v1",
            {
                "params": {
                    "releaseNotes": "Release 1",
                    "evaluateProjectStandardsChecks": True,
                }
            },
        ),
    ]
    assert SECRET not in json.dumps(result)


@pytest.mark.parametrize("state", ["BUILT", "BUILDING", "FAILED", "ABORTED"])
def test_create_refuses_every_existing_bundle_state(backend, state):
    backend.bundles = [{"bundleId": "v1", "state": state}]
    with pytest.raises(Exception, match="already exists"):
        call(
            "create_project_bundle",
            project_key="SOURCE",
            bundle_id="v1",
            export_options={"includedDatasetsData": []},
        )
    assert [method for method, _, _ in backend.calls] == ["GET"]


@pytest.mark.parametrize("target", [None, " TARGET "])
def test_publish_uses_configured_deployer_and_safe_receipt(backend, target):
    backend.bundles = [{"bundleId": "v1", "state": "BUILT"}]
    options = {} if target is None else {"published_project_key": target}
    result = call(
        "publish_project_bundle", project_key="SOURCE", bundle_id="v1", **options
    )
    assert result == {
        "instance_name": "design",
        "project_key": "SOURCE",
        "bundle_id": "v1",
        "status": "published",
        "published_project_key": "SOURCE" if target is None else "TARGET",
        "published_on": 123,
        "published_by": "user",
        "deployment_started": False,
    }
    assert backend.calls[-1] == (
        "POST",
        "/projects/SOURCE/bundles/v1/publish",
        {"params": None if target is None else {"publishedProjectKey": "TARGET"}},
    )
    assert SECRET not in json.dumps(result)


@pytest.mark.parametrize("state", [None, "BUILDING", "FAILED", "ABORTED"])
def test_publish_requires_a_built_bundle(backend, state):
    if state is not None:
        backend.bundles = [{"bundleId": "v1", "state": state}]
    with pytest.raises(Exception, match="BUILT"):
        call("publish_project_bundle", project_key="SOURCE", bundle_id="v1")
    assert [method for method, _, _ in backend.calls] == ["GET"]


@pytest.mark.parametrize(
    "tool,field",
    [
        ("list_project_bundles", "project_key"),
        ("create_project_bundle", "project_key"),
        ("create_project_bundle", "bundle_id"),
        ("publish_project_bundle", "project_key"),
        ("publish_project_bundle", "bundle_id"),
        ("publish_project_bundle", "published_project_key"),
    ],
)
@pytest.mark.parametrize(
    "invalid", ["", " ", ".", "..", "a/b", "a\\b", "%2f", "a?x", "a#x", "a\n", "a\x00"]
)
def test_identifiers_rejected_before_any_sdk_call(backend, tool, field, invalid):
    arguments = {"project_key": "SOURCE"}
    if tool != "list_project_bundles":
        arguments["bundle_id"] = "v1"
    arguments[field] = invalid
    with pytest.raises(Exception, match=field):
        call(tool, **arguments)
    assert not backend.calls


@pytest.mark.parametrize(
    "tool,method",
    [
        ("list_project_bundles", "GET"),
        ("create_project_bundle", "PUT"),
        ("publish_project_bundle", "POST"),
    ],
)
@pytest.mark.parametrize("exception", [Timeout, DataikuException])
def test_errors_never_expose_backend_credentials(backend, tool, method, exception):
    backend.fail_method = method
    backend.exception = exception
    backend.bundles = [{"bundleId": "v1", "state": "BUILT"}] if method == "POST" else []
    arguments = {"project_key": "SOURCE"}
    if method != "GET":
        arguments["bundle_id"] = "v1"
    with pytest.raises(Exception) as error:
        call(tool, **arguments)
    assert SECRET not in str(error.value)
    if method != "GET":
        assert "before retrying" in str(error.value)


def test_export_timeout_can_be_recovered_without_resubmission(backend):
    backend.fail_after_export = True
    with pytest.raises(Exception, match="may still be running or may have completed"):
        call("create_project_bundle", project_key="SOURCE", bundle_id="v1")
    result = call("list_project_bundles", project_key="SOURCE")
    table = result["bundles"]
    assert dict(zip(table["columns"], table["rows"][0]))["state"] == "BUILT"
    with pytest.raises(Exception, match="already exists"):
        call("create_project_bundle", project_key="SOURCE", bundle_id="v1")
    assert sum(method == "PUT" for method, _, _ in backend.calls) == 1


def test_pinned_design_instance_survives_concurrent_switch(backend, monkeypatch):
    get_client = project_bundles.get_dss_client

    def switch_then_get_client():
        stdio._current_instance = _instance("automation")
        return get_client()

    monkeypatch.setattr(project_bundles, "get_dss_client", switch_then_get_client)
    result = call("create_project_bundle", project_key="SOURCE", bundle_id="v1")
    assert result["instance_name"] == "design"
    assert stdio.get_current_instance().instance_type == "automation"


def test_bundle_tool_metadata_matches_effects():
    async def run():
        for name, readonly, destructive in [
            ("list_project_bundles", True, False),
            ("create_project_bundle", False, True),
            ("publish_project_bundle", False, True),
        ]:
            tool = await mcp.get_tool(name)
            assert tool.title
            assert tool.annotations.readOnlyHint is readonly
            assert tool.annotations.destructiveHint is destructive
            assert tool.annotations.openWorldHint is False
            assert tool.meta["allowed_instance_types"] == ["design"]

    asyncio.run(run())


def test_create_saves_content_before_export_and_preserves_other_settings(backend):
    backend.settings["bundleExporterSettings"]["unrelated"] = "retained"
    before = copy.deepcopy(backend.settings)
    overrides = {
        "includedDatasetsData": [{"name": " input ", "type": "UploadedFiles"}],
        "includedSavedModels": [],
        "includedManagedFolders": [{"id": "folder"}],
        "includedModelEvaluationStores": [{"id": "evaluations"}],
        "includedKnowledgeBanks": [{"id": "knowledge"}],
        "includedLabelingTasks": [{"id": "labels"}],
        "includedCodeStudios": [{"id": "studio"}],
        "includedPromptStudiosHistories": [
            {"promptStudioId": "prompts", "promptId": "prompt"}
        ],
        "exportSavedModelsRequiredVersions": True,
        "exportNotebooksWithOutputs": False,
    }
    result = call(
        "create_project_bundle",
        project_key="SOURCE",
        bundle_id="v1",
        export_options=overrides,
    )
    assert result["status"] == "created"
    expected = {**before["bundleExporterSettings"]["exportOptions"], **overrides}
    expected["includedDatasetsData"] = [{"name": "input", "type": "UploadedFiles"}]
    assert backend.exported_options == [expected]
    assert backend.settings == {
        **before,
        "bundleExporterSettings": {
            **before["bundleExporterSettings"],
            "exportOptions": expected,
        },
    }
    assert [path for _, path, _ in backend.calls] == [
        "/projects/SOURCE/bundles/exported",
        "/projects/SOURCE/settings",
        "/projects/SOURCE/settings",
        "/projects/SOURCE/bundles/exported/v1",
    ]
    assert (
        call("list_project_bundles", project_key="SOURCE")["export_options"] == expected
    )


@pytest.mark.parametrize("exporter", [None, {}, {"exportOptions": None}])
def test_content_can_be_configured_when_saved_options_are_missing(backend, exporter):
    backend.settings["bundleExporterSettings"] = exporter
    call(
        "create_project_bundle",
        project_key="SOURCE",
        bundle_id="v1",
        export_options={"includedDatasetsData": [{"name": "input"}]},
    )
    assert backend.exported_options == [{"includedDatasetsData": [{"name": "input"}]}]


@pytest.mark.parametrize("options", [None, {}])
def test_omitting_content_uses_saved_options_without_a_settings_write(backend, options):
    before = copy.deepcopy(backend.settings)
    call(
        "create_project_bundle",
        project_key="SOURCE",
        bundle_id="v1",
        export_options=options,
    )
    assert backend.settings == before
    assert backend.exported_options == [
        before["bundleExporterSettings"]["exportOptions"]
    ]
    assert all(not path.endswith("/settings") for _, path, _ in backend.calls)


@pytest.mark.parametrize(
    "options",
    [
        {"exportAllDatasets": True},
        {"unknown": True},
        {"exportNotebooks": "false"},
        {"exportNotebooks": 1},
        {"includedDatasetsData": None},
        {"includedDatasetsData": "input"},
        {"includedDatasetsData": ["input"]},
        {"includedDatasetsData": [{"name": " "}]},
        {"includedDatasetsData": [{"name": "input", "unexpected": SECRET}]},
        {"includedDatasetsData": [{"name": "input", "type": 1}]},
        {"includedManagedFolders": [{"name": "folder"}]},
        {"includedPromptStudiosHistories": [{"promptStudioId": "studio"}]},
    ],
)
def test_invalid_content_options_are_rejected_before_sdk_calls(backend, options):
    with pytest.raises(Exception, match="option"):
        call(
            "create_project_bundle",
            project_key="SOURCE",
            bundle_id="v1",
            export_options=options,
        )
    assert not backend.calls


def test_settings_save_failure_does_not_start_export_or_expose_credentials(backend):
    backend.fail_method = "PUT"
    with pytest.raises(
        Exception, match="content options may already be saved"
    ) as error:
        call(
            "create_project_bundle",
            project_key="SOURCE",
            bundle_id="v1",
            export_options={"includedDatasetsData": []},
        )
    assert SECRET not in str(error.value)
    assert not backend.exported_options
    assert backend.calls[-1][1] == "/projects/SOURCE/settings"


def test_export_failure_leaves_saved_content_inspectable(backend):
    backend.fail_after_export = True
    with pytest.raises(Exception, match="before retrying"):
        call(
            "create_project_bundle",
            project_key="SOURCE",
            bundle_id="v1",
            export_options={"includedDatasetsData": []},
        )
    result = call("list_project_bundles", project_key="SOURCE")
    assert result["export_options"]["includedDatasetsData"] == []
    with pytest.raises(Exception, match="already exists"):
        call(
            "create_project_bundle",
            project_key="SOURCE",
            bundle_id="v1",
            export_options={"includedDatasetsData": [{"name": "other"}]},
        )
    assert (
        backend.settings["bundleExporterSettings"]["exportOptions"][
            "includedDatasetsData"
        ]
        == []
    )


def test_list_redacts_export_options_without_returning_other_project_settings(backend):
    backend.settings["bundleExporterSettings"]["exportOptions"]["credentials"] = SECRET
    result = call("list_project_bundles", project_key="SOURCE")
    assert result["export_options"]["credentials"] == "__DATAIKU_REDACTED__"
    assert SECRET not in json.dumps(result)
    assert "unrelated" not in result
