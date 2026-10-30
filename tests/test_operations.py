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


"""Operation discovery, schemas, execution policy and request pinning."""

import asyncio
import json
from types import SimpleNamespace

import pytest
from fastmcp import Client
from dataikuapi.dss.apideployer import DSSAPIDeployer
from dataikuapi.dss.projectdeployer import DSSProjectDeployer

from dataiku_mcp import mcp, server
from dataiku_mcp.config import http, request, stdio
from dataiku_mcp.operations_catalog import OPERATIONS
from dataiku_mcp.operation_registry import get_operation
from dataiku_mcp.tools import deployer
from tests.test_instance_policy import _instance
from tests.test_deployer import Backend


async def _call(name, **arguments):
    async with Client(mcp) as client:
        result = await client.call_tool(name, arguments)
        return json.loads(result.content[0].text)


@pytest.mark.parametrize(
    "tool, arguments",
    [
        ("search_operations", {}),
        ("describe_operation", {"operation_id": "deployer.list_stages"}),
        (
            "run_read_operation",
            {"operation_id": "deployer.list_stages", "arguments": {}},
        ),
        (
            "run_write_operation",
            {
                "operation_id": "deployer.start_update",
                "arguments": {
                    "deployer_type": "project",
                    "deployment_id": "deployment",
                },
            },
        ),
    ],
)
def test_all_v2_tools_require_selected_instance(monkeypatch, tool, arguments):
    monkeypatch.setattr(stdio, "_current_instance", None)
    monkeypatch.setattr(stdio, "get_instances", lambda: {})
    monkeypatch.setattr(
        server,
        "exchange_http_token",
        lambda *_: pytest.fail("No exchange without a selected profile"),
    )

    async def run():
        async with Client(mcp) as client:
            result = await client.call_tool(tool, arguments, raise_on_error=False)
            assert result.is_error
            assert "No Dataiku instances are configured" in result.content[0].text
        assert request._pinned_instance.get() is None

    asyncio.run(run())


def _http_setup(monkeypatch, kind="deployer"):
    profiles = {kind: _instance(kind)}
    monkeypatch.setattr(
        http,
        "get_instances_and_selections",
        lambda: (profiles, {"issuer": {"alice": kind}}),
    )
    monkeypatch.setattr(
        server,
        "get_access_token",
        lambda: SimpleNamespace(
            token="mcp-token", claims={"iss": "issuer", "sub": "alice"}
        ),
    )
    events = []

    async def exchange(_):
        events.append("exchange")
        return "backend-token"

    monkeypatch.setattr(server, "exchange_http_token", exchange)
    return events


def test_deployer_registry_uses_existing_sdk_handler(monkeypatch):
    backend = Backend("project")
    monkeypatch.setattr(stdio, "_current_instance", _instance("deployer"))
    monkeypatch.setattr(
        deployer,
        "get_dss_client",
        lambda: SimpleNamespace(
            get_projectdeployer=lambda: DSSProjectDeployer(backend),
            get_apideployer=lambda: DSSAPIDeployer(backend),
        ),
    )
    result = asyncio.run(
        _call(
            "run_write_operation",
            operation_id="deployer.start_update",
            arguments={"deployer_type": "project", "deployment_id": "deployment"},
        )
    )
    assert result["result"]["future_id"] == "future"
    assert len(backend.calls) == 1


@pytest.mark.parametrize("kind", ["design", "automation"])
@pytest.mark.parametrize(
    "tool, arguments",
    [
        ("search_operations", {}),
        ("describe_operation", {"operation_id": "deployer.list_stages"}),
        (
            "run_read_operation",
            {
                "operation_id": "deployer.list_stages",
                "arguments": {"deployer_type": "project"},
            },
        ),
        (
            "run_write_operation",
            {
                "operation_id": "deployer.start_update",
                "arguments": {
                    "deployer_type": "project",
                    "deployment_id": "deployment",
                },
            },
        ),
    ],
)
def test_v2_tools_reject_design_and_automation_before_exchange(
    monkeypatch, kind, tool, arguments
):
    events = _http_setup(monkeypatch, kind)

    async def run():
        async with Client(mcp) as client:
            result = await client.call_tool(tool, arguments, raise_on_error=False)
            assert result.is_error
            assert f"instance type '{kind}'" in result.content[0].text
        assert not request.is_http_request()
        assert request._pinned_instance.get() is None

    asyncio.run(run())
    assert not events


def test_each_v2_operation_requires_its_matching_instance_type():
    from dataiku_mcp.operation_registry import require_operation

    for operation in OPERATIONS.values():
        assert operation.allowed_instance_types == (operation.domain,)
        for kind in ("design", "automation", "agent-management", "deployer", "govern"):
            if kind == operation.domain:
                assert (
                    require_operation(operation.operation_id, operation.effect, kind)
                    is operation
                )
            else:
                with pytest.raises(ValueError, match="unavailable for instance type"):
                    require_operation(operation.operation_id, operation.effect, kind)


