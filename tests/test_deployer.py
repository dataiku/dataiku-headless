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

"""Deployer SDK contract, async boundary and secret-exposure regressions."""

import asyncio
import copy
import json
import threading
from types import SimpleNamespace

import pytest
from dataikuapi.dss.apideployer import DSSAPIDeployer
from dataikuapi.dss.projectdeployer import DSSProjectDeployer
from dataikuapi.utils import DataikuException
from fastmcp import Client
from requests import Timeout

from dataiku_mcp import mcp
from dataiku_mcp.tools import deployer

SECRET = "DO_NOT_RETURN_THIS_SECRET"


class Backend:
    """Use real SDK handles against an in-memory HTTP boundary."""

    def __init__(self, kind):
        self.kind = kind
        self.calls = []
        self.owner_thread = threading.get_ident()
        self.settings = {
            "id": "deployment",
            "infraId": "target",
            "bundleId": "old",
            "publishedProjectKey": "source",
            "publishedServiceId": "source",
            "enabled": True,
            "generationsMapping": {
                "mode": "MULTI_GENERATION",
                "entries": [
                    {"generation": "old", "proba": 0.5},
                    {"generation": "other", "proba": 0.5},
                ],
            },
            "auth": {"apiKeys": [{"key": SECRET}]},
            "localVariables": {"credential": SECRET},
            "untouched": {"nested": "preserved"},
        }
        self.info = {
            "infraBasicInfo": {
                "id": "target",
                "stage": "stage",
                "infraType": "STATIC",
                "apiKey": SECRET,
                "prePushScript": SECRET,
            },
            "projectBasicInfo": {"id": "source", "name": "Source"},
            "serviceBasicInfo": {"id": "source", "name": "Source"},
            "deploymentBasicInfo": {**self.settings, "futureSecret": SECRET},
            "packages": [
                {
                    "id": "version",
                    "publishedOn": 42,
                    "publishedBy": "user",
                    "endpoints": [{"code": SECRET}],
                }
            ],
            "deployments": [self.settings],
            "infras": [{"id": "target", "password": SECRET}],
            "canDeploy": True,
            "canWrite": False,
            "apiKeys": [{"key": SECRET}],
            "authorizationInherited": {"apiKeys": [{"key": SECRET}]},
            "oauth2Config": {"clientSecret": SECRET},
        }
        self.update = {
            "startTimestamp": 123,
            "endTimestamp": 456,
            "status": "DONE",
            "type": "UPDATE",
            "logs": {"lines": [SECRET]},
            "error": SECRET,
        }

    def _request(self, method, path, kwargs):
        assert threading.get_ident() != self.owner_thread, "SDK called on event loop"
        self.calls.append((method, path, copy.deepcopy(kwargs)))
        if method == "PUT":
            self.settings = copy.deepcopy(kwargs["body"])
            return None
        if method == "POST" and path.endswith("/actions/update"):
            return {"jobId": "future", "hasResult": False}
        if method == "POST":
            return {}
        if path.endswith("/settings"):
            return copy.deepcopy(self.settings)
        if path.endswith("/governance-status"):
            return {
                "messages": [
                    {"code": "GOVERN", "severity": "WARNING", "details": SECRET}
                ]
            }
        if path.endswith("/status"):
            return {
                "health": "OUT_OF_SYNC",
                "healthMessages": {
                    "messages": [
                        {"code": "SYNC", "severity": "WARNING", "message": SECRET}
                    ]
                },
                "apiNodes": [{"apiKey": SECRET}],
            }
        if path.endswith("/stages"):
            return [{"id": "stage", "desc": "Stage"}]
        if path.endswith("/update"):
            return [self.update]
        if path.endswith("/last-update") or "/update/" in path:
            return self.update
        if path.rsplit("/", 1)[-1] in {"deployments", "infras", "projects", "services"}:
            return [copy.deepcopy(self.info)]
        return copy.deepcopy(self.info)

    def _perform_json(self, method, path, **kwargs):
        return self._request(method, path, kwargs)

    def _perform_empty(self, method, path, **kwargs):
        return self._request(method, path, kwargs)


@pytest.fixture(params=["project", "api"])
def backend(request, monkeypatch):
    fake = Backend(request.param)
    client = SimpleNamespace(
        get_projectdeployer=lambda: DSSProjectDeployer(fake),
        get_apideployer=lambda: DSSAPIDeployer(fake),
    )

    def get_client():
        assert threading.get_ident() != fake.owner_thread
        return client

    monkeypatch.setattr(deployer, "get_dss_client", get_client)
    return fake


