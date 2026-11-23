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
import base64
import copy
import json
import threading
from types import SimpleNamespace

import pytest
from dataikuapi.dss.apideployer import DSSAPIDeployer
from dataikuapi.dss.projectdeployer import DSSProjectDeployer
from dataikuapi.utils import DataikuException, handle_http_exception
from fastmcp import Client
from requests import Timeout

from dataiku_mcp import mcp
from dataiku_mcp.operations.handlers import deployer

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
            "localVariables": {"output_schema": "production", "credential": SECRET},
            "bundleContainerSettings": {
                "remapping": {
                    "connections": [{"source": "development", "target": "production"}]
                },
                "codeEnvsBehavior": "USE_EXISTING",
            },
            "scenariosToActivate": {"refresh": True},
            "untouched": {"nested": "preserved"},
        }
        self.infra_settings = {
            "id": "target",
            "defaultConnectionRemapping": [
                {"source": "development", "target": "production"}
            ],
            "apiNodes": [{"url": "https://node.example", "adminAPIKey": SECRET}],
            "futureSetting": {"enabled": False, "password": SECRET},
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
            "report": {
                "error": True,
                "messages": [
                    {
                        "severity": "ERROR",
                        "code": "IMPORT_FAILED",
                        "title": "Data import failed",
                        "message": "Data import failed: target table is not writable",
                        "details": "target table is not writable",
                    }
                ],
                "activateReport": {
                    "importedDatasets": ["input"],
                    "connection": {"password": SECRET},
                },
            },
            "logs": {"lines": ["Starting deployment", "Data import failed"]},
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
            return copy.deepcopy(
                self.infra_settings if "/infras/" in path else self.settings
            )
        if path.endswith("/governance-status"):
            return {
                "messages": [
                    {
                        "code": "GOVERN",
                        "severity": "WARNING",
                        "title": "Invalid governance status",
                        "details": "The bundle is not governed",
                        "governLink": "https://govern.example/artifact/123",
                        "password": SECRET,
                    }
                ]
            }
        if path.endswith("/status"):
            return {
                "health": "OUT_OF_SYNC",
                "healthMessages": {
                    "messages": [
                        {
                            "code": "SYNC",
                            "severity": "WARNING",
                            "message": "The project is out of sync",
                            "password": SECRET,
                        }
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
    assert SECRET not in json.dumps(result)
    assert all(
        path.startswith(f"/{backend.kind}-deployer/") for _, path, _ in backend.calls
    )
    return result


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
    assert result["health_messages"] == [
        {"severity": "WARNING", "code": "SYNC", "message": "The project is out of sync"}
    ]
    assert result["governance_messages"] == [
        {
            "severity": "WARNING",
            "code": "GOVERN",
            "title": "Invalid governance status",
            "details": "The bundle is not governed",
            "governLink": "https://govern.example/artifact/123",
        }
    ]


def test_published_versions_are_discoverable(backend):
    result = call(deployer.get_deployer_published_item, backend, source_id="source")
    assert result["packages"] == {
        "columns": ["id", "publishedOn", "publishedBy"],
        "rows": [["version", 42, "user"]],
    }
    assert result["canDeploy"] is True
    assert result["canWrite"] is False


def test_update_detail_includes_report_without_logs_or_saved_settings(backend):
    backend.update["infra"] = {"apiKey": SECRET}
    backend.update["deployment"] = backend.settings
    result = call(
        deployer.get_deployer_update,
        backend,
        deployment_id="deployment",
        timestamp="123",
    )
    assert result["report"]["messages"] == backend.update["report"]["messages"]
    assert result["report"]["error"] is True
    assert result["report"]["activateReport"]["connection"]["password"] == (
        "__DATAIKU_REDACTED__"
    )
    assert not {"logs", "error", "infra", "deployment"} & result.keys()
    assert backend.calls[0][1].endswith("/update/123")


def test_update_logs_are_opt_in_and_preserve_all_lines(backend):
    lines = [f"Log line {index}" for index in range(350)]
    backend.update["logs"] = {"lines": lines}
    result = call(
        deployer.get_deployer_update,
        backend,
        deployment_id="deployment",
        include_logs=True,
    )
    assert result["logs"] == lines
    assert backend.calls[0][1].endswith("/last-update")
    assert len(backend.calls) == 1


@pytest.mark.parametrize(
    "prefix",
    [
        "[2026/01/02-03:04:05.006] [FT-1] [INFO] [dku.test]  - ",
        "1234 [FT-1] INFO  dku.test  - [ct: 12] ",
    ],
)
@pytest.mark.parametrize("manifest", ["deployment", "opaque secret"])
def test_update_logs_omit_generated_kubernetes_manifests(backend, prefix, manifest):
    # SingleK8SDeploymentManager logs whole manifests; Secret data is base64,
    # while legacy Deployment env values are plaintext. Neither is safe text.
    encoded = base64.b64encode(SECRET.encode()).decode()
    before = prefix + "Preparing deployment"
    after = prefix + "Applying configuration"
    lines = [
        before,
        prefix + f"final {manifest}:",
        "apiVersion: v1",
        "kind: Secret" if manifest == "opaque secret" else "kind: Deployment",
        "data:" if manifest == "opaque secret" else "spec:",
        "  SERVICE_PASSWORD: " + encoded,
        "  env:",
        "  - name: DATABASE_URL",
        "    value: |",
        "      " + SECRET,
        "      " + SECRET + " final deployment:",
        "      [2026/01/02-03:04:05.006] [FT-1] [INFO] [dku.test]  - " + SECRET,
        "",
        after,
        "Diagnostic continuation",
    ]
    backend.update["logs"] = {"lines": lines}
    result = call(
        deployer.get_deployer_update,
        backend,
        deployment_id="deployment",
        timestamp="123",
        include_logs=True,
    )
    assert result["logs"] == [
        before,
        prefix + f"final {manifest}: [Kubernetes manifest redacted]",
        after,
        "Diagnostic continuation",
    ]
    assert encoded not in json.dumps(result)
    assert backend.update["logs"]["lines"] == lines


@pytest.mark.parametrize("ending", [[], ["CUSTOM INFO - Finished"]])
def test_update_logs_suppress_truncated_or_unrecognized_manifest_continuations(ending):
    lines = ["final opaque secret: " + SECRET, "data:", "  value: " + SECRET]
    assert deployer._redact_deployer_logs(lines + ending) == [
        "final opaque secret: [Kubernetes manifest redacted]"
    ]


def test_update_logs_filter_consecutive_manifests_within_multiline_entries():
    prefix = "[2026/01/02-03:04:05.006] [FT-1] [INFO] [dku.test] context - "
    entry = (
        prefix + "final deployment:\r\n"
        "spec:\r\n"
        "  env: " + SECRET + "\r\n" + prefix + "final opaque secret:\r\n"
        "data:\r\n"
        "  value: " + SECRET + "\r\n" + prefix + "Applying configuration\r\n"
    )
    assert deployer._redact_deployer_logs([entry]) == [
        prefix
        + "final deployment: [Kubernetes manifest redacted]\r\n"
        + prefix
        + "final opaque secret: [Kubernetes manifest redacted]\r\n"
        + prefix
        + "Applying configuration\r\n"
    ]


def test_update_logs_preserve_ordinary_entries_and_apply_shared_redaction():
    lines = [
        "",
        "Ordinary entry\nwith continuation\n",
        "https://user:" + SECRET + "@example.com/path",
    ]
    result = deployer._redact_deployer_logs(lines)
    assert result[:2] == lines[:2]
    assert result[2] == "https://example.com/path"
    assert deployer._redact_deployer_logs(["Ordinary entry"]) == ["Ordinary entry"]


@pytest.mark.parametrize("lines", [None, []])
def test_update_handles_pending_report_and_unavailable_or_empty_logs(backend, lines):
    backend.update.pop("report")
    backend.update.pop("logs")
    if lines is not None:
        backend.update["logs"] = {"lines": lines}
    result = call(
        deployer.get_deployer_update,
        backend,
        deployment_id="deployment",
        include_logs=True,
    )
    assert "report" not in result
    assert result["logs"] == lines


def test_update_lists_remain_compact(backend):
    result = call(deployer.list_deployer_updates, backend, deployment_id="deployment")
    assert result["updates"] == [
        {
            "startTimestamp": 123,
            "endTimestamp": 456,
            "status": "DONE",
            "type": "UPDATE",
        }
    ]


def test_mcp_update_detail_accepts_include_logs(backend, monkeypatch):
    from dataiku_mcp.config import stdio
    from tests.test_instance_policy import _instance
    from tests.test_operations import _call

    backend.update["logs"]["lines"] = [
        "final opaque secret:",
        "data:",
        "  SERVICE_PASSWORD: " + SECRET,
        "1234 [FT-1] INFO  dku.test  - Applying configuration",
    ]
    monkeypatch.setattr(stdio, "_current_instance", _instance("deployer"))
    result = asyncio.run(
        _call(
            "run_read_operation",
            operation_id="deployer.get_update",
            arguments={
                "deployer_type": backend.kind,
                "deployment_id": "deployment",
                "timestamp": "123",
                "include_logs": True,
            },
        )
    )["result"]
    assert result["logs"] == [
        "final opaque secret: [Kubernetes manifest redacted]",
        "1234 [FT-1] INFO  dku.test  - Applying configuration",
    ]
    assert result["report"]["messages"][0]["details"] == "target table is not writable"
    assert SECRET not in json.dumps(result)


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


@pytest.mark.parametrize("action", ["create", "update"])
@pytest.mark.parametrize("severity", ["WARNING", "ERROR"])
def test_governance_warning_requires_explicit_retry(
    backend, monkeypatch, action, severity
):
    code = "ERR_DEPLOYER_INVALID_GOVERNANCE_STATUS"
    report = (
        f"{severity} : Invalid governance status: "
        'The bundle "version" should be approved before deployment, but is not governed.'
    )
    warning = f"com.dataiku.dip.exceptions.CodedException: {report}"
    original_request = backend._request

    def request(method, path, kwargs):
        if method in {"POST", "PUT"} and (
            severity == "ERROR" or not kwargs["params"]["ignoreWarnings"]
        ):
            assert threading.get_ident() != backend.owner_thread
            backend.calls.append((method, path, copy.deepcopy(kwargs)))
            handle_http_exception(
                SimpleNamespace(
                    status_code=500,
                    json=lambda: {
                        "errorType": "com.dataiku.dip.exceptions.CodedException",
                        "errorCode": code,
                        "detailedMessage": report,
                    },
                )
            )
        return original_request(method, path, kwargs)

    monkeypatch.setattr(backend, "_request", request)
    function = (
        deployer.create_deployer_deployment
        if action == "create"
        else deployer.update_deployer_deployment
    )
    arguments = {"deployment_id": "deployment", "version": "version"}
    if action == "create":
        arguments.update(source_id="source", infra_id="target")

    with pytest.raises(RuntimeError, match="Invalid governance status") as error:
        call(function, backend, **arguments)
    assert str(error.value) == warning
    assert error.value.__suppress_context__
    writes = [entry for entry in backend.calls if entry[0] != "GET"]
    assert len(writes) == 1  # No automatic retry with warnings ignored.
    assert writes[0][2]["params"]["ignoreWarnings"] is False

    if severity == "ERROR":
        with pytest.raises(RuntimeError, match="Invalid governance status"):
            call(function, backend, **arguments, ignore_warnings=True)
    else:
        result = call(function, backend, **arguments, ignore_warnings=True)
        assert result["update_started"] is False
    writes = [entry for entry in backend.calls if entry[0] != "GET"]
    assert len(writes) == 2
    assert writes[-1][2]["params"]["ignoreWarnings"] is True


@pytest.mark.parametrize("action", ["create", "update"])
def test_governance_override_schema_defaults_to_false(action):
    from dataiku_mcp.operations.catalog import OPERATIONS

    operation = OPERATIONS[f"deployer.{action}_deployment"]
    field = operation.describe()["input_schema"]["properties"]["ignore_warnings"]
    assert field["type"] == "boolean"
    assert field["default"] is False
    assert "explicit user approval" in field["description"]
    with pytest.raises(ValueError, match="ignore_warnings: bool_type"):
        operation.validate({**operation.example, "ignore_warnings": "true"})
    assert (
        operation.validate({**operation.example, "ignore_warnings": True})[
            "ignore_warnings"
        ]
        is True
    )


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
    from dataiku_mcp.operations.catalog import OPERATIONS

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


def test_dispatch_normalizes_identifiers_before_sdk_calls(backend, monkeypatch):
    from dataiku_mcp.config import stdio
    from tests.test_instance_policy import _instance
    from tests.test_operations import _call

    monkeypatch.setattr(stdio, "_current_instance", _instance("deployer"))
    result = asyncio.run(
        _call(
            "run_read_operation",
            operation_id="deployer.get_update",
            arguments={
                "deployer_type": backend.kind,
                "deployment_id": " deployment ",
                "timestamp": " 123 ",
            },
        )
    )
    assert result["result"]["status"] == "DONE"
    assert [(method, path) for method, path, _ in backend.calls] == [
        ("GET", f"/{backend.kind}-deployer/deployments/deployment/update/123")
    ]


@pytest.mark.parametrize(
    "operation_id,field",
    [
        ("deployer.get_infrastructure", "infra_id"),
        ("deployer.get_published_item", "source_id"),
        ("deployer.get_deployment", "deployment_id"),
        ("deployer.list_updates", "deployment_id"),
        ("deployer.get_update", "deployment_id"),
        ("deployer.get_update", "timestamp"),
        ("deployer.create_deployment", "deployment_id"),
        ("deployer.create_deployment", "source_id"),
        ("deployer.create_deployment", "infra_id"),
        ("deployer.create_deployment", "deployed_project_key"),
        ("deployer.create_deployment", "project_folder_id"),
        ("deployer.create_deployment", "endpoint_id"),
        ("deployer.update_deployment", "deployment_id"),
        ("deployer.start_update", "deployment_id"),
        ("deployer.get_future_status", "future_id"),
    ],
)
def test_direct_handlers_validate_identifiers_before_sdk_calls(
    monkeypatch, operation_id, field
):
    from dataiku_mcp.operations.catalog import get_operation

    monkeypatch.setattr(
        deployer,
        "get_dss_client",
        lambda: pytest.fail("Invalid identifier reached SDK"),
    )
    operation = get_operation(operation_id)
    arguments = {**operation.example, field: "invalid?identifier"}
    if field == "endpoint_id":
        arguments["deployer_type"] = "api"
    with pytest.raises(ValueError, match=field):
        asyncio.run(operation.handler(**arguments))


def test_infrastructure_detail_includes_redacted_saved_settings(backend):
    before = copy.deepcopy(backend.infra_settings)
    result = call(deployer.get_deployer_infrastructure, backend, infra_id="target")
    assert result["settings"] == {
        "id": "target",
        "defaultConnectionRemapping": [
            {"source": "development", "target": "production"}
        ],
        "apiNodes": [
            {"url": "https://node.example", "adminAPIKey": "__DATAIKU_REDACTED__"}
        ],
        "futureSetting": {"enabled": False, "password": "__DATAIKU_REDACTED__"},
    }
    assert result["infraBasicInfo"]["id"] == "target"
    assert result["canDeploy"] is True
    assert result["deployments"][0]["id"] == "deployment"
    assert backend.infra_settings == before
    assert [(method, path) for method, path, _ in backend.calls] == [
        ("GET", f"/{backend.kind}-deployer/infras/target"),
        ("GET", f"/{backend.kind}-deployer/infras/target/settings"),
    ]


def test_deployment_detail_keeps_native_settings_and_redacts_nested_credentials(
    backend,
):
    before = copy.deepcopy(backend.settings)
    result = call(deployer.get_deployer_deployment, backend, deployment_id="deployment")
    settings = result["settings"]
    assert set(settings) == set(before)
    assert settings["bundleContainerSettings"] == before["bundleContainerSettings"]
    assert settings["localVariables"] == {
        "output_schema": "production",
        "credential": "__DATAIKU_REDACTED__",
    }
    assert settings["auth"] == {"apiKeys": "__DATAIKU_REDACTED__"}
    assert settings["scenariosToActivate"] == {"refresh": True}
    assert settings["untouched"] == before["untouched"]
    assert backend.settings == before
    assert all(method == "GET" for method, _, _ in backend.calls)
    assert sum(path.endswith("/settings") for _, path, _ in backend.calls) == 1


@pytest.mark.parametrize(
    "function",
    [deployer.list_deployer_infrastructures, deployer.list_deployer_deployments],
)
def test_list_responses_remain_compact_without_settings_reads(backend, function):
    result = call(function, backend)
    assert "settings" not in json.dumps(result)
    assert "localVariables" not in json.dumps(result)
    assert "bundleContainerSettings" not in json.dumps(result)
    assert all(not path.endswith("/settings") for _, path, _ in backend.calls)


@pytest.mark.parametrize(
    "function,arguments",
    [
        (deployer.get_deployer_infrastructure, {"infra_id": "target"}),
        (deployer.get_deployer_deployment, {"deployment_id": "deployment"}),
    ],
)
def test_detail_settings_read_errors_are_safely_reported(
    backend, monkeypatch, function, arguments
):
    request = backend._perform_json

    def fail_settings(method, path, **kwargs):
        if path.endswith("/settings"):
            raise DataikuException(SECRET)
        return request(method, path, **kwargs)

    monkeypatch.setattr(backend, "_perform_json", fail_settings)
    with pytest.raises(RuntimeError) as error:
        call(function, backend, **arguments)
    assert SECRET not in str(error.value)
    assert error.value.__suppress_context__
    assert all(method == "GET" for method, _, _ in backend.calls)


@pytest.mark.parametrize(
    "operation,arguments",
    [
        ("deployer.get_infrastructure", {"infra_id": "target"}),
        ("deployer.get_deployment", {"deployment_id": "deployment"}),
    ],
)
def test_mcp_detail_reads_include_settings_without_new_arguments(
    backend, monkeypatch, operation, arguments
):
    from dataiku_mcp.config import stdio
    from tests.test_instance_policy import _instance

    monkeypatch.setattr(stdio, "_current_instance", _instance("deployer"))

    async def run():
        async with Client(mcp) as client:
            result = await client.call_tool(
                "run_read_operation",
                {
                    "operation_id": operation,
                    "arguments": {"deployer_type": backend.kind, **arguments},
                },
            )
            return json.loads(result.content[0].text)

    result = asyncio.run(run())
    assert result["operation_id"] == operation
    assert result["result"]["settings"]["id"] in {"target", "deployment"}
    assert "__DATAIKU_REDACTED__" in json.dumps(result["result"]["settings"])
    assert SECRET not in json.dumps(result)
    assert all(method == "GET" for method, _, _ in backend.calls)
