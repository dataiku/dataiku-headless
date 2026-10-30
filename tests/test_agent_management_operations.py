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

"""Expanded product coverage, SDK routing, authentication and local-file boundaries."""

import asyncio
import copy
import json
import threading
from dataclasses import replace
from types import SimpleNamespace

import pytest
import requests
from dataikuapi.utils import DataikuException
from fastmcp import Client

from dataiku_mcp import mcp, auth, server
from dataiku_mcp.config import http, request, stdio
from dataiku_mcp.operations_catalog import OPERATIONS
from dataiku_mcp.operation_registry import get_operation
from dataiku_mcp.tools import agent_management, deployer
from tests.test_instance_policy import _instance
from tests.test_operations import _call, _http_setup

SECRET = "do-not-return-this-secret"

EXPECTED_AGENT_MANAGEMENT_IDS = {
    "delete_agent",
    "abort_platform_operation",
    "get_agent_operation",
    "scan_platform",
    "rename_tag",
    "update_platform_settings",
    "create_agent",
    "setup_agent_monitoring",
    "get_agent_risk_assessment",
    "list_tags",
    "create_platform",
    "get_agent_operation_result",
    "delete_tag",
    "get_platform",
    "list_platforms",
    "delete_platform",
    "get_platform_operation_result",
    "update_settings",
    "update_risk_taxonomy",
    "run_platform_uptime_tests",
    "abort_agent_operation",
    "search_operations",
    "evaluate_alerts",
    "get_agent_uptime_results",
    "get_metric_buckets",
    "search_agents",
    "update_agent_settings",
    "get_agent",
    "fetch_agent_operational_metrics",
    "fetch_agent_logs",
    "sign_off_agent_risk_assessment",
    "update_agent_risk_assessment",
    "get_settings",
    "update_tag",
    "remove_agent_risk_sign_off",
    "get_default_risk_taxonomy",
    "get_platform_settings",
    "compute_risk_taxonomy_replacement_impact",
    "get_risk_taxonomy",
    "get_agent_settings",
    "get_available_metric_ids",
    "download_agent_risk_evidence",
    "get_platform_operation",
    "get_metric_time_series",
    "get_risk_exposure",
    "get_agent_status",
}


class EvidenceResponse:
    headers = {"Content-Type": "application/octet-stream"}

    def __init__(self):
        self.closed = False

    def iter_content(self, chunk_size):
        yield b"evidence"

    def close(self):
        self.closed = True


class AgentManagementBackend:
    """Fake HTTP boundary beneath the real public SDK objects."""

    def __init__(self):
        self.calls = []
        self.main_thread = threading.get_ident()
        self.settings = {
            "fetchedRevision": "revision-from-read",
            "displayName": "Original",
            "connection": {"password": SECRET},
            "untouched": 7,
            "businessKPIs": [],
        }

    def send(self, session, prepared, **kwargs):
        from urllib.parse import urlsplit

        assert threading.get_ident() != self.main_thread
        path = urlsplit(prepared.url).path
        assert path.startswith("/dip/publicapi/agent-management/")
        self.calls.append(prepared)
        payload = {"ok": True, "password": SECRET}
        if path.endswith("/platforms"):
            payload = (
                [{"id": "discovered-platform"}]
                if prepared.method == "GET"
                else {"id": "requested-platform"}
            )
        elif path.endswith("/agents/search"):
            payload = {
                "agents": [{"id": "discovered-agent", "password": SECRET}],
                "facets": {},
            }
        elif path.endswith("/operations/search"):
            payload = {
                "operations": [
                    {
                        "id": "operation",
                        "infraId": "discovered-platform",
                        "password": SECRET,
                    }
                ],
                "hasMore": True,
            }
        elif "/agents/metrics/" in path:
            payload = []
        elif path.endswith("/tags"):
            payload = [{"name": "discovered-tag", "color": "red"}]
        elif "/tags/" in path:
            payload = {"name": "requested-tag", "color": "blue"}
        elif path.endswith("/settings"):
            if prepared.method == "PUT":
                self.settings = json.loads(prepared.body)
            payload = self.settings
        elif path.endswith("/risk-exposure"):
            payload = {"exposure": {"value": 2, "password": SECRET}}
        elif "/risk-taxonomy" in path:
            payload = {
                "taxonomy": {},
                "fetchedRevision": "revision-from-read",
                "fingerprint": "fingerprint-from-impact",
            }
        elif "/risk-assessment/evidences/" in path:
            response = requests.Response()
            response.status_code = 200
            response._content = b"evidence"
            response._content_consumed = True
            return response
        elif "/risk-assessment" in path:
            payload = {"assessment": {}, "fetchedRevision": "revision-from-read"}
        elif path.endswith("/agents") and prepared.method == "POST":
            payload = {"id": "requested-agent"}
        elif path.endswith("/evaluate-alerts"):
            payload = {"queuedAgentCount": 2}
        elif "/actions/" in path:
            payload = {
                "operation": {"id": "returned-operation", "agentId": "discovered-agent"}
            }
        elif path.endswith("/result"):
            payload = {"result": {"value": 1, "password": SECRET}}
        response = requests.Response()
        response.status_code = 200
        response._content = json.dumps(payload).encode()
        return response