def call(function, backend, **kwargs):
    result = asyncio.run(function(deployer_type=backend.kind, **kwargs))
    assert SECRET not in result
    assert all(
        path.startswith(f"/{backend.kind}-deployer/") for _, path, _ in backend.calls
    )
    return json.loads(result)


@pytest.mark.parametrize(
    "function, kwargs",
    [
        (deployer.list_deployer_stages, {}),
        (deployer.list_deployer_infrastructures, {}),
        (deployer.get_deployer_infrastructure, {"infra_id": "target"}),
        (deployer.list_deployer_published_items, {}),
        (deployer.get_deployer_published_item, {"source_id": "source"}),
        (deployer.list_deployer_deployments, {}),
        (deployer.get_deployer_deployment, {"deployment_id": "deployment"}),
        (deployer.list_deployer_updates, {"deployment_id": "deployment"}),
        (deployer.get_deployer_update, {"deployment_id": "deployment"}),
        (
            deployer.get_deployer_update,
            {"deployment_id": "deployment", "timestamp": "123"},
        ),
    ],
)
def test_read_tools_use_sdk_off_loop_and_omit_secrets(backend, function, kwargs):
    result = call(function, backend, **kwargs)
    assert result
    assert all(method == "GET" for method, _, _ in backend.calls)


def test_deployment_detail_reports_health_mapping_and_codes(backend):
    result = call(deployer.get_deployer_deployment, backend, deployment_id="deployment")
    assert result["health"] == "OUT_OF_SYNC"
    assert result["settings"]["enabled"] is True
    assert result["settings"]["generationsMapping"]["entries"][1] == {
        "generation": "other",
        "proba": 0.5,
    }
    assert result["health_messages"] == [{"severity": "WARNING", "code": "SYNC"}]
    assert result["governance_messages"] == [{"severity": "WARNING", "code": "GOVERN"}]


def test_published_versions_are_discoverable(backend):
    result = call(deployer.get_deployer_published_item, backend, source_id="source")
    assert result["packages"] == {
        "columns": ["id", "publishedOn", "publishedBy"],
        "rows": [["version", 42, "user"]],
    }
    assert result["canDeploy"] is True
    assert result["canWrite"] is False


def test_create_only_saves_configuration(backend):
    options = (
        {"deployed_project_key": "destination", "project_folder_id": "folder"}
        if backend.kind == "project"
        else {"endpoint_id": "endpoint"}
    )
    result = call(
        deployer.create_deployer_deployment,
        backend,
        deployment_id="new",
        source_id="source",
        infra_id="target",
        version="version",
        **options,
    )
    assert result == {
        "deployment_id": "new",
        "status": "configuration_created",
        "update_started": False,
    }
    [(method, path, params)] = backend.calls
    assert method == "POST"
    assert path.endswith("/deployments")
    assert params["params"]["ignoreWarnings"] is False
    assert (
        params["body"]["bundleId" if backend.kind == "project" else "version"]
        == "version"
    )
    assert (
        params["body"][
            "publishedProjectKey" if backend.kind == "project" else "publishedServiceId"
        ]
        == "source"
    )
    if backend.kind == "project":
        assert params["body"]["deployedProjectKey"] == "destination"
        assert params["body"]["projectFolderId"] == "folder"
    else:
        assert params["body"]["endpointId"] == "endpoint"


def test_version_change_preserves_other_settings_and_governance(backend):
    before = copy.deepcopy(backend.settings)
    result = call(
        deployer.update_deployer_deployment,
        backend,
        deployment_id="deployment",
        version="version",
    )
    assert result["update_started"] is False
    after = backend.settings
    assert after["untouched"] == before["untouched"]
    assert after["auth"] == before["auth"]
    assert after["localVariables"] == before["localVariables"]
    if backend.kind == "project":
        assert after["bundleId"] == "version"
        assert after["generationsMapping"] == before["generationsMapping"]
    else:
        assert after["generationsMapping"] == {
            "mode": "SINGLE_GENERATION",
            "generation": "version",
        }
    assert [method for method, _, _ in backend.calls] == ["GET", "PUT"]
    assert backend.calls[-1][2]["params"]["ignoreWarnings"] is False


def test_api_disable_preserves_version_mapping(backend):
    if backend.kind == "project":
        with pytest.raises(ValueError, match="API"):
            call(
                deployer.update_deployer_deployment,
                backend,
                deployment_id="deployment",
                enabled=False,
            )
        assert not backend.calls
    else:
        mapping = copy.deepcopy(backend.settings["generationsMapping"])
        call(
            deployer.update_deployer_deployment,
            backend,
            deployment_id="deployment",
            enabled=False,
        )
        assert backend.settings["enabled"] is False
        assert backend.settings["generationsMapping"] == mapping


