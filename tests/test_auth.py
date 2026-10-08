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

import ssl
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace

import pytest
import requests

from dataiku_mcp import auth
from dataiku_mcp.config import request, stdio
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
        instance_type="design",
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
    assert captured == {
        "url": instance.url,
        "extra_headers": {"X-DKU-Client-Application": "dataiku-headless"},
        **expected[credential],
    }
    assert client._session.verify is not no_check_certificate


def test_client_ticket_uses_sdk_ticket_header(monkeypatch):
    instance = DSSInstance(
        name="studio",
        url="https://studio.example.com",
        no_check_certificate=False,
        source="environment",
        api_ticket="studio-ticket",
        instance_type="design",
    )
    monkeypatch.setattr(request, "get_pinned_instance", lambda: instance)
    monkeypatch.setattr(request, "is_http_request", lambda: False)

    # SDK construction is local: no HTTP request is made.
    client = auth.get_dss_client()

    assert client.api_key is None
    assert client._session.auth is None
    assert client._session.headers["X-DKU-APITicket"] == "studio-ticket"


@pytest.mark.parametrize("disabled", [False, True])
def test_client_reuses_certificate_path(monkeypatch, localhost_certificate, disabled):
    pem, _, _ = localhost_certificate
    path = stdio._write_encrypted_rpc_certificate(pem)
    instance = DSSInstance(
        name="studio",
        url="https://localhost",
        source="environment",
        api_ticket="ticket",
        no_check_certificate=disabled,
        encrypted_rpc_cert_path=path,
        instance_type="design",
    )
    monkeypatch.setattr(request, "get_pinned_instance", lambda: instance)
    monkeypatch.setattr(request, "is_http_request", lambda: False)
    for _ in range(2):
        client = auth.get_dss_client()
        assert client._session.verify == (False if disabled else path)
        client._session.close()


@pytest.mark.parametrize("mode", ["trusted", "untrusted", "wrong_hostname"])
def test_client_verifies_local_https(monkeypatch, localhost_certificate, mode):
    pem, cert_path, key_path = localhost_certificate

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            assert self.headers["X-DKU-APITicket"] == "test-ticket"
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"verified")

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(str(cert_path), str(key_path))
    server.socket = context.wrap_socket(server.socket, server_side=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        hostname = "127.0.0.1" if mode == "wrong_hostname" else "localhost"
        instance = DSSInstance(
            name="studio",
            url=f"https://{hostname}:{server.server_port}",
            source="code-studio-environment",
            instance_type="design",
            no_check_certificate=False,
            api_ticket="test-ticket",
            encrypted_rpc_cert_path=(
                None
                if mode == "untrusted"
                else stdio._write_encrypted_rpc_certificate(pem)
            ),
        )
        monkeypatch.setattr(request, "get_pinned_instance", lambda: instance)
        monkeypatch.setattr(request, "is_http_request", lambda: False)
        client = auth.get_dss_client()
        # Keep the test independent of workstation proxies and CA overrides.
        client._session.trust_env = False
        with client._session:
            if mode == "trusted":
                response = client._session.get(instance.url, timeout=3)
                assert response.status_code == 200
                assert response.content == b"verified"
            else:
                with pytest.raises(requests.exceptions.SSLError):
                    client._session.get(instance.url, timeout=3)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


@pytest.mark.parametrize("no_check_certificate", [False, True])
@pytest.mark.parametrize("credential", ["api_key", "api_ticket"])
def test_govern_client_uses_active_govern_instance(
    monkeypatch, credential, no_check_certificate
):
    instance = DSSInstance(
        name="govern",
        url="https://govern.example.com",
        api_key="api-key" if credential == "api_key" else None,
        api_ticket="api-ticket" if credential == "api_ticket" else None,
        no_check_certificate=no_check_certificate,
        source="config",
        instance_type="govern",
    )
    monkeypatch.setattr(request, "get_pinned_instance", lambda: instance)
    monkeypatch.setattr(request, "is_http_request", lambda: False)
    captured = {}
    client = SimpleNamespace(_session=SimpleNamespace(verify=True))

    def create_client(url, **kwargs):
        captured.update(url=url, **kwargs)
        return client

    monkeypatch.setattr(auth.dataikuapi, "GovernClient", create_client)

    assert auth.get_govern_client() is client
    assert captured == {
        "url": instance.url,
        "api_key": instance.api_key,
        "internal_ticket": instance.api_ticket,
        "extra_headers": {"X-DKU-Client-Application": "dataiku-headless"},
    }
    assert client._session.verify is not no_check_certificate


@pytest.mark.parametrize(
    "instance_type", ["design", "automation", "deployer", "agent-management"]
)
def test_govern_client_rejects_other_instance_types(monkeypatch, instance_type):
    instance = DSSInstance(
        name="dev",
        url="https://dev.example.com",
        api_key="api-key",
        no_check_certificate=False,
        source="config",
        instance_type=instance_type,
    )
    monkeypatch.setattr(request, "get_pinned_instance", lambda: instance)
    monkeypatch.setattr(request, "is_http_request", lambda: False)

    with pytest.raises(ValueError, match="switch_instance"):
        auth.get_govern_client()


def test_govern_client_is_stdio_only(monkeypatch):
    monkeypatch.setattr(request, "is_http_request", lambda: True)

    with pytest.raises(ValueError, match="local stdio mode"):
        auth.get_govern_client()