@pytest.mark.parametrize("name", sorted(EXPECTED_AGENT_MANAGEMENT_IDS))
def test_every_agent_management_action_uses_real_public_sdk(
    monkeypatch, tmp_path, name
):
    operation = OPERATIONS["agent-management." + name]
    monkeypatch.setattr(stdio, "_current_instance", _instance("agent-management"))
    backend = AgentManagementBackend()
    monkeypatch.setattr(
        requests.Session,
        "send",
        lambda session, prepared, **kwargs: backend.send(session, prepared, **kwargs),
    )
    arguments = copy.deepcopy(operation.example)
    if "output_path" in operation.local_file_fields:
        arguments["output_path"] = str(tmp_path / "evidence.bin")
    result = asyncio.run(
        _call(
            "run_read_operation"
            if operation.effect == "read"
            else "run_write_operation",
            operation_id=operation.operation_id,
            arguments=arguments,
        )
    )
    assert backend.calls
    assert SECRET not in json.dumps(result)
    if "output_path" in operation.local_file_fields:
        assert (tmp_path / "evidence.bin").read_bytes() == b"evidence"
    if name in {
        "scan_platform",
        "fetch_agent_logs",
        "fetch_agent_operational_metrics",
        "run_platform_uptime_tests",
    }:
        assert result["result"]["operation_id"] == "returned-operation"
    if name == "evaluate_alerts":
        assert result["result"] == {"queued_agent_count": 2}


def test_agent_management_post_searches_are_reads_and_alerts_require_scope():
    assert OPERATIONS["agent-management.search_agents"].effect == "read"
    assert OPERATIONS["agent-management.search_operations"].effect == "read"
    operation = OPERATIONS["agent-management.evaluate_alerts"]
    assert operation.effect == "write"
    with pytest.raises(ValueError):
        operation.validate({})
    operation.validate({"scope": "all_writable_agents"})
    operation.validate({"agent_filter": {"favorites": False}})
    with pytest.raises(ValueError):
        operation.validate({"agent_filter": {"platform_ids": []}})


def test_backend_defined_settings_require_objects_not_scalars():
    for name, field in [
        ("update_platform_settings", "changes"),
        ("update_agent_settings", "changes"),
        ("update_risk_taxonomy", "taxonomy"),
    ]:
        operation = OPERATIONS["agent-management." + name]
        with pytest.raises(ValueError):
            operation.validate({**operation.example, field: 42})
        assert "Backend-defined" in json.dumps(operation.describe()["input_schema"])


