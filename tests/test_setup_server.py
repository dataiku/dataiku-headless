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

import json

from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pytest
from requests.exceptions import SSLError

from dataiku_mcp import setup_server
from dataiku_mcp.config import stdio
from dataiku_mcp.config.models import DSSInstance, StdioDSSInstanceConfig
from dataiku_mcp.setup_server import _test_connection, _validate_form

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


def test_setup_requires_an_explicit_type():
    form = _form("https://example.com")
    form.pop("instance_type")
    with pytest.raises(ValueError, match="Instance type"):
        _validate_form(form)


@pytest.mark.parametrize("instance_type", ["", "unsupported", "DESIGN", " design"])
def test_setup_rejects_invalid_instance_types(instance_type):
    with pytest.raises(ValueError, match="Instance type must be one of"):
        _validate_form(
            {**_form("https://example.com"), "instance_type": [instance_type]}
        )


@pytest.fixture
def manager(tmp_path, monkeypatch):
    monkeypatch.setattr(stdio, "_settings_path", tmp_path / "profiles.json")
    monkeypatch.setattr(stdio, "_environment_instances", [])
    monkeypatch.setattr(stdio, "_current_instance", None)
    monkeypatch.setattr(stdio, "_config", stdio._load_config())
    monkeypatch.setattr(setup_server, "_test_connection", lambda values: None)
    session = setup_server.start_setup_server(open_browser=False)
    yield session
    session.close()


def post(session, **form):
    request = Request(session.url, data=urlencode(form).encode(), method="POST")
    try:
        with urlopen(request) as response:
            return response.status, json.loads(response.read())
    except HTTPError as error:
        return error.code, json.loads(error.read())


def candidate(**changes):
    return {
        "name": "sandbox",
        "url": "https://example.com",
        "api_key": "secret",
        "description": "",
        "instance_type": "design",
        **changes,
    }


def save(session, **form):
    status, result = post(session, action="test", **form)
    assert status == 200, result
    return post(session, action="save", validation_id=result["validation_id"], **form)


def record(session, name):
    with urlopen(session.url) as response:
        page = response.read().decode()
    import re

    state = json.loads(
        re.search(r'type="application/json">(.*?)</script>', page, re.S).group(1)
    )
    return next(c for c in state["connections"] if c["name"] == name)


def test_manager_requires_successful_test_and_rejects_changed_credentials(manager):
    form = candidate()
    assert post(manager, action="save", **form)[0] == 400
    _, tested = post(manager, action="test", **form)
    assert (
        post(
            manager,
            action="save",
            validation_id=tested["validation_id"],
            **candidate(api_key="changed"),
        )[0]
        == 400
    )
    assert not stdio.get_settings_path().exists()


def test_failed_retest_revokes_validation(manager, monkeypatch):
    form = candidate()
    _, result = post(manager, action="test", **form)

    def fail(values):
        raise ValueError("Could not connect.")

    monkeypatch.setattr(setup_server, "_test_connection", fail)
    assert post(manager, action="test", **form)[0] == 400
    assert (
        post(manager, action="save", validation_id=result["validation_id"], **form)[0]
        == 400
    )
    assert not stdio.get_settings_path().exists()


@pytest.mark.parametrize("credential", ["api_key", "api_ticket"])
def test_edit_preserves_hidden_credential_and_rename_identity(manager, credential):
    instance = StdioDSSInstanceConfig(
        url="https://old.example.com",
        instance_type="design",
        **{credential: "never-expose-this"},
    )
    stdio.save_instance_profile(
        "old",
        instance,
        original_name=None,
        expected_instance=None,
        set_default=True,
        activate=True,
    )
    row = record(manager, "old")
    form = candidate(
        original_name="old",
        revision=row["revision"],
        name="new",
        api_key="",
        set_default="on",
    )
    assert save(manager, **form)[0] == 200
    config = stdio.get_profile_config()
    assert list(config.dss_instances) == ["new"]
    assert getattr(config.dss_instances["new"], credential) == "never-expose-this"
    assert config.default_instance == "new"
    assert stdio.get_current_instance().name == "new"
    with urlopen(manager.url) as response:
        page = response.read().decode()
    assert "never-expose-this" not in page
    assert '"api_key"' not in page
    assert '"api_ticket"' not in page


