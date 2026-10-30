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
from types import SimpleNamespace

import dataikuapi
import pytest
from dataikuapi.utils import DataikuException
from fastmcp import Client

from dataiku_mcp import mcp, auth
from dataiku_mcp.config import request, stdio
from dataiku_mcp.operations_catalog import OPERATIONS
from dataiku_mcp.tools import govern
from tests.test_instance_policy import _instance
from tests.test_operations import _call, _http_setup

SECRET = "do-not-return-this-secret"

EXPECTED_GOVERN_IDS = {
    "list_signoff_configurations",
    "get_signoff_recurrence",
    "list_users",
    "update_custom_pages_order",
    "get_time_series_values",
    "list_role_assignments",
    "search_artifacts",
    "get_blueprint",
    "delete_blueprint",
    "update_custom_page",
    "list_custom_pages",
    "get_signoff_details",
    "delete_signoff_configuration",
    "list_signoffs",
    "create_signoff_configuration",
    "create_signoff",
    "delete_artifact",
    "get_group",
    "delegate_signoff_approval",
    "delete_role_assignments",
    "create_blueprint",
    "get_auth_info",
    "create_time_series",
    "delete_signoff_approval",
    "update_user",
    "list_blueprint_versions",
    "list_signoff_feedbacks",
    "delete_user",
    "create_custom_page",
    "get_role_assignments",
    "list_blueprint_permissions",
    "create_role",
    "push_time_series_values",
    "update_group",
    "create_blueprint_version",
    "add_signoff_approval",
    "update_signoff_feedback",
    "get_signoff_configuration",
    "update_artifact",
    "get_custom_page_definition",
    "get_blueprint_version",
    "delegate_signoff_feedback",
    "download_uploaded_file",
    "update_role_assignments",
    "add_signoff_feedback",
    "delete_custom_page",
    "get_artifact",
    "upload_file",
    "get_user",
    "update_role",
    "get_uploaded_file",
    "update_signoff_recurrence",
    "list_roles",
    "get_signoff_feedback",
    "delete_signoff_feedback",
    "list_groups",
    "update_default_blueprint_permissions",
    "create_role_assignments",
    "delete_role",
    "get_own_user",
    "update_signoff_configuration",
    "delete_uploaded_file",
    "update_signoff_status",
    "get_signoff",
    "update_artifact_fields",
    "list_blueprints",
    "update_blueprint_permissions",
    "get_blueprint_permissions",
    "create_artifact",
    "get_role",
    "create_blueprint_permissions",
    "get_signoff_approval",
    "create_user",
    "delete_group",
    "get_instance_info",
    "delete_time_series_values",
    "update_blueprint",
    "get_default_blueprint_permissions",
    "delete_blueprint_version",
    "set_blueprint_version_status",
    "get_custom_pages_order",
    "get_custom_page",
    "create_group",
    "update_blueprint_version",
    "update_signoff_approval",
    "delete_blueprint_permissions",
}


@pytest.mark.parametrize(
    "id",
    ["govern.get_instance_info", "govern.search_artifacts", "govern.delete_artifact"],
)
def test_govern_http_denies_before_exchange(monkeypatch, id):
    events = _http_setup(monkeypatch, "govern")
    op = OPERATIONS[id]

    async def run():
        async with Client(mcp) as client:
            result = await client.call_tool(
                "run_read_operation" if op.effect == "read" else "run_write_operation",
                {"operation_id": id, "arguments": op.example},
                raise_on_error=False,
            )
            assert result.is_error
            assert "stdio" in result.content[0].text
        assert not request.is_http_request()

    asyncio.run(run())
    assert not events


def test_govern_http_current_instance_reports_unsupported_without_exchange(monkeypatch):
    events = _http_setup(monkeypatch, "govern")
    monkeypatch.setattr(
        auth.dataikuapi,
        "GovernClient",
        lambda *a, **k: pytest.fail("No Govern HTTP client"),
    )
    result = asyncio.run(_call("get_current_instance"))
    assert result["connection_status"] == "unsupported_authentication"
    assert not events


def test_all_govern_operations_are_stdio_only():
    assert all(
        op.transports == ("stdio",)
        for op in OPERATIONS.values()
        if op.domain == "govern"
    )