def test_all_schemas_accept_examples_and_are_closed():
    assert sum(op.domain == "deployer" for op in OPERATIONS.values()) == 13
    for operation in OPERATIONS.values():
        operation.validate(operation.example)
        description = operation.describe()
        assert description["input_schema"]["additionalProperties"] is False
        assert description["server_support"] == "unknown"
        assert description["requirements"]
        assert description["response_contract"]
        assert description["effect"] in {"read", "write"}


def test_search_filters_paginates_and_preserves_tool_catalog(monkeypatch):
    monkeypatch.setattr(stdio, "_current_instance", _instance("deployer"))

    async def run():
        before = {tool.name for tool in await mcp.list_tools()}
        results = []
        offset = 0
        while offset is not None:
            page = await _call(
                "search_operations", domain="deployer", limit=5, offset=offset
            )
            assert page["total"] == 13
            results.extend(op["operation_id"] for op in page["operations"])
            offset = page["next_offset"]
        assert len(set(results)) == 13
        writes = await _call("search_operations", query="deployment", effect="write")
        assert "deployer.update_deployment" in {
            op["operation_id"] for op in writes["operations"]
        }
        detail = await _call("describe_operation", operation_id="deployer.start_update")
        assert detail["allowed_on_selected_instance"] is True
        assert {tool.name for tool in await mcp.list_tools()} == before

    asyncio.run(run())


@pytest.mark.parametrize(
    "tool,operation_id,arguments",
    [
        ("run_read_operation", "deployer.start_update", {}),
        ("run_write_operation", "deployer.list_stages", {"deployer_type": "project"}),
        ("run_read_operation", "not-in-catalog", {}),
        (
            "run_read_operation",
            "deployer.list_stages",
            {"deployer_type": "project", "path": "/admin"},
        ),
        ("run_read_operation", "deployer.list_stages", 42),
    ],
)
def test_invalid_operation_rejected_before_sdk_execution(
    monkeypatch, tool, operation_id, arguments
):
    events = _http_setup(monkeypatch)
    monkeypatch.setattr(
        deployer,
        "get_dss_client",
        lambda: pytest.fail("Invalid operations must not reach SDK"),
    )

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
    assert events == ["exchange"]


@pytest.mark.parametrize(
    "bad_id", [".", "..", " .. ", "x/y", "x\\y", "%2e%2e", "%252f", "a\n", " "]
)
def test_path_escape_rejected_before_sdk_execution(monkeypatch, bad_id):
    _http_setup(monkeypatch)
    monkeypatch.setattr(
        deployer,
        "get_dss_client",
        lambda: pytest.fail("Invalid identifier reached SDK"),
    )

    async def run():
        async with Client(mcp) as client:
            result = await client.call_tool(
                "run_read_operation",
                {
                    "operation_id": "deployer.get_infrastructure",
                    "arguments": {"deployer_type": "project", "infra_id": bad_id},
                },
                raise_on_error=False,
            )
            assert result.is_error

    asyncio.run(run())


def test_expected_instance_rejects_stale_selection_before_sdk_execution(monkeypatch):
    _http_setup(monkeypatch)
    monkeypatch.setattr(
        deployer, "get_dss_client", lambda: pytest.fail("Stale selection reached SDK")
    )

    async def run():
        async with Client(mcp) as client:
            result = await client.call_tool(
                "run_read_operation",
                {
                    "operation_id": "deployer.list_stages",
                    "arguments": {"deployer_type": "project"},
                    "expected_instance": "other",
                },
                raise_on_error=False,
            )
            assert result.is_error
            assert "Selected instance changed" in result.content[0].text

    asyncio.run(run())


def test_http_pinning_survives_switch_during_exchange(monkeypatch):
    profiles = {kind: _instance(kind) for kind in ("deployer", "design")}
    selection = {"issuer": {"alice": "deployer"}}
    _http_setup(monkeypatch)
    monkeypatch.setattr(
        http, "get_instances_and_selections", lambda: (profiles, selection)
    )

    async def exchange(_):
        selection["issuer"]["alice"] = "design"
        await asyncio.sleep(0)
        return "backend-token"

    monkeypatch.setattr(server, "exchange_http_token", exchange)

    def get_client():
        assert request.get_pinned_instance().name == "deployer"
        assert request.get_http_dss_token() == "backend-token"
        return SimpleNamespace(
            get_projectdeployer=lambda: SimpleNamespace(list_stages=lambda: [])
        )

    monkeypatch.setattr(deployer, "get_dss_client", get_client)
    result = asyncio.run(
        _call(
            "run_read_operation",
            operation_id="deployer.list_stages",
            arguments={"deployer_type": "project"},
        )
    )
    assert result["instance_name"] == "deployer"
    assert not request.is_http_request()


def test_redacted_credentials_cannot_be_written_back():
    operation = get_operation("deployer.update_deployment")
    with pytest.raises(ValueError, match="redacted result placeholders"):
        operation.validate(
            {"deployer_type": "project", "deployment_id": "__DATAIKU_REDACTED__"}
        )
