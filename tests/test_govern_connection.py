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


from dataclasses import replace
from types import SimpleNamespace

import pytest

from dataiku_mcp import auth, setup_server
from dataiku_mcp.config import request
from tests.test_instance_policy import _instance

SECRET = "do-not-return-this-secret"


@pytest.mark.parametrize("field", ["api_key", "api_ticket"])
@pytest.mark.parametrize("verification", [True, False, "/private/certificate.pem"])
def test_govern_client_preserves_pinned_auth_and_certificate(
    monkeypatch, field, verification
):
    instance = replace(
        _instance("govern"),
        api_key=SECRET if field == "api_key" else None,
        api_ticket=SECRET if field == "api_ticket" else None,
        no_check_certificate=verification is False,
        encrypted_rpc_cert_path=verification if isinstance(verification, str) else None,
    )
    monkeypatch.setattr(request, "get_pinned_instance", lambda: instance)
    monkeypatch.setattr(request, "is_http_request", lambda: False)
    captured = {}
    fake = SimpleNamespace(_session=SimpleNamespace(verify=None))

    def create(url, **kwargs):
        captured.update(url=url, **kwargs)
        return fake

    monkeypatch.setattr(auth.dataikuapi, "GovernClient", create)
    assert auth.get_govern_client() is fake
    assert fake._session.verify == verification
    assert captured["api_key" if field == "api_key" else "internal_ticket"] == SECRET
    assert captured["extra_headers"]["X-DKU-Client-Application"] == "dataiku-headless"


def test_govern_client_rejects_http(monkeypatch):
    monkeypatch.setattr(request, "get_pinned_instance", lambda: _instance("govern"))
    monkeypatch.setattr(request, "is_http_request", lambda: True)
    with pytest.raises(ValueError, match="stdio"):
        auth.get_govern_client()


def test_govern_client_rejects_wrong_profile(monkeypatch):
    monkeypatch.setattr(request, "get_pinned_instance", lambda: _instance("design"))
    with pytest.raises(ValueError, match="govern"):
        auth.get_govern_client()


def test_govern_setup_tests_the_correct_client_and_invalidates_type_change(monkeypatch):
    captured = []

    def create(url, key):
        captured.append("govern")
        return SimpleNamespace(
            _session=SimpleNamespace(verify=None), get_auth_info=lambda: {}
        )

    monkeypatch.setattr(setup_server.dataikuapi, "GovernClient", create)
    monkeypatch.setattr(
        setup_server.dataikuapi,
        "DSSClient",
        lambda *a, **k: pytest.fail("Wrong client"),
    )
    values = {
        "url": "https://govern.example",
        "api_key": "placeholder",
        "no_check_certificate": False,
        "instance_type": "govern",
    }
    setup_server._test_connection(values)
    assert captured == ["govern"]
    assert setup_server._connection_settings(
        values
    ) != setup_server._connection_settings({**values, "instance_type": "design"})