def test_agent_management_local_files_rejected_before_sdk_execution(monkeypatch):
    events = _http_setup(monkeypatch, "agent-management")
    args = {
        "platform_id": "platform",
        "agent_id": "agent",
        "assessment": {},
        "expected_revision": "revision-from-read",
        "documents": {"evidence": "/private/local-file"},
    }

    async def run():
        async with Client(mcp) as client:
            result = await client.call_tool(
                "run_write_operation",
                {
                    "operation_id": "agent-management.update_agent_risk_assessment",
                    "arguments": args,
                },
                raise_on_error=False,
            )
            assert result.is_error
            assert "filesystem" in result.content[0].text

    asyncio.run(run())
    assert events == ["exchange"]


def test_agent_management_multipart_without_files_uses_native_http_auth(monkeypatch):
    events = _http_setup(monkeypatch, "agent-management")
    backend = AgentManagementBackend()

    def send(session, prepared, **kwargs):
        assert prepared.headers["Authorization"] == "Bearer backend-token"
        assert "X-DKU-APITicket" not in prepared.headers
        return backend.send(session, prepared, **kwargs)

    monkeypatch.setattr(requests.Session, "send", send)
    asyncio.run(
        _call(
            "run_write_operation",
            operation_id="agent-management.update_agent_risk_assessment",
            arguments={
                "platform_id": "platform",
                "agent_id": "agent",
                "assessment": {},
                "expected_revision": "revision-from-read",
            },
        )
    )
    assert events == ["exchange"]
    assert len(backend.calls) == 2
    assert b"revision-from-read" in backend.calls[-1].body
    assert b"filename=" not in backend.calls[-1].body


def test_binary_download_does_not_clobber_destination_created_during_transfer(
    monkeypatch, tmp_path
):
    destination = tmp_path / "evidence.bin"
    response = EvidenceResponse()

    def chunks(chunk_size):
        destination.write_bytes(b"created-concurrently")
        yield b"replacement"

    response.iter_content = chunks
    with pytest.raises(FileExistsError):
        agent_management._download_binary(
            response,
            str(destination),
            False,
        )
    assert destination.read_bytes() == b"created-concurrently"
    assert response.closed
    assert list(tmp_path.iterdir()) == [destination]


def test_redacted_credentials_cannot_be_written_back(monkeypatch):
    events = _http_setup(monkeypatch, "agent-management")

    async def run():
        async with Client(mcp) as client:
            result = await client.call_tool(
                "run_write_operation",
                {
                    "operation_id": "agent-management.update_settings",
                    "arguments": {
                        "body": {"connection": {"password": "__DATAIKU_REDACTED__"}}
                    },
                },
                raise_on_error=False,
            )
            assert result.is_error
            assert "redacted result placeholders" in result.content[0].text

    asyncio.run(run())
    assert events == ["exchange"]


@pytest.mark.parametrize("kind", ["key", "ticket", "http"])
def test_native_agent_management_sdk_preserves_credentials_and_certificates(
    monkeypatch, kind
):
    instance = replace(
        _instance("agent-management"),
        api_key=SECRET if kind == "key" else None,
        api_ticket=SECRET if kind == "ticket" else None,
        encrypted_rpc_cert_path="/private/certificate.pem",
    )
    monkeypatch.setattr(request, "get_pinned_instance", lambda: instance)
    monkeypatch.setattr(request, "is_http_request", lambda: kind == "http")
    monkeypatch.setattr(request, "get_http_dss_token", lambda: SECRET)
    client = auth.get_dss_client().get_agent_management_client()
    prepared = client._session.prepare_request(requests.Request("GET", instance.url))
    assert client._session.verify == "/private/certificate.pem"
    assert prepared.headers["X-DKU-Client-Application"] == "dataiku-headless"
    if kind == "http":
        assert prepared.headers["Authorization"] == "Bearer " + SECRET
        assert "X-DKU-APITicket" not in prepared.headers
    elif kind == "ticket":
        assert prepared.headers["X-DKU-APITicket"] == SECRET
        assert "Authorization" not in prepared.headers
    else:
        assert prepared.headers["Authorization"].startswith("Basic ")