def test_existing_ticket_can_be_replaced_with_key(manager):
    instance = StdioDSSInstanceConfig(
        url="https://old.example.com", instance_type="design", api_ticket="ticket"
    )
    stdio.save_instance_profile(
        "old",
        instance,
        original_name=None,
        expected_instance=None,
        set_default=False,
        activate=False,
    )
    row = record(manager, "old")
    assert (
        save(
            manager,
            **candidate(
                original_name="old",
                revision=row["revision"],
                name="old",
                api_key="new-key",
            ),
        )[0]
        == 200
    )
    instance = stdio.get_profile_config().dss_instances["old"]
    assert instance.api_key == "new-key"
    assert instance.api_ticket is None


def test_duplicate_name_is_not_an_implicit_edit(manager):
    assert save(manager, **candidate())[0] == 200
    original = stdio.get_settings_path().read_bytes()
    assert post(manager, action="test", **candidate(api_key="overwrite"))[0] == 400
    assert stdio.get_settings_path().read_bytes() == original


def test_stale_editor_and_stale_delete_are_rejected(manager):
    assert save(manager, **candidate(activate="on"))[0] == 200
    row = record(manager, "sandbox")
    path = stdio.get_settings_path()
    config = json.loads(path.read_text())
    config["dss_instances"]["sandbox"].update(
        url="https://updated.example.com", api_key="other"
    )
    path.write_text(json.dumps(config))
    form = candidate(original_name="sandbox", revision=row["revision"], api_key="")
    assert post(manager, action="test", **form)[0] == 400
    assert (
        post(manager, action="delete", name="sandbox", revision=row["revision"])[0]
        == 400
    )
    assert stdio.get_instances()["sandbox"].api_key == "other"
    assert stdio.get_current_instance().url == "https://updated.example.com"


def test_delete_does_not_activate_a_profile_hidden_by_environment(manager, monkeypatch):
    assert save(manager, **candidate(name="shadowed"))[0] == 200
    assert save(manager, **candidate(activate="on", set_default="on"))[0] == 200
    monkeypatch.setattr(
        stdio,
        "_environment_instances",
        [
            DSSInstance(
                name="shadowed",
                url="https://environment.example.com",
                api_key="environment-key",
                instance_type="design",
                no_check_certificate=False,
                source="environment",
            )
        ],
    )
    row = record(manager, "sandbox")
    status, result = post(
        manager, action="delete", name="sandbox", revision=row["revision"]
    )
    assert status == 200
    assert result["state"]["active"] is None
    assert result["state"]["default"] is None
    assert result["state"]["connections"][0]["source"] == "environment"
    assert stdio.get_current_instance() is None


def test_profile_changed_after_test_cannot_be_saved(manager):
    assert save(manager, **candidate())[0] == 200
    row = record(manager, "sandbox")
    form = candidate(original_name="sandbox", revision=row["revision"], api_key="")
    _, tested = post(manager, action="test", **form)
    stdio.add_instance_to_config(
        "sandbox", "https://updated.example.com", "other", instance_type="design"
    )
    assert (
        post(manager, action="save", validation_id=tested["validation_id"], **form)[0]
        == 400
    )


def test_switch_default_and_delete_have_explicit_separate_effects(manager):
    status, result = save(
        manager,
        **candidate(activate="on", set_default="on", instance_type="automation"),
    )
    assert status == 200
    assert result["state"]["connections"][0]["instance_type"] == "automation"
    assert not manager.completed.is_set()
    assert stdio.get_settings_path().stat().st_mode & 0o777 == 0o600
    assert save(manager, **candidate(name="other"))[0] == 200
    assert stdio.get_current_instance().name == "sandbox"
    assert post(manager, action="default", name="other")[0] == 200
    assert stdio.get_current_instance().name == "sandbox"
    assert post(manager, action="switch", name="other")[0] == 200
    row = record(manager, "other")
    assert (
        post(manager, action="delete", name="other", revision=row["revision"])[0] == 400
    )
    status, result = post(
        manager,
        action="delete",
        name="other",
        revision=row["revision"],
        replacement="sandbox",
    )
    assert status == 200
    assert result["state"]["active"] == "sandbox"
    assert result["state"]["default"] == "sandbox"
    row = record(manager, "sandbox")
    status, result = post(
        manager, action="delete", name="sandbox", revision=row["revision"]
    )
    assert status == 200
    assert result["state"]["connections"] == []
    assert result["state"]["active"] is None
    assert result["state"]["default"] is None


