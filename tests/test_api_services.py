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

"""Public SDK contracts, preservation, lifecycle recovery and safe responses."""

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
from dataiku_mcp.tools import api_services
from tests.test_instance_policy import _instance

SECRET = "DO_NOT_RETURN_SERVICE_SECRET"


class Backend:
    def __init__(self):
        self.owner = threading.get_ident()
        self.calls = []
        self.services = []
        self.packages = []
        self.failure = None
        self.fail_after_write = False
        self.raw = {
            "name": "Existing",
            "authMethod": "API_KEYS",
            "authRealm": {"apiKeys": [SECRET]},
            "oauth2Config": {"clientSecret": SECRET},
            "deploymentMonitoring": [{"kept": True}],
            "endpoints": [
                {
                    "id": "predict",
                    "type": "STD_PREDICTION",
                    "modelRef": "model",
                    "useJava": True,
                },
                {"id": "keep", "type": "PY_FUNCTION", "code": "def run(): return 1"},
            ],
        }

    def check(self, method, path, kwargs):
        assert threading.get_ident() != self.owner
        self.calls.append((method, path, copy.deepcopy(kwargs)))
        if self.failure:
            raise self.failure(SECRET)

    def _perform_json(self, method, path, **kwargs):
        self.check(method, path, kwargs)
        assert method == "GET"
        if path.endswith("/settings"):
            return copy.deepcopy(self.raw)
        if path.endswith("/packages"):
            return copy.deepcopy(self.packages)
        assert path.endswith("/apiservices/")
        return copy.deepcopy(self.services)

    def _perform_empty(self, method, path, **kwargs):
        self.check(method, path, kwargs)
        if method == "PUT":
            self.raw = copy.deepcopy(kwargs["body"])
        elif path.endswith("/packages/v1"):
            self.packages.append({"id": "v1", "createdOn": 42})
        if self.fail_after_write:
            raise Timeout(SECRET)


@pytest.fixture
def backend(monkeypatch):
    backend = Backend()
    monkeypatch.setattr(stdio, "_current_instance", _instance("design"))

    def client():
        assert threading.get_ident() != backend.owner
        assert request.get_pinned_instance().name == "design"
        return SimpleNamespace(get_project=lambda key: DSSProject(backend, key))

    monkeypatch.setattr(api_services, "get_dss_client", client)
    return backend


def call(tool, **arguments):
    async def invoke():
        async with Client(mcp) as client:
            result = await client.call_tool(
                tool, {"project_key": "PROJECT", **arguments}
            )
            return json.loads(result.content[0].text)

    return asyncio.run(invoke())


def test_list_and_get_exclude_service_credentials_and_redact_nested_fields(backend):
    backend.services = [{"id": "service", **backend.raw}]
    backend.raw["endpoints"][0]["nested"] = {"password": SECRET}
    backend.raw["endpoints"][1]["testQueries"] = [
        {"q": {}, "headers": [{"key": "Authorization", "value": SECRET}]}
    ]
    backend.packages = [{"id": "v1", "createdOn": 42, "secret": SECRET}]
    listing = call("list_api_services")
    detail = call("get_api_service", service_id="service")
    assert listing["services"]["rows"][0][0] == "service"
    assert detail["auth_method"] == "API_KEYS"
    assert detail["packages"]["rows"] == [["v1", 42]]
    assert detail["endpoints"][0]["modelRef"] == "model"
    assert SECRET not in json.dumps([listing, detail])
    assert "authRealm" not in detail
    assert "oauth2Config" not in detail


def test_create_empty_service_and_conflict(backend):
    result = call("create_api_service", service_id=" service ")
    assert result["status"] == "created"
    assert result["published"] is False
    assert backend.calls[-1] == ("POST", "/projects/PROJECT/apiservices/service", {})
    backend.services = [{"id": "service"}]
    with pytest.raises(Exception, match="already exists"):
        call("create_api_service", service_id="service")
    assert backend.calls[-1][0] == "GET"


def test_update_replaces_selected_definition_adds_endpoint_and_preserves_settings(
    backend,
):
    original = copy.deepcopy(backend.raw)
    endpoints = [
        {"id": "predict", "type": "STD_FORECAST", "modelRef": "another-model"},
        {"id": "lookup", "type": "DATASETS_LOOKUP", "lookups": []},
    ]
    result = call(
        "update_api_service", service_id="service", name="New name", endpoints=endpoints
    )
    assert result["status"] == "updated"
    assert backend.raw == {
        **original,
        "name": "New name",
        "endpoints": [endpoints[0], original["endpoints"][1], endpoints[1]],
    }
    assert [c[0] for c in backend.calls] == ["GET", "PUT"]
    assert SECRET not in json.dumps(result)