def test_govern_artifact_field_merge_uses_real_sdk_and_preserves_definition(
    monkeypatch,
):
    monkeypatch.setattr(stdio, "_current_instance", _instance("govern"))
    client = dataikuapi.GovernClient("https://govern.example", api_key="placeholder")
    state = {
        "id": "ar.example",
        "name": "Artifact",
        "fields": {"old": {"value": 1}},
        "workflow": {"state": "preserved"},
        "password": SECRET,
    }
    calls = []
    owner_thread = threading.get_ident()

    def perform(method, path, **kwargs):
        assert threading.get_ident() != owner_thread
        calls.append((method, path, copy.deepcopy(kwargs)))
        if method == "PUT":
            state.clear()
            state.update(copy.deepcopy(kwargs["body"]))
        return {"artifact": copy.deepcopy(state)}

    monkeypatch.setattr(client, "_perform_json", perform)
    monkeypatch.setattr(govern, "get_govern_client", lambda: client)
    result = asyncio.run(
        _call(
            "run_write_operation",
            operation_id="govern.update_artifact_fields",
            arguments={"artifact_id": "ar.example", "fields": {"new": {"value": 0}}},
        )
    )
    assert state["fields"] == {"old": {"value": 1}, "new": {"value": 0}}
    assert state["workflow"] == {"state": "preserved"}
    assert state["password"] == SECRET
    assert SECRET not in json.dumps(result)
    assert [(method, path) for method, path, _ in calls] == [
        ("GET", "/artifact/ar.example"),
        ("PUT", "/artifact/ar.example"),
        ("GET", "/artifact/ar.example"),
    ]


def test_govern_decision_defaults_do_not_send_notifications(monkeypatch):
    monkeypatch.setattr(stdio, "_current_instance", _instance("govern"))
    captured = {}
    signoff = SimpleNamespace(
        update_status=lambda *a, **k: captured.update(k),
        get_definition=lambda: SimpleNamespace(
            get_raw=lambda: {"status": "WAITING_FOR_APPROVAL"}
        ),
    )
    monkeypatch.setattr(
        govern,
        "get_govern_client",
        lambda: SimpleNamespace(
            get_artifact=lambda _: SimpleNamespace(get_signoff=lambda _: signoff)
        ),
    )
    asyncio.run(
        _call(
            "run_write_operation",
            operation_id="govern.update_signoff_status",
            arguments={
                "artifact_id": "ar.example",
                "step_id": "review",
                "status": "WAITING_FOR_APPROVAL",
            },
        )
    )
    assert captured["users_to_notify"] == []
    assert captured["reload_conf_for_reset"] is False


def test_govern_time_series_destructive_intent_and_upsert_default(monkeypatch):
    operation = OPERATIONS["govern.delete_time_series_values"]
    with pytest.raises(ValueError):
        operation.validate({"time_series_id": "ts.example"})
    operation.validate({"time_series_id": "ts.example", "delete_all": True})
    operation.validate({"time_series_id": "ts.example", "min_timestamp": 10})
    with pytest.raises(ValueError):
        operation.validate(
            {"time_series_id": "ts.example", "min_timestamp": 10, "max_timestamp": 5}
        )
    monkeypatch.setattr(stdio, "_current_instance", _instance("govern"))
    captured = {}
    series = SimpleNamespace(
        push_values=lambda values, **kwargs: captured.update(kwargs)
    )
    monkeypatch.setattr(
        govern,
        "get_govern_client",
        lambda: SimpleNamespace(get_time_series=lambda _: series),
    )
    asyncio.run(
        _call(
            "run_write_operation",
            operation_id="govern.push_time_series_values",
            arguments={
                "time_series_id": "ts.example",
                "datapoints": [{"timestamp": 1, "value": 2}],
            },
        )
    )
    assert captured["upsert"] is False


def test_search_pages_all_operations_without_increasing_tool_catalog(monkeypatch):
    monkeypatch.setattr(stdio, "_current_instance", _instance("govern"))
    first = asyncio.run(_call("search_operations", domain="govern", limit=50))
    second = asyncio.run(
        _call(
            "search_operations",
            domain="govern",
            limit=50,
            offset=first["next_offset"],
        )
    )
    assert first["total"] == 86
    assert second["next_offset"] is None
    assert (
        len(
            {
                item["operation_id"]
                for item in first["operations"] + second["operations"]
            }
        )
        == 86
    )


def test_govern_sdk_failure_is_sanitized_without_retry(monkeypatch):
    monkeypatch.setattr(stdio, "_current_instance", _instance("govern"))
    calls = []

    def fail():
        calls.append(1)
        raise DataikuException(SECRET)

    monkeypatch.setattr(
        govern, "get_govern_client", lambda: SimpleNamespace(get_instance_info=fail)
    )

    async def run():
        async with Client(mcp) as client:
            result = await client.call_tool(
                "run_read_operation",
                {"operation_id": "govern.get_instance_info", "arguments": {}},
                raise_on_error=False,
            )
            assert result.is_error
            assert SECRET not in result.content[0].text

    asyncio.run(run())
    assert len(calls) == 1


def test_govern_catalog_covers_expected_actions_without_new_mcp_tools():
    ids = {
        op.operation_id.split(".", 1)[1]
        for op in OPERATIONS.values()
        if op.domain == "govern"
    }
    assert ids == EXPECTED_GOVERN_IDS
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


def test_govern_adapter_uses_only_public_sdk_methods():
    import ast
    import inspect

    for node in ast.walk(ast.parse(inspect.getsource(govern))):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            assert not node.func.attr.startswith("_perform")
            assert node.func.attr not in {"request", "urlopen"}
