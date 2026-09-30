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

from types import SimpleNamespace

import pytest

from dataiku_mcp import auth
from dataiku_mcp.config import request
from dataiku_mcp.config.models import DSSInstance


@pytest.mark.parametrize("no_check_certificate", [False, True])
@pytest.mark.parametrize("credential", ["api_key", "api_ticket", "http"])
def test_client_uses_selected_authentication(
    monkeypatch, credential, no_check_certificate
):
    instance = DSSInstance(
        name="dev",
        url="https://dev.example.com",
        api_key="api-key" if credential == "api_key" else None,
        api_ticket="api-ticket" if credential == "api_ticket" else None,
        no_check_certificate=no_check_certificate,
        source="http" if credential == "http" else "environment",
    )
    monkeypatch.setattr(request, "get_pinned_instance", lambda: instance)
    monkeypatch.setattr(request, "is_http_request", lambda: credential == "http")

    def delegated_token():
        assert credential == "http"
        return "delegated-token"

    monkeypatch.setattr(request, "get_http_dss_token", delegated_token)
    captured = {}
    client = SimpleNamespace(_session=SimpleNamespace(verify=True))

    def create_client(url, **kwargs):
        captured.update(url=url, **kwargs)
        return client

    monkeypatch.setattr(auth.dataikuapi, "DSSClient", create_client)

    assert auth.get_dss_client() is client
    expected = {
        "api_key": {"api_key": "api-key"},
        "api_ticket": {"internal_ticket": "api-ticket"},
        "http": {"jwt_bearer_token": "delegated-token"},
    }
    assert captured == {"url": instance.url, **expected[credential]}
    assert client._session.verify is not no_check_certificate


def test_client_ticket_uses_sdk_ticket_header(monkeypatch):
    instance = DSSInstance(
        name="studio",
        url="https://studio.example.com",
        no_check_certificate=False,
        source="environment",
        api_ticket="studio-ticket",
    )
    monkeypatch.setattr(request, "get_pinned_instance", lambda: instance)
    monkeypatch.setattr(request, "is_http_request", lambda: False)

    # SDK construction is local: no HTTP request is made.
    client = auth.get_dss_client()

    assert client.api_key is None
    assert client._session.auth is None
    assert client._session.headers["X-DKU-APITicket"] == "studio-ticket"
