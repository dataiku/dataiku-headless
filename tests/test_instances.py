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

"""Unit tests for the current instance tool's Dataiku version reporting."""

import asyncio
import json
from dataclasses import replace

import pytest
from requests.exceptions import SSLError

from dataiku_mcp.config import request
from dataiku_mcp.config.models import DSSInstance
from dataiku_mcp.tools import instances

from tests.utils.fakes import FakeContext

API_KEY = "super-secret-key"


class _FakeInstanceInfo:
    def __init__(self, raw: dict):
        self.raw = raw


class _FakeClient:
    def __init__(self, raw: dict):
        self.raw = raw
        self.info_calls = 0

    def get_instance_info(self) -> _FakeInstanceInfo:
        self.info_calls += 1
        return _FakeInstanceInfo(self.raw)


def _instance(name: str) -> DSSInstance:
    return DSSInstance(
        name=name,
        url=f"https://{name}.example",
        api_key=API_KEY,
        no_check_certificate=False,
        source="config",
        instance_type="design",
        description=f"{name} desc",
    )


def _install(monkeypatch, instance_names: list[str], client: _FakeClient, active: str):
    configured = {name: _instance(name) for name in instance_names}
    monkeypatch.setattr(request, "get_pinned_instance", lambda: configured[active])
    monkeypatch.setattr(instances, "get_dss_client", lambda: client)


def _current(monkeypatch, client: _FakeClient) -> dict:
    _install(monkeypatch, ["primary"], client, "primary")
    return json.loads(asyncio.run(instances.get_current_instance(FakeContext())))


@pytest.mark.parametrize(
    "instance_type", ["design", "automation", "deployer", "govern", "agent-management"]
)
def test_instance_tools_report_configured_type(monkeypatch, instance_type):
    configured = replace(_instance("primary"), instance_type=instance_type)
    monkeypatch.setattr(request, "get_instances", lambda: {"primary": configured})
    monkeypatch.setattr(request, "get_pinned_instance", lambda: configured)

    def unexpected_client():
        pytest.fail("Listing and switching must not construct a DSS client")

    monkeypatch.setattr(instances, "get_dss_client", unexpected_client)
    monkeypatch.setattr(
        "dataiku_mcp.config.stdio.set_current_instance", lambda inst: None
    )
    monkeypatch.setattr(request, "is_http_request", lambda: False)
    listing = asyncio.run(instances.list_instances(FakeContext()))
    switching = asyncio.run(instances.switch_instance("primary", FakeContext()))
    table = json.loads(listing)
    assert table["columns"] == ["name", "url", "description", "active", "instance_type"]
    assert table["rows"][0][-1] == instance_type
    assert json.loads(switching)["instance_type"] == instance_type

    # API information is observational; it must not replace the configured type.
    client = _FakeClient({"dssVersion": "14.7.2", "nodeType": "AUTOMATION"})
    monkeypatch.setattr(instances, "get_dss_client", lambda: client)
    current = asyncio.run(instances.get_current_instance(FakeContext()))
    assert json.loads(current)["instance_type"] == instance_type
    unsupported = instance_type in {"govern", "deployer", "agent-management"}
    assert client.info_calls == (0 if unsupported else 1)
    assert json.loads(current)["connection_status"] == (
        "unsupported" if unsupported else "connected"
    )
    if unsupported:
        assert "dataiku_version" not in json.loads(current)
    for response in (listing, switching, current):
        assert API_KEY not in response
        assert "api_key" not in response


def test_get_current_instance_reports_the_dataiku_version(monkeypatch):
    client = _FakeClient({"dssVersion": "14.7.2", "nodeType": "DESIGN"})
    result = _current(monkeypatch, client)

    assert result["dataiku_version"] == "14.7.2"
    assert result["connection_status"] == "connected"
    assert "error" not in result
    assert client.info_calls == 1


def test_get_current_instance_omits_the_dataiku_version_without_credentials(
    monkeypatch,
):
    _install(monkeypatch, ["primary"], _FakeClient({}), "primary")

    def missing_client():
        raise ValueError("missing API key")

    monkeypatch.setattr(
        instances,
        "get_dss_client",
        missing_client,
    )

    result = json.loads(asyncio.run(instances.get_current_instance(FakeContext())))

    assert "dataiku_version" not in result
    assert result["connection_status"] == "failed"
    assert result["name"] == "primary"
    assert result["instance_type"] == "design"


@pytest.mark.parametrize(
    "error",
    [
        ConnectionError("connection failed"),
        SSLError("[SSL: CERTIFICATE_VERIFY_FAILED] certificate has expired"),
    ],
)
def test_get_current_instance_reports_failed_connection(monkeypatch, error):
    client = _FakeClient({})

    def unavailable_instance_info():
        raise error

    client.get_instance_info = unavailable_instance_info
    result = _current(monkeypatch, client)

    assert result["connection_status"] == "failed"
    assert result["error"] == str(error)
    assert "dataiku_version" not in result
    assert client.info_calls == 0