@pytest.mark.parametrize(
    "operation_name", ["get_metric_time_series", "get_metric_buckets"]
)
def test_native_metric_results_and_sdk_filter_mapping(monkeypatch, operation_name):
    monkeypatch.setattr(stdio, "_current_instance", _instance("agent-management"))
    calls = []
    bucketed = operation_name == "get_metric_buckets"

    def send(session, prepared, **kwargs):
        calls.append(json.loads(prepared.body))
        response = requests.Response()
        response.status_code = 200
        response._content = json.dumps(
            [
                {
                    "infrastructureName": "platform",
                    "agentId": "agent",
                    "columns": ["start", "end", "activity.interactions"]
                    if bucketed
                    else ["timestamp", "activity.interactions"],
                    "rows": [[0, 86400000, 0]] if bucketed else [[0, 0]],
                }
            ]
        ).encode()
        return response

    monkeypatch.setattr(requests.Session, "send", send)
    args = {
        "metrics": ["activity.interactions"],
        "from_time": 0,
        "to_time": 86400000,
        "agent_filter": {
            "platform_ids": ["platform"],
            "agent_ids": ["agent"],
            "favorites": False,
        },
    }
    if bucketed:
        args["bucket"] = "DAY"
    result = asyncio.run(
        _call(
            "run_read_operation",
            operation_id="agent-management." + operation_name,
            arguments=args,
        )
    )
    assert calls[0]["agentFilter"] == {
        "platformName": ["platform"],
        "agentId": ["agent"],
        "favorites": False,
    }
    assert result["result"][0]["rows"][0][-1] == 0
    assert result["result"][0]["rows"][0][0] == "1970-01-01 00:00:00+00:00"


