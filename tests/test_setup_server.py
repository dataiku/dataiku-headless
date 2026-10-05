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

from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pytest

from dataiku_mcp import setup_server
from dataiku_mcp.setup_server import _page, _validate_form

NORMALIZED_URLS = (
    (
        "https://sandbox.se-platform.dataiku-sandbox.io",
        "https://sandbox.se-platform.dataiku-sandbox.io",
    ),
    (
        "https://sandbox.se-platform.dataiku-sandbox.io/",
        "https://sandbox.se-platform.dataiku-sandbox.io",
    ),
    (
        "https://sandbox.se-platform.dataiku-sandbox.io/home",
        "https://sandbox.se-platform.dataiku-sandbox.io",
    ),
    (
        "https://sandbox.se-platform.dataiku-sandbox.io/home/",
        "https://sandbox.se-platform.dataiku-sandbox.io",
    ),
    (
        "https://sandbox.se-platform.dataiku-sandbox.io/flow",
        "https://sandbox.se-platform.dataiku-sandbox.io",
    ),
    (
        "https://sandbox.se-platform.dataiku-sandbox.io/projects/DEMO/flow"
        "?view=all#selection",
        "https://sandbox.se-platform.dataiku-sandbox.io",
    ),
    ("http://localhost:11200/home", "http://localhost:11200"),
    ("https://[::1]:11200/home", "https://[::1]:11200"),
)

INVALID_URLS = (
    "ftp://example.com/projects",
    "https:///projects",
    "https://user@example.com",
    "https://example.com:abc/home",
    "https://example.com:/home",
    "https://example.com:0/home",
    "https://example.com:99999/home",
    "https://example.com\\home",
    "https://example.com/a path",
    "https://example.com/\x00flow",
    "https://[::1/home",
)


def _form(url: str) -> dict[str, list[str]]:
    return {
        "name": ["sandbox"],
        "url": [url],
        "api_key": ["secret"],
        "description": [""],
        "instance_type": ["design"],
    }


@pytest.mark.parametrize(
    ("submitted_url", "saved_url"),
    NORMALIZED_URLS,
)
def test_validate_form_normalizes_dataiku_page_urls(submitted_url, saved_url):
    assert _validate_form(_form(submitted_url))["url"] == saved_url


@pytest.mark.parametrize("url", INVALID_URLS)
def test_validate_form_rejects_malformed_or_unsafe_urls(url):
    with pytest.raises(ValueError):
        _validate_form(_form(url))


def test_setup_page_explains_instance_url():
    page = _page()

    assert "Enter the URL of your Dataiku instance." in page


@pytest.mark.parametrize(
    "instance_type", ["design", "automation", "deployer", "govern", "agent-management"]
)
def test_setup_form_and_page_preserve_instance_type(instance_type):
    values = _validate_form(
        {**_form("https://example.com"), "instance_type": [instance_type]}
    )
    assert values["instance_type"] == instance_type
    for page in (
        _page(values=values),
        _page(values=values, error="Connection failed"),
    ):
        assert f'<option value="{instance_type}" selected>' in page


def test_setup_requires_an_explicit_type():
    form = _form("https://example.com")
    form.pop("instance_type")
    with pytest.raises(ValueError, match="Instance type"):
        _validate_form(form)
    page = _page()
    assert '<option value="" disabled selected>Choose an instance type</option>' in page
    assert '<option value="design" selected>' not in page
    assert 'name="instance_type" required' in page


@pytest.mark.parametrize("instance_type", ["", "unsupported", "DESIGN", " design"])
def test_setup_rejects_invalid_instance_types(instance_type):
    with pytest.raises(ValueError, match="Instance type must be one of"):
        _validate_form(
            {**_form("https://example.com"), "instance_type": [instance_type]}
        )


def test_setup_server_saves_selected_instance_type(monkeypatch):
    saved = []

    def save(**values):
        saved.append(values)
        return {"name": values["name"], "instance_type": values["instance_type"]}

    monkeypatch.setattr(setup_server.stdio, "add_instance_to_config", save)
    monkeypatch.setattr(setup_server.request, "set_current_instance", lambda name: None)
    monkeypatch.setattr(setup_server, "_test_connection", lambda values: None)
    session = setup_server.start_setup_server(open_browser=False)
    form = {
        "name": "typed",
        "url": "https://example.com",
        "api_key": "secret",
        "instance_type": "automation",
    }
    try:
        status, page = _post_setup_form(session.url, {**form, "action": "test"})
        assert status == 200
        assert '<option value="automation" selected>' in page
        status, _ = _post_setup_form(session.url, {**form, "action": "save"})
        assert status == 200
        assert session.result["instance_type"] == "automation"
    finally:
        session.close()
    assert len(saved) == 1
    assert saved[0]["instance_type"] == "automation"