@pytest.mark.parametrize(
    "arguments",
    [
        {},
        {"endpoints": []},
        {"name": " "},
        {"endpoints": [{"type": "PY_FUNCTION"}]},
        {"endpoints": [{"id": "a", "type": ""}]},
        {
            "endpoints": [
                {
                    "id": "a",
                    "type": "PY_FUNCTION",
                    "nested": {"password": "__DATAIKU_REDACTED__"},
                }
            ]
        },
        {
            "endpoints": [
                {"id": "a", "type": "PY_FUNCTION"},
                {"id": "a", "type": "SQL_QUERY"},
            ]
        },
    ],
)
def test_invalid_update_before_sdk(backend, arguments):
    with pytest.raises(Exception):
        call("update_api_service", service_id="service", **arguments)
    assert backend.calls == []


def test_package_then_publish_public_sdk_contract(backend):
    created = call(
        "create_api_service_package",
        service_id="service",
        package_id="v1",
        release_notes="Release",
    )
    assert created["published"] is False
    assert backend.calls[-1] == (
        "POST",
        "/projects/PROJECT/apiservices/service/packages/v1",
        {"params": {"releaseNotes": "Release"}},
    )
    published = call(
        "publish_api_service_package",
        service_id="service",
        package_id="v1",
        published_service_id="target",
    )
    assert published["published_service_id"] == "target"
    assert published["deployment_started"] is False
    assert backend.calls[-1] == (
        "POST",
        "/projects/PROJECT/apiservices/service/packages/v1/publish",
        {"params": {"publishedServiceId": "target"}},
    )
    default = call("publish_api_service_package", service_id="service", package_id="v1")
    assert default["published_service_id"] == "service"
    assert backend.calls[-1][2] == {"params": None}


def test_package_conflict_and_missing_publish_never_mutate(backend):
    with pytest.raises(Exception, match="must exist"):
        call("publish_api_service_package", service_id="service", package_id="v1")
    backend.packages = [{"id": "v1"}]
    with pytest.raises(Exception, match="already exists"):
        call("create_api_service_package", service_id="service", package_id="v1")
    assert all(c[0] == "GET" for c in backend.calls)


@pytest.mark.parametrize("exception", [Timeout, DataikuException])
@pytest.mark.parametrize(
    "tool,arguments",
    [
        ("list_api_services", {}),
        ("get_api_service", {"service_id": "service"}),
        ("create_api_service", {"service_id": "service"}),
        ("update_api_service", {"service_id": "service", "name": "New"}),
        ("create_api_service_package", {"service_id": "service", "package_id": "v1"}),
        ("publish_api_service_package", {"service_id": "service", "package_id": "v1"}),
    ],
)
def test_errors_are_sanitized_and_writes_offer_recovery(
    backend, tool, arguments, exception
):
    backend.failure = exception
    with pytest.raises(Exception) as error:
        call(tool, **arguments)
    assert SECRET not in str(error.value)
    if tool.startswith(("create", "update", "publish")):
        assert "before retrying" in str(error.value)


@pytest.mark.parametrize(
    "tool,arguments",
    [
        ("create_api_service", {"service_id": "service"}),
        ("update_api_service", {"service_id": "service", "name": "Saved"}),
        ("create_api_service_package", {"service_id": "service", "package_id": "v1"}),
        ("publish_api_service_package", {"service_id": "service", "package_id": "v1"}),
    ],
)
def test_uncertain_write_returns_recovery_instead_of_success(backend, tool, arguments):
    if tool.startswith("publish"):
        backend.packages = [{"id": "v1"}]
    backend.fail_after_write = True
    with pytest.raises(Exception, match="before retrying") as error:
        call(tool, **arguments)
    assert SECRET not in str(error.value)
    assert backend.calls[-1][0] in {"PUT", "POST"}
    if tool.startswith("update"):
        assert backend.raw["name"] == "Saved"
    if tool.startswith("create_api_service_package"):
        assert backend.packages == [{"id": "v1", "createdOn": 42}]


def test_receipt_and_sdk_use_pinned_instance_after_switch(backend, monkeypatch):
    get_client = api_services.get_dss_client

    def switch_then_get_client():
        stdio._current_instance = _instance("automation")
        return get_client()

    monkeypatch.setattr(api_services, "get_dss_client", switch_then_get_client)
    result = call("create_api_service", service_id="service")
    assert result["instance_name"] == "design"
    assert stdio.get_current_instance().instance_type == "automation"