@pytest.mark.parametrize("credential", ["api_key", "api_ticket"])
@pytest.mark.parametrize("connected", [False, True])
def test_get_current_instance_never_returns_credentials(
    monkeypatch, credential, connected
):
    secret = "do-not-return-this-credential"
    instance = DSSInstance(
        name="dataiku",
        url="https://dev.example.com",
        no_check_certificate=False,
        source="code-studio-environment" if credential == "api_ticket" else "config",
        encrypted_rpc_cert_path="/private/test-certificate.pem",
        instance_type="design",
        **{credential: secret},
    )
    monkeypatch.setattr(request, "get_pinned_instance", lambda: instance)

    def get_client():
        if not connected:
            raise ConnectionError("connection failed")
        return _FakeClient({"dssVersion": "14.7.2"})

    monkeypatch.setattr(instances, "get_dss_client", get_client)
    response = asyncio.run(instances.get_current_instance(FakeContext()))
    result = json.loads(response)

    assert "api_key" not in result
    assert "api_ticket" not in result
    assert "encrypted_rpc_cert_path" not in result
    assert instance.encrypted_rpc_cert_path not in response
    assert secret not in response
    assert result["name"] == instance.name
    assert result["source"] == instance.source
    assert result["connection_status"] == ("connected" if connected else "failed")


@pytest.mark.parametrize(
    "elicitation", ["unsupported", "accept", "decline", "expire", "cancel"]
)
def test_connection_manager_tool_completion(monkeypatch, elicitation):
    import threading
    from types import SimpleNamespace

    completed = threading.Event()
    waiting = threading.Event()
    closed = []
    if elicitation != "cancel":
        completed.set()

    def wait(timeout):
        waiting.set()
        return completed.wait(timeout)

    def close():
        closed.append(True)
        completed.set()

    session = SimpleNamespace(
        url="http://127.0.0.1:1234/token",
        browser_opened=False,
        completed=SimpleNamespace(wait=wait),
        result=None
        if elicitation == "expire"
        else {"active_instance": "sandbox", "connection_count": 2},
        expired=elicitation == "expire",
        close=close,
    )
    starts = []

    def start(**kwargs):
        starts.append(kwargs)
        return session

    monkeypatch.setattr(instances, "start_setup_server", start)
    monkeypatch.setattr(request, "is_http_request", lambda: False)

    class Session:
        client_params = SimpleNamespace(
            capabilities=SimpleNamespace(
                elicitation=(
                    None if elicitation == "unsupported" else SimpleNamespace(url={})
                )
            )
        )

        async def elicit_url(self, **kwargs):
            return SimpleNamespace(
                action="decline" if elicitation == "decline" else "accept"
            )

        async def send_elicit_complete(self, *args, **kwargs):
            pass

    ctx = FakeContext()
    ctx.session = Session()
    ctx.request_id = "request"

    async def invoke():
        task = asyncio.create_task(instances.configure_instance(ctx))
        if elicitation == "cancel":
            try:
                assert await asyncio.to_thread(waiting.wait, 2)
                task.cancel()
                await task
            finally:
                # A failed cleanup assertion must not leave the test runner waiting.
                completed.set()
        return await task

    if elicitation == "cancel":
        with pytest.raises(asyncio.CancelledError):
            asyncio.run(invoke())
        assert closed == [True]
        return
    result = json.loads(asyncio.run(invoke()))
    if elicitation in {"unsupported", "decline"}:
        assert result["interaction_mode"] == "direct_local_url"
        assert result["setup_url"] == session.url
        assert len(starts) == (2 if elicitation == "decline" else 1)
    elif elicitation == "expire":
        assert result["status"] == "expired"
    else:
        assert result["status"] == "completed"
        assert result["state"]["active_instance"] == "sandbox"


@pytest.mark.parametrize("elicitation", ["unsupported", "accept", "decline"])
@pytest.mark.parametrize("cancellation", ["task", "scope"])
def test_connection_manager_cancellation_during_startup(
    monkeypatch, elicitation, cancellation
):
    import threading
    from types import SimpleNamespace

    import anyio

    started = threading.Event()
    release = threading.Event()
    closed = threading.Event()
    starts = []
    session = SimpleNamespace(close=closed.set, url="http://127.0.0.1:1234/token")

    def start(**kwargs):
        starts.append(kwargs)
        if elicitation != "decline" or len(starts) == 2:
            started.set()
            if not release.wait(5):
                raise TimeoutError("Test did not release server startup")
        return session

    class Session:
        client_params = SimpleNamespace(
            capabilities=SimpleNamespace(
                elicitation=(
                    None if elicitation == "unsupported" else SimpleNamespace(url={})
                )
            )
        )

        async def elicit_url(self, **kwargs):
            return SimpleNamespace(action="decline")

    monkeypatch.setattr(instances, "start_setup_server", start)
    monkeypatch.setattr(request, "is_http_request", lambda: False)
    ctx = FakeContext()
    ctx.session = Session()
    ctx.request_id = "request"

    async def invoke():
        scope = None

        async def configure():
            nonlocal scope
            with anyio.CancelScope() as scope:
                await instances.configure_instance(ctx)

        task = asyncio.create_task(
            configure()
            if cancellation == "scope"
            else instances.configure_instance(ctx)
        )
        try:
            assert await asyncio.to_thread(started.wait, 2)
            if cancellation == "scope":
                scope.cancel()
            else:
                task.cancel()
            # Let cancellation reach the tool while startup is still blocked.
            await asyncio.sleep(0)
            release.set()
            if cancellation == "scope":
                await task
            else:
                with pytest.raises(asyncio.CancelledError):
                    await task
            assert closed.is_set()
        finally:
            release.set()
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

    asyncio.run(invoke())
    assert len(starts) == (2 if elicitation == "decline" else 1)
