# Copyright 2026 Dataiku
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


def _post_setup_form(url: str, form: dict[str, str]) -> tuple[int, str]:
    request = Request(url, data=urlencode(form).encode(), method="POST")
    try:
        with urlopen(request) as response:
            return response.status, response.read().decode()
    except HTTPError as error:
        return error.code, error.read().decode()


def test_setup_server_requires_a_successful_test_before_saving(monkeypatch):
    session = setup_server.start_setup_server(open_browser=False)
    form = {
        "name": "sandbox",
        "url": "https://example.com",
        "api_key": "secret",
        "description": "",
        "action": "save",
    }
    monkeypatch.setattr(
        setup_server.config,
        "add_instance_to_config",
        lambda **values: pytest.fail(f"Unexpected save: {values}"),
    )
    try:
        status, page = _post_setup_form(session.url, form)
    finally:
        session.close()

    assert status == 400
    assert "Test the connection successfully before saving." in page


def test_setup_server_invalidates_a_test_when_connection_settings_change(monkeypatch):
    session = setup_server.start_setup_server(open_browser=False)
    form = {
        "name": "sandbox",
        "url": "https://example.com",
        "api_key": "secret",
        "description": "",
    }
    monkeypatch.setattr(setup_server, "_test_connection", lambda values: None)
    try:
        status, page = _post_setup_form(session.url, {**form, "action": "test"})
        changed_status, changed_page = _post_setup_form(
            session.url,
            {**form, "api_key": "other-secret", "action": "save"},
        )
    finally:
        session.close()

    assert status == 200
    assert "You can now save this instance." in page
    assert changed_status == 400
    assert (
        "Test again after changing the URL, API key, or certificate setting."
        in changed_page
    )