def test_risk_evidence_upload_uses_sdk_revision_and_document_mapping(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(stdio, "_current_instance", _instance("agent-management"))
    backend = AgentManagementBackend()
    monkeypatch.setattr(
        requests.Session,
        "send",
        lambda session, prepared, **kwargs: backend.send(session, prepared, **kwargs),
    )
    document = tmp_path / "evidence.txt"
    document.write_text("evidence contents")
    asyncio.run(
        _call(
            "run_write_operation",
            operation_id="agent-management.update_agent_risk_assessment",
            arguments={
                "platform_id": "platform",
                "agent_id": "agent",
                "assessment": {"answer": 0},
                "expected_revision": "inspected-revision",
                "documents": {"evidence-id": str(document)},
            },
        )
    )
    sent = backend.calls[-1]
    assert sent.method == "PUT"
    assert b"inspected-revision" in sent.body
    assert b'name="fetchedRevision"' in sent.body
    assert b"evidence-id" in sent.body
    assert b"evidence.txt" in sent.body
    assert b"evidence contents" in sent.body


@pytest.fixture
def selected(monkeypatch):
    instance = _instance("agent-management")
    monkeypatch.setattr(stdio, "_current_instance", instance)
    return instance


@pytest.mark.parametrize(
    "kind, total",
    [
        ("deployer", 13),
        ("agent-management", 46),
        ("govern", 86),
    ],
)
def test_search_filters_without_mutating_catalog(monkeypatch, kind, total):
    monkeypatch.setattr(stdio, "_current_instance", _instance(kind))

    async def run():
        before = {tool.name for tool in await mcp.list_tools()}
        result = await _call("search_operations", limit=50)
        assert result["total"] == total
        assert {tool.name for tool in await mcp.list_tools()} == before

    asyncio.run(run())


def test_search_query_effect_and_describe_disallowed(selected):
    result = asyncio.run(
        _call("search_operations", query="agent settings", effect="write")
    )
    assert "agent-management.update_agent_settings" in [
        op["operation_id"] for op in result["operations"]
    ]
    detail = asyncio.run(
        _call("describe_operation", operation_id="deployer.start_update")
    )
    assert detail["allowed_on_selected_instance"] is False


@pytest.mark.parametrize(
    "tool, operation_id, arguments, kind",
    [
        (
            "run_read_operation",
            "agent-management.update_agent_settings",
            {},
            "agent-management",
        ),
        (
            "run_write_operation",
            "agent-management.get_platform",
            {"platform_id": "platform"},
            "agent-management",
        ),
        (
            "run_read_operation",
            "deployer.list_stages",
            {"deployer_type": "project"},
            "agent-management",
        ),
        ("run_read_operation", "agent-management.list_platforms", {}, "deployer"),
        ("run_read_operation", "not-in-catalog", {}, "design"),
        (
            "run_read_operation",
            "agent-management.get_platform",
            {"platform_id": "platform", "path": "/admin"},
            "agent-management",
        ),
        (
            "run_read_operation",
            "agent-management.get_platform",
            42,
            "agent-management",
        ),
    ],
)
def test_invalid_operation_rejected_before_sdk_execution(
    monkeypatch, tool, operation_id, arguments, kind
):
    events = _http_setup(monkeypatch, kind)
    sdk_calls = []

    def unexpected_client():
        sdk_calls.append(True)
        raise AssertionError("Invalid operations must not reach the SDK")

    monkeypatch.setattr(agent_management, "get_dss_client", unexpected_client)
    monkeypatch.setattr(deployer, "get_dss_client", unexpected_client)

    async def run():
        async with Client(mcp) as client:
            result = await client.call_tool(
                tool,
                {"operation_id": operation_id, "arguments": arguments},
                raise_on_error=False,
            )
            assert result.is_error
        assert not request.is_http_request()
        assert request._pinned_instance.get() is None

    asyncio.run(run())
    assert events == ([] if kind in {"design", "automation"} else ["exchange"])
    assert not sdk_calls


@pytest.mark.parametrize(
    "bad_id", [".", "..", " .. ", "x/y", "x\\y", "%2e%2e", "%252f", "a\n", " "]
)
@pytest.mark.parametrize(
    "operation_id, arguments",
    [
        ("agent-management.get_platform", {}),
        ("deployer.get_infrastructure", {"deployer_type": "project"}),
    ],
)
def test_path_escape_rejected_before_sdk_execution(
    monkeypatch, bad_id, operation_id, arguments
):
    kind = (
        "agent-management"
        if operation_id.startswith("agent-management.")
        else "deployer"
    )
    events = _http_setup(monkeypatch, kind)

    async def run():
        async with Client(mcp) as client:
            result = await client.call_tool(
                "run_read_operation",
                {
                    "operation_id": operation_id,
                    "arguments": {
                        **arguments,
                        (
                            "platform_id"
                            if operation_id.startswith("agent-management.")
                            else "infra_id"
                        ): bad_id,
                    },
                },
                raise_on_error=False,
            )
            assert result.is_error

    asyncio.run(run())
    assert events == ["exchange"]


def test_agent_management_settings_preserve_hidden_fields_and_revision(
    selected, monkeypatch
):
    owner_thread = threading.get_ident()
    raw = {
        "fetchedRevision": "revision-from-read",
        "apiKey": SECRET,
        "untouched": 7,
        "value": 9,
    }
    saved = []

    def save(**kwargs):
        assert threading.get_ident() != owner_thread
        saved.append(raw.copy())
        return settings

    settings = SimpleNamespace(get_raw=lambda: raw, save=save)
    sdk = SimpleNamespace(get_settings=lambda: settings)
    monkeypatch.setattr(
        agent_management,
        "get_dss_client",
        lambda: SimpleNamespace(get_agent_management_client=lambda: sdk),
    )
    result = asyncio.run(
        _call(
            "run_write_operation",
            operation_id="agent-management.update_settings",
            arguments={
                "changes": {"value": 0, "nullable": None},
                "expected_revision": "revision-from-read",
            },
            expected_instance=selected.name,
        )
    )
    assert saved == [
        {
            "fetchedRevision": "revision-from-read",
            "apiKey": SECRET,
            "untouched": 7,
            "value": 0,
            "nullable": None,
        }
    ]
    assert SECRET not in json.dumps(result)


def test_sdk_conflict_is_sanitized_and_not_retried(selected, monkeypatch):
    calls = []

    def conflict(*args, **kwargs):
        calls.append(args)
        raise DataikuException(SECRET)

    monkeypatch.setattr(
        agent_management,
        "get_dss_client",
        lambda: SimpleNamespace(
            get_agent_management_client=lambda: SimpleNamespace(get_settings=conflict)
        ),
    )

    async def run():
        async with Client(mcp) as client:
            result = await client.call_tool(
                "run_write_operation",
                {
                    "operation_id": "agent-management.update_settings",
                    "arguments": {
                        "changes": {"value": 0},
                        "expected_revision": "stale",
                    },
                },
                raise_on_error=False,
            )
            assert result.is_error
            assert SECRET not in result.content[0].text
            assert "Re-read" in result.content[0].text

    asyncio.run(run())
    assert len(calls) == 1


@pytest.mark.parametrize("changes", [42, None, SECRET])
def test_invalid_settings_schema_does_not_echo_payload(changes):
    operation = get_operation("agent-management.update_settings")
    with pytest.raises(ValueError) as error:
        operation.validate({"changes": changes, "expected_revision": SECRET})
    assert SECRET not in str(error.value)


def test_http_pinning_survives_switch_during_exchange(monkeypatch):
    profiles = {kind: _instance(kind) for kind in ("agent-management", "govern")}
    selection = {"issuer": {"alice": "agent-management"}}
    monkeypatch.setattr(
        http, "get_instances_and_selections", lambda: (profiles, selection)
    )
    monkeypatch.setattr(
        server,
        "get_access_token",
        lambda: SimpleNamespace(
            token="mcp-token", claims={"iss": "issuer", "sub": "alice"}
        ),
    )

    async def exchange(_):
        selection["issuer"]["alice"] = "govern"
        await asyncio.sleep(0)
        return "backend-token"

    monkeypatch.setattr(server, "exchange_http_token", exchange)

    def get_client():
        assert request.get_pinned_instance().name == "agent-management"
        assert request.get_http_dss_token() == "backend-token"
        return SimpleNamespace(
            get_agent_management_client=lambda: SimpleNamespace(
                get_platform=lambda _: SimpleNamespace(
                    get_status=lambda: SimpleNamespace(
                        get_raw=lambda: {"id": "platform"}
                    )
                )
            )
        )

    monkeypatch.setattr(agent_management, "get_dss_client", get_client)
    result = asyncio.run(
        _call(
            "run_read_operation",
            operation_id="agent-management.get_platform",
            arguments={"platform_id": "platform"},
        )
    )
    assert result["instance_name"] == "agent-management"
    assert not request.is_http_request()


def test_agent_management_catalog_covers_expected_actions_without_new_mcp_tools():
    ids = {
        op.operation_id.split(".", 1)[1]
        for op in OPERATIONS.values()
        if op.domain == "agent-management"
    }
    assert ids == EXPECTED_AGENT_MANAGEMENT_IDS
    tools = asyncio.run(mcp.list_tools())
    assert len(tools) == 133
    assert not any(
        tool.name == "govern" or "mira" in tool.name or "deployer" in tool.name
        for tool in tools
    )
    assert not any(
        "mira" in op.operation_id or "MIRA" in op.description
        for op in OPERATIONS.values()
    )


def test_agent_management_adapter_uses_only_public_sdk_methods():
    import ast
    import inspect

    for node in ast.walk(ast.parse(inspect.getsource(agent_management))):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            assert not node.func.attr.startswith("_perform")
            assert node.func.attr not in {"request", "urlopen"}