def test_start_returns_durable_future_without_polling(backend):
    result = call(deployer.start_deployer_update, backend, deployment_id="deployment")
    assert result["future_id"] == "future"
    assert result["status"] == "update_submitted"
    assert [(method, path) for method, path, _ in backend.calls] == [
        ("POST", f"/{backend.kind}-deployer/deployments/deployment/actions/update")
    ]


@pytest.mark.parametrize("options", [{}, {"version": ""}, {"version": "  "}])
def test_invalid_changes_do_not_call_sdk(backend, options):
    with pytest.raises(ValueError):
        call(
            deployer.update_deployer_deployment,
            backend,
            deployment_id="deployment",
            **options,
        )
    assert not backend.calls


def test_rejects_component_specific_create_arguments(backend):
    options = (
        {"endpoint_id": "endpoint"}
        if backend.kind == "project"
        else {"project_folder_id": "folder"}
    )
    with pytest.raises(ValueError):
        call(
            deployer.create_deployer_deployment,
            backend,
            deployment_id="new",
            source_id="source",
            infra_id="target",
            version="version",
            **options,
        )
    assert not backend.calls


@pytest.mark.parametrize("exception", [DataikuException, Timeout])
def test_sdk_error_has_no_sensitive_text_or_cause(backend, monkeypatch, exception):
    def fail(*args, **kwargs):
        raise exception(SECRET)

    monkeypatch.setattr(backend, "_perform_json", fail)
    with pytest.raises(RuntimeError) as error:
        call(deployer.start_deployer_update, backend, deployment_id="deployment")
    assert SECRET not in str(error.value)
    assert "before retrying" in str(error.value)
    assert error.value.__suppress_context__


def test_mcp_schema_rejects_unknown_deployer_type(monkeypatch):
    from dataiku_mcp.config import stdio

    monkeypatch.setattr(
        stdio,
        "_current_instance",
        SimpleNamespace(name="test", instance_type="deployer"),
    )

    async def run():
        async with Client(mcp) as client:
            with pytest.raises(Exception, match="Invalid operation arguments"):
                await client.call_tool(
                    "run_read_operation",
                    {
                        "operation_id": "deployer.list_stages",
                        "arguments": {"deployer_type": "automation"},
                    },
                )

    asyncio.run(run())


def test_mcp_keeps_deployer_target_when_active_instance_changes(backend, monkeypatch):
    from dataiku_mcp.config import request, stdio
    from dataiku_mcp.config.models import DSSInstance

    original = DSSInstance(
        name="local-deployer",
        url="https://local.example",
        instance_type="deployer",
        api_key="placeholder",
        source="config",
        no_check_certificate=False,
    )
    other = DSSInstance(
        name="other",
        url="https://other.example",
        instance_type="design",
        api_key="placeholder",
        source="config",
        no_check_certificate=False,
    )
    monkeypatch.setattr(stdio, "_current_instance", original)
    observed = []

    def get_client():
        stdio._current_instance = other
        observed.append(request.get_pinned_instance().name)
        assert request.get_pinned_instance().instance_type == "deployer"
        return SimpleNamespace(
            get_projectdeployer=lambda: DSSProjectDeployer(backend),
            get_apideployer=lambda: DSSAPIDeployer(backend),
        )

    monkeypatch.setattr(deployer, "get_dss_client", get_client)

    async def run():
        async with Client(mcp) as client:
            result = await client.call_tool(
                "run_read_operation",
                {
                    "operation_id": "deployer.list_stages",
                    "arguments": {"deployer_type": backend.kind},
                },
            )
            assert not result.is_error

    asyncio.run(run())
    assert observed == ["local-deployer"]
    assert stdio.get_current_instance() == other


def test_deployer_is_exposed_only_as_operations():
    from dataiku_mcp.operations_catalog import OPERATIONS

    tools = asyncio.run(mcp.list_tools())
    assert not any("deployer" in tool.name for tool in tools)
    operations = [op for op in OPERATIONS.values() if op.domain == "deployer"]
    assert len(operations) == 13
    assert all(op.allowed_instance_types == ("deployer",) for op in operations)
    assert OPERATIONS["deployer.start_update"].destructive
    assert not OPERATIONS["deployer.list_stages"].destructive


def test_start_without_future_id_does_not_fetch_or_leak_result(backend, monkeypatch):
    monkeypatch.setattr(
        backend,
        "_perform_json",
        lambda *args, **kwargs: {"hasResult": True, "result": SECRET},
    )
    result = call(deployer.start_deployer_update, backend, deployment_id="deployment")
    assert result["future_id"] is None
    assert "inspect update history" in result["hint"]