def _post_setup_form(url: str, form: dict[str, str]) -> tuple[int, str]:
    request = Request(url, data=urlencode(form).encode(), method="POST")
    try:
        with urlopen(request) as response:
            return response.status, response.read().decode()
    except HTTPError as error:
        return error.code, error.read().decode()


@pytest.mark.parametrize(
    "instance_type", ["design", "automation", "agent-management", "deployer"]
)
def test_setup_server_requires_a_successful_test_before_saving(
    monkeypatch, instance_type
):
    session = setup_server.start_setup_server(open_browser=False)
    form = {
        "name": "sandbox",
        "url": "https://example.com",
        "api_key": "secret",
        "description": "",
        "instance_type": instance_type,
        "action": "save",
    }
    monkeypatch.setattr(
        setup_server.stdio,
        "add_instance_to_config",
        lambda **values: pytest.fail(f"Unexpected save: {values}"),
    )
    try:
        status, page = _post_setup_form(session.url, form)
    finally:
        session.close()

    assert status == 400
    assert "Test the connection successfully before saving." in page


@pytest.mark.parametrize(
    "change",
    [
        {"api_key": "other-secret"},
        {"instance_type": "deployer"},
        {"url": "https://other.example"},
        {"no_check_certificate": "on"},
    ],
)
def test_setup_server_invalidates_a_test_when_connection_settings_change(
    monkeypatch, change
):
    session = setup_server.start_setup_server(open_browser=False)
    form = {
        "name": "sandbox",
        "url": "https://example.com",
        "api_key": "secret",
        "description": "",
        "instance_type": "design",
    }
    monkeypatch.setattr(setup_server, "_test_connection", lambda values: None)
    try:
        status, page = _post_setup_form(session.url, {**form, "action": "test"})
        changed_status, changed_page = _post_setup_form(
            session.url,
            {**form, **change, "action": "save"},
        )
    finally:
        session.close()

    assert status == 200
    assert "You can now save this instance." in page
    assert changed_status == 400
    assert (
        "Test again after changing the URL, API key, certificate setting, or instance type."
        in changed_page
    )


def test_govern_profile_can_be_saved_after_unavailable_test(monkeypatch):
    saved = []
    monkeypatch.setattr(
        setup_server.dataikuapi,
        "DSSClient",
        lambda *args: pytest.fail("Govern must not construct a DSS client"),
    )
    monkeypatch.setattr(
        setup_server.stdio,
        "add_instance_to_config",
        lambda **values: (
            saved.append(values)
            or {"name": values["name"], "instance_type": values["instance_type"]}
        ),
    )
    monkeypatch.setattr(setup_server.request, "set_current_instance", lambda name: None)
    session = setup_server.start_setup_server(open_browser=False)
    form = {
        "name": "govern",
        "url": "https://example.com",
        "api_key": "secret",
        "instance_type": "govern",
    }
    try:
        status, page = _post_setup_form(session.url, {**form, "action": "test"})
        assert status == 400
        assert "Connection testing is unavailable for Govern" in page
        assert session.validated_connection is None
        status, page = _post_setup_form(session.url, {**form, "action": "save"})
        assert status == 200
        assert "Instance saved" in page
        assert saved[0]["instance_type"] == "govern"
    finally:
        session.close()


def test_deployer_connection_test_uses_dss_client(monkeypatch):
    calls = []

    class Client:
        def __init__(self, url, key):
            from types import SimpleNamespace

            self._session = SimpleNamespace(verify=None)
            calls.append("client")

        def get_auth_info(self):
            calls.append("auth")
            assert self._session.verify is True

    monkeypatch.setattr(setup_server.dataikuapi, "DSSClient", Client)
    setup_server._test_connection(
        _validate_form({**_form("https://example.com"), "instance_type": ["deployer"]})
    )
    assert calls == ["client", "auth"]