@pytest.mark.parametrize(
    "tool,arguments",
    [
        ("list_api_services", {"project_key": "../bad"}),
        ("get_api_service", {"service_id": "bad/id"}),
        ("create_api_service", {"service_id": "bad%2fid"}),
        (
            "update_api_service",
            {
                "service_id": "service",
                "endpoints": [{"id": "bad/id", "type": "PY_FUNCTION"}],
            },
        ),
        ("create_api_service_package", {"service_id": "service", "package_id": ".."}),
        (
            "publish_api_service_package",
            {
                "service_id": "service",
                "package_id": "v1",
                "published_service_id": "bad?id",
            },
        ),
    ],
)
def test_invalid_identifiers_do_not_reach_sdk(backend, tool, arguments):
    with pytest.raises(Exception, match="path segment"):
        call(tool, **arguments)
    assert not backend.calls


def test_api_service_tool_metadata_matches_effects():
    async def inspect():
        for name, readonly, destructive in [
            ("list_api_services", True, False),
            ("get_api_service", True, False),
            ("create_api_service", False, False),
            ("update_api_service", False, True),
            ("create_api_service_package", False, False),
            ("publish_api_service_package", False, True),
        ]:
            tool = await mcp.get_tool(name)
            assert tool.title
            assert tool.annotations.readOnlyHint is readonly
            assert tool.annotations.destructiveHint is destructive
            assert tool.annotations.openWorldHint is False
            assert tool.meta["allowed_instance_types"] == ["design"]

    asyncio.run(inspect())


@pytest.mark.parametrize("ids", [[" predict "], ["predict", "keep"]])
def test_remove_endpoints_uses_settings_save_and_preserves_other_state(backend, ids):
    before = copy.deepcopy(backend.raw)
    backend.packages = [{"id": "v1", "createdOn": 42}]
    result = call("update_api_service", service_id="service", remove_endpoint_ids=ids)
    removed = {id.strip() for id in ids}
    assert backend.raw == {
        **before,
        "endpoints": [e for e in before["endpoints"] if e["id"] not in removed],
    }
    assert backend.packages == [{"id": "v1", "createdOn": 42}]
    assert [(method, path) for method, path, _ in backend.calls] == [
        ("GET", "/projects/PROJECT/apiservices/service/settings"),
        ("PUT", "/projects/PROJECT/apiservices/service/settings"),
    ]
    assert result["status"] == "updated"
    assert result["published"] is False
    assert SECRET not in json.dumps(result)


def test_removal_and_upsert_are_saved_together(backend):
    before = copy.deepcopy(backend.raw)
    changed = {"id": "keep", "type": "PY_FUNCTION", "code": "def run(): return 2"}
    added = {"id": "new", "type": "PY_FUNCTION", "code": "def run(): return 3"}
    call(
        "update_api_service",
        service_id="service",
        name="Renamed",
        endpoints=[changed, added],
        remove_endpoint_ids=["predict"],
    )
    assert backend.raw == {**before, "name": "Renamed", "endpoints": [changed, added]}
    assert [method for method, _, _ in backend.calls] == ["GET", "PUT"]


@pytest.mark.parametrize(
    "arguments",
    [
        {"remove_endpoint_ids": []},
        {"remove_endpoint_ids": [" "]},
        {"remove_endpoint_ids": ["bad/id"]},
        {"remove_endpoint_ids": ["predict", " predict "]},
        {
            "remove_endpoint_ids": ["predict"],
            "endpoints": [
                {"id": "predict", "type": "STD_PREDICTION", "modelRef": "model"}
            ],
        },
    ],
)
def test_invalid_removal_intent_never_reaches_sdk(backend, arguments):
    with pytest.raises(Exception):
        call("update_api_service", service_id="service", **arguments)
    assert not backend.calls


def test_missing_removal_prevents_all_changes(backend):
    before = copy.deepcopy(backend.raw)
    with pytest.raises(Exception, match="does not exist"):
        call(
            "update_api_service",
            service_id="service",
            name="Not saved",
            remove_endpoint_ids=["predict", "missing"],
        )
    assert backend.raw == before
    assert [method for method, _, _ in backend.calls] == ["GET"]


def test_uncertain_removal_does_not_claim_success(backend):
    backend.fail_after_write = True
    with pytest.raises(Exception, match="before retrying") as error:
        call(
            "update_api_service", service_id="service", remove_endpoint_ids=["predict"]
        )
    assert SECRET not in str(error.value)
    assert [e["id"] for e in backend.raw["endpoints"]] == ["keep"]
    assert [method for method, _, _ in backend.calls] == ["GET", "PUT"]


def test_update_schema_advertises_explicit_endpoint_removal():
    tool = asyncio.run(mcp.get_tool("update_api_service"))
    assert "remove_endpoint_ids" in tool.parameters["properties"]
    assert tool.annotations.destructiveHint is True