def test_environment_connections_are_read_only_but_switchable(manager, monkeypatch):
    env = DSSInstance(
        name="env",
        url="https://env.example.com",
        api_ticket="private",
        instance_type="design",
        no_check_certificate=False,
        source="code-studio-environment",
    )
    monkeypatch.setattr(stdio, "_environment_instances", [env])
    assert post(manager, action="switch", name="env")[0] == 200
    assert stdio.get_current_instance() is env
    assert post(manager, action="test", **candidate(name="env"))[0] == 400
    assert post(manager, action="default", name="env")[0] == 400
    assert post(manager, action="delete", name="env")[0] == 400
    assert post(manager, action="test", **candidate(original_name="env"))[0] == 400
    assert not stdio.get_settings_path().exists()


def test_done_closes_manager_with_compact_result(manager):
    assert save(manager, **candidate(activate="on"))[0] == 200
    assert post(manager, action="done")[0] == 200
    assert manager.completed.is_set()
    assert manager.result == {"active_instance": "sandbox", "connection_count": 1}
    manager.thread.join(timeout=2)
    from urllib.error import URLError

    with pytest.raises(URLError):
        urlopen(manager.url, timeout=1)


def test_expired_session_cannot_write_after_test(manager):
    _, tested = post(manager, action="test", **candidate())
    manager.expired = True
    assert (
        post(
            manager, action="save", validation_id=tested["validation_id"], **candidate()
        )[0]
        == 400
    )
    assert not stdio.get_settings_path().exists()


def test_failed_write_preserves_active_config_and_disk(manager, monkeypatch):
    assert save(manager, **candidate(activate="on", set_default="on"))[0] == 200
    original = stdio.get_settings_path().read_bytes()
    row = record(manager, "sandbox")

    def fail(*args):
        raise OSError("sensitive filesystem detail")

    monkeypatch.setattr(stdio, "_save_config", fail)
    status, result = save(
        manager,
        **candidate(original_name="sandbox", revision=row["revision"], name="new"),
    )
    assert status == 500
    assert "sensitive" not in str(result)
    assert stdio.get_settings_path().read_bytes() == original
    assert stdio.get_current_instance().name == "sandbox"


def test_setup_rejects_wrong_host_origin_path_and_oversized_body(manager):
    for url, headers, body, expected in [
        (manager.url + "/wrong", {}, b"action=done", 404),
        (manager.url, {"Host": "example.com"}, b"action=done", 404),
        (manager.url, {"Origin": "https://attacker.example"}, b"action=done", 403),
        (manager.url, {}, b"x" * (setup_server.MAX_REQUEST_BYTES + 1), 400),
        (manager.url, {}, b"action=done&action=save", 400),
    ]:
        with pytest.raises(HTTPError) as error:
            urlopen(Request(url, data=body, headers=headers, method="POST"))
        assert error.value.code == expected
    assert not manager.completed.is_set()


def test_get_is_no_store_and_uses_nonce_csp(manager):
    with urlopen(manager.url) as response:
        assert response.headers["Cache-Control"] == "no-store"
        assert "script-src 'nonce-" in response.headers["Content-Security-Policy"]
        assert response.headers["Referrer-Policy"] == "no-referrer"


@pytest.mark.parametrize(
    "error",
    [
        RuntimeError("Connection refused"),
        SSLError("[SSL: CERTIFICATE_VERIFY_FAILED] certificate has expired"),
    ],
)
def test_connection_errors_are_returned_to_the_form(manager, monkeypatch, error):
    class BrokenClient:
        def __init__(self, *args, **kwargs):
            raise error

    monkeypatch.setattr(setup_server, "_test_connection", _test_connection)
    monkeypatch.setattr(setup_server.dataikuapi, "DSSClient", BrokenClient)
    status, result = post(manager, action="test", **candidate())
    assert status == 400
    assert result == {"error": f"Could not connect: {error}"}
    assert manager.validated_connection is None


def test_manager_refuses_to_read_or_write_a_different_profile_file(manager, tmp_path):
    stdio.set_settings_path(tmp_path / "other.json")
    with pytest.raises(HTTPError) as error:
        urlopen(manager.url)
    assert error.value.code == 410
    assert post(manager, action="default", name="sandbox")[0] == 400


def test_expiry_releases_socket_and_clears_validation(manager):
    from urllib.error import URLError

    assert post(manager, action="test", **candidate())[0] == 200
    manager.timer.function()
    assert manager.expired
    assert manager.completed.is_set()
    assert manager.validated_connection is None
    assert manager.result is None
    with pytest.raises(URLError):
        urlopen(manager.url, timeout=1)


def test_expiry_during_authentication_cannot_authorize_a_save(manager, monkeypatch):
    def expire(values):
        manager.expired = True

    monkeypatch.setattr(setup_server, "_test_connection", expire)
    assert post(manager, action="test", **candidate())[0] == 400
    assert manager.validated_connection is None
    assert not stdio.get_settings_path().exists()


@pytest.mark.parametrize("credential", ["api_key", "api_ticket"])
def test_connection_probe_uses_correct_sdk_credential_and_bounded_request(
    monkeypatch, credential
):
    from types import SimpleNamespace

    observed = {}
    calls = []
    closed = []

    class Client:
        def __init__(self, url, **kwargs):
            observed.update(kwargs)
            self._session = SimpleNamespace(
                request=lambda *a, **kw: calls.append(kw),
                close=lambda: closed.append(True),
            )

        def get_auth_info(self):
            self._session.request("GET", "/auth/info")

    monkeypatch.setattr(setup_server.dataikuapi, "DSSClient", Client)
    setup_server._test_connection(
        {
            "url": "https://example.com",
            "instance_type": "design",
            "api_key": None,
            "api_ticket": None,
            credential: "credential",
            "no_check_certificate": False,
        }
    )
    assert (
        observed["api_key" if credential == "api_key" else "internal_ticket"]
        == "credential"
    )
    assert calls == [{"timeout": 15}]
    assert closed == [True]


@pytest.mark.parametrize("instance_type", ["agent-management", "govern", "deployer"])
@pytest.mark.parametrize("attempt_test", [False, True])
def test_unsupported_profile_can_be_saved_without_test(
    manager, monkeypatch, instance_type, attempt_test
):
    def unexpected_probe(*args, **kwargs):
        pytest.fail("Unsupported profiles must not contact DSS")

    monkeypatch.setattr(setup_server, "_test_connection", _test_connection)
    monkeypatch.setattr(setup_server.dataikuapi, "DSSClient", unexpected_probe)
    form = candidate(instance_type=instance_type)
    if attempt_test:
        status, result = post(manager, action="test", **form)
        assert status == 400
        assert "unavailable" in result["error"]
        assert manager.validated_connection is None
    status, result = post(manager, action="save", **form)
    assert status == 200
    assert result["state"]["connections"][0]["instance_type"] == instance_type
    assert result["state"]["supported_instance_types"] == ["automation", "design"]


@pytest.mark.parametrize(
    "change",
    [
        {"url": "https://other.example.com"},
        {"api_key": "changed"},
        {"no_check_certificate": "on"},
        {"instance_type": "automation"},
    ],
)
def test_manager_invalidates_test_when_target_changes(manager, change):
    _, tested = post(manager, action="test", **candidate())
    assert (
        post(
            manager,
            action="save",
            validation_id=tested["validation_id"],
            **candidate(**change),
        )[0]
        == 400
    )
    assert not stdio.get_settings_path().exists()
