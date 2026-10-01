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

import asyncio
import json
import logging
import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from dataiku_mcp.config import request, stdio
from dataiku_mcp.config.models import DSSInstance, StdioConfig, StdioDSSInstanceConfig
from dataiku_mcp.tools import instances as instance_tools


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    monkeypatch.setattr(
        stdio,
        "DEFAULT_SETTINGS_PATH",
        tmp_path / "home" / ".dataiku" / "stdio-config.json",
    )
    monkeypatch.setattr(stdio, "_settings_path", tmp_path / "stdio-config.json")
    monkeypatch.setattr(stdio, "_config", None)
    monkeypatch.setattr(stdio, "_current_instance", None)
    monkeypatch.setattr(stdio, "_environment_instances", [])
    for variable in (
        "DKU_DSS_URL",
        "DKU_API_KEY",
        "DKU_INSTANCE_NAME",
        "DKU_NO_CHECK_CERTIFICATE",
        "DKU_CONFIG_FILE",
        "DKU_IS_CODE_STUDIO",
        "DKU_API_TICKET",
        "DKU_SERVER_CERT",
        "DKU_BACKEND_PROTOCOL",
        "DKU_BACKEND_HOST",
        "DKU_BACKEND_PORT",
    ):
        monkeypatch.delenv(variable, raising=False)


def add_instance(name: str, *, set_default: bool = False) -> None:
    stdio.add_instance_to_config(
        name,
        f"https://{name}.example.com",
        f"{name}-api-key",
        set_default=set_default,
    )


def test_stdio_config_uses_explicit_settings_path(tmp_path):
    path = tmp_path / "custom.json"

    assert stdio.set_settings_path(path) == path
    assert stdio.get_settings_path() == path


def test_stdio_config_uses_canonical_default(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(stdio, "_settings_path", None)

    assert stdio.get_settings_path() == stdio.DEFAULT_SETTINGS_PATH


def test_stdio_config_prefers_existing_cwd_settings(tmp_path, monkeypatch):
    stdio.DEFAULT_SETTINGS_PATH.parent.mkdir(parents=True)
    stdio.DEFAULT_SETTINGS_PATH.write_text("{}")
    settings_path = tmp_path / ".dataiku" / "stdio-config.json"
    settings_path.parent.mkdir()
    settings_path.write_text("{}")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(stdio, "_settings_path", None)

    assert stdio.get_settings_path() == settings_path


def test_stdio_config_rejects_deprecated_dku_config_file(monkeypatch):
    monkeypatch.setattr(stdio, "_settings_path", None)
    monkeypatch.setenv("DKU_CONFIG_FILE", "")

    with pytest.raises(ValueError, match="DKU_CONFIG_FILE.*--settings-path"):
        stdio.set_settings_path(None)


@pytest.mark.parametrize("location", ["cwd", "home"])
@pytest.mark.parametrize(
    "contents",
    [
        json.dumps(
            {
                "default_instance": "dev",
                "dss_instances": {
                    "dev": {"url": "https://dev.example.com", "api_key": "api-key"}
                },
            }
        ),
        json.dumps({"unexpected": True}),
        "{",
    ],
    ids=["valid", "invalid-schema", "invalid-json"],
)
def test_stdio_config_ignores_legacy_settings(
    tmp_path, monkeypatch, location, contents
):
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    default_path = stdio.DEFAULT_SETTINGS_PATH
    legacy_path = (
        cwd / ".dataiku" / "config.json"
        if location == "cwd"
        else default_path.with_name("config.json")
    )
    legacy_path.parent.mkdir(parents=True)
    legacy_path.write_text(contents, encoding="utf-8")
    monkeypatch.chdir(cwd)
    monkeypatch.setattr(stdio, "_settings_path", None)

    assert stdio.get_settings_path() == default_path
    assert stdio._load_config() == StdioConfig()
    assert legacy_path.read_text(encoding="utf-8") == contents
    assert not (cwd / ".dataiku" / "stdio-config.json").exists()
    assert not default_path.exists()


def test_stdio_config_uses_canonical_when_legacy_also_exists(tmp_path, monkeypatch):
    canonical_path = tmp_path / ".dataiku" / "stdio-config.json"
    legacy_path = canonical_path.with_name("config.json")
    canonical_path.parent.mkdir()
    canonical_path.write_text("{}")
    legacy_path.write_text("{}")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(stdio, "_settings_path", None)

    assert stdio.get_settings_path() == canonical_path

    assert legacy_path.exists()


def test_stdio_config_explicit_path_leaves_legacy_settings_untouched(
    tmp_path, monkeypatch
):
    legacy_path = tmp_path / ".dataiku" / "config.json"
    legacy_path.parent.mkdir()
    legacy_path.write_text("{}")
    monkeypatch.chdir(tmp_path)
    explicit_path = tmp_path / "custom.json"

    assert stdio.set_settings_path(explicit_path) == explicit_path
    assert legacy_path.exists()
    assert not legacy_path.with_name("stdio-config.json").exists()


def test_stdio_getters_require_initialization():
    with pytest.raises(RuntimeError, match="has not been initialized"):
        stdio.get_instances()


def test_setting_stdio_path_invalidates_cached_state():
    add_instance("dev", set_default=True)
    stdio.initialize_config()

    stdio.set_settings_path(stdio.get_settings_path())

    with pytest.raises(RuntimeError, match="has not been initialized"):
        stdio.get_instances()
    assert stdio.get_current_instance() is None


def test_stdio_config_rejects_non_object():
    stdio.get_settings_path().write_text("[]", encoding="utf-8")

    with pytest.raises(
        ValueError,
        match="Stdio instance configuration must be a JSON object",
    ):
        stdio.initialize_config()


def test_stdio_config_returns_empty_model_when_file_is_missing():
    assert stdio._load_config() == StdioConfig()


def test_stdio_config_normalizes_legacy_empty_default():
    stdio.get_settings_path().write_text(
        json.dumps({"default_instance": "", "dss_instances": {}})
    )

    assert stdio._load_config().default_instance is None


def test_stdio_config_rejects_unknown_root_fields():
    stdio.get_settings_path().write_text(json.dumps({"unexpected": True}))

    with pytest.raises(ValueError, match="Extra inputs are not permitted"):
        stdio._load_config()


@pytest.mark.parametrize(
    "unknown_field",
    ["unexpected", "delegated_audience", "delegated_scope"],
)
def test_stdio_config_rejects_unknown_instance_fields(unknown_field):
    stdio.get_settings_path().write_text(
        json.dumps(
            {
                "dss_instances": {
                    "dev": {
                        "url": "https://dev.example.com",
                        unknown_field: "unexpected",
                    }
                }
            }
        )
    )

    with pytest.raises(ValueError, match="Extra inputs are not permitted"):
        stdio._load_config()


@pytest.mark.parametrize(
    "instance",
    [
        {"api_key": "api-key"},
        {"url": "", "api_key": "api-key"},
        {"url": "https://dev.example.com"},
        {"url": "https://dev.example.com", "api_key": ""},
        {
            "url": "https://dev.example.com",
            "api_key": "api-key",
            "no_check_certificate": "false",
        },
    ],
)
def test_stdio_config_rejects_invalid_instance_fields(instance):
    stdio.get_settings_path().write_text(
        json.dumps({"dss_instances": {"dev": instance}})
    )

    with pytest.raises(ValueError, match="Invalid stdio settings"):
        stdio._load_config()


def test_stdio_config_rejects_unknown_default():
    stdio.get_settings_path().write_text(
        json.dumps({"default_instance": "missing", "dss_instances": {}})
    )

    with pytest.raises(ValueError, match="Default instance 'missing'.*not found"):
        stdio._load_config()


def test_stdio_config_validation_errors_do_not_expose_api_keys():
    secret = "do-not-print-this-api-key"
    stdio.get_settings_path().write_text(
        json.dumps(
            {
                "dss_instances": {
                    "dev": {
                        "url": "https://dev.example.com",
                        "api_key": [secret],
                    }
                }
            }
        )
    )

    with pytest.raises(ValueError) as exc_info:
        stdio._load_config()

    assert secret not in str(exc_info.value)


def test_stdio_config_example_is_valid(monkeypatch):
    example_path = Path(__file__).parents[1] / ".dataiku" / "stdio-config.json.example"
    monkeypatch.setattr(stdio, "_settings_path", example_path)

    config = stdio._load_config()

    assert config.default_instance == "dev"
    assert config.dss_instances["dev"] == StdioDSSInstanceConfig(
        url="https://dev.dataiku.com",
        api_key="your-dev-api-key",
        no_check_certificate=False,
    )


@pytest.mark.parametrize("from_document", [False, True])
@pytest.mark.parametrize(
    "credentials",
    [
        {"api_key": "key"},
        {"api_ticket": "ticket"},
        {"api_key": "key", "api_ticket": None},
        {"api_key": None, "api_ticket": "ticket"},
    ],
)
def test_stdio_credentials_accept_exactly_one(credentials, from_document):
    document = {"url": "https://dev.example.com", **credentials}
    config = (
        StdioDSSInstanceConfig.model_validate(document)
        if from_document
        else StdioDSSInstanceConfig(**document)
    )
    instance = config.to_instance("dev")

    assert instance.api_key == credentials.get("api_key")
    assert instance.api_ticket == credentials.get("api_ticket")
    stdio._save_config(StdioConfig(dss_instances={"dev": config}))
    saved = json.loads(stdio.get_settings_path().read_text())["dss_instances"]["dev"]
    assert saved == {key: value for key, value in document.items() if value is not None}
    assert stdio._load_config().dss_instances["dev"] == config


@pytest.mark.parametrize("from_document", [False, True])
@pytest.mark.parametrize(
    "credentials",
    [
        {},
        {"api_key": None, "api_ticket": None},
        {"api_key": "secret-key", "api_ticket": "secret-ticket"},
        {"api_key": ""},
        {"api_ticket": ""},
        {"api_key": "secret-key", "api_ticket": ""},
        {"api_ticket": "secret-ticket", "api_key": ""},
        {"api_key": ["secret-key"]},
        {"api_ticket": ["secret-ticket"]},
        {"api_key": 123},
        {"api_ticket": 123},
    ],
)
def test_stdio_credentials_reject_invalid_combinations(credentials, from_document):
    document = {"url": "https://dev.example.com", **credentials}
    with pytest.raises(ValidationError) as exc_info:
        if from_document:
            StdioDSSInstanceConfig.model_validate(document)
        else:
            StdioDSSInstanceConfig(**document)

    assert "secret-key" not in str(exc_info.value)
    assert "secret-ticket" not in str(exc_info.value)


@pytest.mark.parametrize("credential", ["api_key", "api_ticket"])
def test_stdio_credentials_are_hidden_from_representations(credential):
    secret = "do-not-print-this-credential"
    config = StdioDSSInstanceConfig(
        url="https://dev.example.com", **{credential: secret}
    )

    assert secret not in repr(config)
    assert secret not in repr(config.to_instance("dev"))


def test_stdio_instance_config_converts_to_runtime_instance():
    config = StdioDSSInstanceConfig(
        url="https://dev.example.com",
        api_key="api-key",
        no_check_certificate=True,
        description="Development",
    )

    assert config.to_instance("dev") == DSSInstance(
        name="dev",
        url="https://dev.example.com",
        api_key="api-key",
        no_check_certificate=True,
        source="config",
        description="Development",
    )


def test_runtime_instance_repr_hides_api_key():
    instance = DSSInstance(
        name="dev",
        url="https://dev.example.com",
        api_key="do-not-print-this-api-key",
        no_check_certificate=False,
        source="config",
    )

    assert "do-not-print-this-api-key" not in repr(instance)


@pytest.mark.parametrize("api_key", [None, ""])
def test_stdio_environment_requires_api_key(monkeypatch, api_key):
    monkeypatch.setenv("DKU_DSS_URL", "https://dev.example.com")
    if api_key is not None:
        monkeypatch.setenv("DKU_API_KEY", api_key)

    with pytest.raises(ValueError, match="Invalid stdio environment settings"):
        stdio.initialize_config()


def test_stdio_environment_uses_validated_instance(monkeypatch):
    monkeypatch.setenv("DKU_DSS_URL", "https://dev.example.com")
    monkeypatch.setenv("DKU_API_KEY", "api-key")
    stdio.initialize_config()

    instance = stdio.get_instances()["dataiku-from-env"]

    assert instance.url == "https://dev.example.com"
    assert instance.api_key == "api-key"
    assert instance.source == "environment"


@pytest.fixture
def code_studio_environment(monkeypatch):
    monkeypatch.setenv("DKU_IS_CODE_STUDIO", "1")
    monkeypatch.setenv("DKU_BACKEND_PROTOCOL", "https")
    monkeypatch.setenv("DKU_BACKEND_HOST", "studio.example.com")
    monkeypatch.setenv("DKU_BACKEND_PORT", "443")
    # Both environment instances should remain available, with the explicit one first.
    monkeypatch.setenv("DKU_DSS_URL", "https://other.example.com")
    monkeypatch.setenv("DKU_API_KEY", "other-key")


@pytest.mark.parametrize("instance_name", [None, "custom-studio"])
def test_code_studio_environment_uses_ticket(
    monkeypatch, code_studio_environment, instance_name
):
    monkeypatch.setenv("DKU_API_TICKET", "studio-ticket")
    if instance_name is not None:
        monkeypatch.setenv("DKU_INSTANCE_NAME", instance_name)
    stdio.initialize_config()

    instance = stdio.get_instances()["dataiku-from-code-studio"]
    assert instance.name == "dataiku-from-code-studio"
    assert instance.url == "https://studio.example.com:443"
    assert instance.api_key is None
    assert instance.api_ticket == "studio-ticket"
    assert instance.source == "code-studio-environment"


@pytest.mark.parametrize("ticket", [None, ""])
def test_code_studio_environment_requires_ticket(
    monkeypatch, code_studio_environment, ticket
):
    if ticket is not None:
        monkeypatch.setenv("DKU_API_TICKET", ticket)

    message = (
        "Missing Code Studio environment setting: DKU_API_TICKET"
        if ticket is None
        else "Invalid stdio environment settings in Code Studio"
    )
    with pytest.raises(ValueError, match=message):
        stdio.initialize_config()


def test_stdio_getters_use_the_startup_snapshot(monkeypatch):
    add_instance("dev", set_default=True)
    stdio.initialize_config()
    monkeypatch.setenv("DKU_DSS_URL", "https://environment.example.com")
    monkeypatch.setenv("DKU_API_KEY", "environment-key")
    stdio.get_settings_path().write_text(
        json.dumps(
            {
                "default_instance": "changed",
                "dss_instances": {
                    "changed": {
                        "url": "https://changed.example.com",
                        "api_key": "changed-key",
                    }
                },
            }
        )
    )

    assert set(stdio.get_instances()) == {"dev"}
    assert stdio.get_current_instance().name == "dev"

    stdio.initialize_config()
    assert set(stdio.get_instances()) == {"changed", "dataiku-from-env"}
    assert stdio.get_current_instance().name == "dataiku-from-env"


def test_stdio_mutation_failure_leaves_cached_state_unchanged(monkeypatch):
    add_instance("dev", set_default=True)
    stdio.initialize_config()

    def fail_save(_config):
        raise OSError("write failed")

    monkeypatch.setattr(stdio, "_save_config", fail_save)

    with pytest.raises(OSError, match="write failed"):
        stdio.add_instance_to_config(
            "prod",
            "https://prod.example.com",
            "prod-key",
        )

    assert set(stdio.get_instances()) == {"dev"}
    assert stdio.get_current_instance().name == "dev"


def test_instance_tool_mutations_use_blocking_executor(monkeypatch):
    calls = []

    class Context:
        async def info(self, _message):
            pass

    async def run_in_executor(func, *args):
        calls.append((func, args))
        return func(*args)

    def select(name):
        return {"name": name}

    def delete(name):
        return {"deleted": name}

    monkeypatch.setattr(instance_tools, "run_blocking", run_in_executor)
    monkeypatch.setattr(request, "set_current_instance", select)
    monkeypatch.setattr(request, "is_http_request", lambda: False)
    monkeypatch.setattr(stdio, "delete_instance_from_config", delete)

    asyncio.run(instance_tools.switch_instance("prod", Context()))
    asyncio.run(instance_tools.delete_instance("dev", Context()))

    assert calls == [(select, ("prod",)), (delete, ("dev",))]


def test_stdio_config_save_excludes_runtime_fields():
    stdio.add_instance_to_config(
        "dev",
        "https://dev.example.com",
        "api-key",
        description="Development",
        no_check_certificate=True,
        set_default=True,
    )

    document = json.loads(stdio.get_settings_path().read_text())
    instance = document["dss_instances"]["dev"]
    assert document["default_instance"] == "dev"
    assert instance == {
        "url": "https://dev.example.com",
        "no_check_certificate": True,
        "description": "Development",
        "api_key": "api-key",
    }
    assert "name" not in instance
    assert "source" not in instance

    resolved = stdio.get_instances()["dev"]
    assert resolved.name == "dev"
    assert resolved.source == "config"
    assert resolved.api_key == "api-key"


def test_stdio_mutations_hold_settings_lock(monkeypatch):
    class RecordingLock:
        held = False
        entries = 0

        def __enter__(self):
            assert not self.held
            self.held = True
            self.entries += 1

        def __exit__(self, exc_type, exc_value, traceback):
            self.held = False

    lock = RecordingLock()
    load_config = stdio._load_config
    save_config = stdio._save_config

    def load_while_locked():
        assert lock.held
        return load_config()

    def save_while_locked(config):
        assert lock.held
        save_config(config)

    monkeypatch.setattr(stdio, "_settings_lock", lock)
    monkeypatch.setattr(stdio, "_load_config", load_while_locked)
    monkeypatch.setattr(stdio, "_save_config", save_while_locked)

    add_instance("only", set_default=True)
    stdio.delete_instance_from_config("only")

    assert lock.entries == 2


def test_deleting_active_default_switches_to_next_instance():
    add_instance("first", set_default=True)
    add_instance("second")
    stdio.initialize_config()

    result = stdio.delete_instance_from_config("first")

    assert result["default_instance"] == "second"
    assert stdio.get_current_instance().name == "second"


def test_deleting_only_active_instance_clears_current_instance():
    add_instance("only", set_default=True)
    stdio.initialize_config()

    stdio.delete_instance_from_config("only")

    assert stdio.get_current_instance() is None
    with pytest.raises(
        ValueError,
        match="No Dataiku instances are configured. Run configure_instance.",
    ):
        request.get_pinned_instance()


def test_deleting_inactive_instance_preserves_current_instance():
    add_instance("active", set_default=True)
    add_instance("inactive")
    stdio.initialize_config()

    stdio.delete_instance_from_config("inactive")

    assert stdio.get_current_instance().name == "active"


@pytest.mark.parametrize("explicit", [False, True])
def test_environment_instances_remain_switchable(
    monkeypatch, code_studio_environment, explicit
):
    monkeypatch.setenv("DKU_API_TICKET", "studio-ticket")
    monkeypatch.setenv("DKU_NO_CHECK_CERTIFICATE", "true")
    if not explicit:
        monkeypatch.delenv("DKU_DSS_URL")
    add_instance("dataiku-from-code-studio", set_default=True)
    stdio.initialize_config()

    assert [instance.name for instance in stdio._environment_instances] == (
        ["dataiku-from-env", "dataiku-from-code-studio"]
        if explicit
        else ["dataiku-from-code-studio"]
    )
    assert stdio.get_current_instance().name == (
        "dataiku-from-env" if explicit else "dataiku-from-code-studio"
    )
    assert (
        stdio.get_instances()["dataiku-from-code-studio"].api_ticket == "studio-ticket"
    )
    assert (
        stdio.get_instances()["dataiku-from-code-studio"].no_check_certificate is False
    )
    if explicit:
        assert stdio.get_instances()["dataiku-from-env"].no_check_certificate is True
    request.set_current_instance("dataiku-from-code-studio")
    assert stdio.get_current_instance().api_ticket == "studio-ticket"
    if explicit:
        request.set_current_instance("dataiku-from-env")
        assert stdio.get_current_instance().api_key == "other-key"
    monkeypatch.setenv("DKU_API_TICKET", "changed-ticket")
    assert (
        stdio.get_instances()["dataiku-from-code-studio"].api_ticket == "studio-ticket"
    )


def test_environment_instances_reject_duplicate_names(
    monkeypatch, code_studio_environment
):
    monkeypatch.setenv("DKU_API_TICKET", "studio-ticket")
    monkeypatch.setenv("DKU_INSTANCE_NAME", "dataiku-from-code-studio")
    with pytest.raises(
        ValueError, match="Duplicate environment instance name.*DKU_INSTANCE_NAME"
    ):
        stdio.initialize_config()


def test_invalid_explicit_instance_does_not_fall_back_to_code_studio(
    monkeypatch, code_studio_environment
):
    monkeypatch.setenv("DKU_API_TICKET", "studio-ticket")
    monkeypatch.delenv("DKU_API_KEY")
    with pytest.raises(ValueError, match="Invalid stdio environment settings"):
        stdio.initialize_config()


def test_environment_cache_resets_with_settings_path(monkeypatch):
    monkeypatch.setenv("DKU_DSS_URL", "https://dev.example.com")
    monkeypatch.setenv("DKU_API_KEY", "key")
    stdio.initialize_config()
    stdio.set_settings_path(stdio.get_settings_path())
    assert stdio._environment_instances == []
    assert stdio.get_current_instance() is None


def test_initial_settings_path_resolution_preserves_environment(monkeypatch, tmp_path):
    monkeypatch.setattr(stdio, "_settings_path", None)
    monkeypatch.setattr(stdio, "DEFAULT_SETTINGS_PATH", tmp_path / "settings.json")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DKU_DSS_URL", "https://dev.example.com")
    monkeypatch.setenv("DKU_API_KEY", "key")
    stdio.initialize_config()
    assert stdio.get_current_instance() == stdio.get_instances()["dataiku-from-env"]


def test_code_studio_certificate_survives_configuration_reset(
    monkeypatch, code_studio_environment, localhost_certificate
):
    pem, _, _ = localhost_certificate
    monkeypatch.setenv("DKU_API_TICKET", "studio-ticket")
    monkeypatch.setenv("DKU_SERVER_CERT", pem)
    stdio.initialize_config()
    instance = stdio.get_instances()["dataiku-from-code-studio"]
    path = Path(instance.encrypted_rpc_cert_path)
    assert path.read_text() == pem
    assert path.stat().st_mode & 0o777 == 0o600
    assert stdio.get_instances()["dataiku-from-env"].encrypted_rpc_cert_path is None
    assert str(path) not in repr(instance)
    stdio._save_config(StdioConfig())
    assert "encrypted_rpc_cert_path" not in stdio.get_settings_path().read_text()
    stdio.set_settings_path(stdio.get_settings_path())
    assert path.read_text() == pem


def test_certificate_file_is_removed_on_process_exit(localhost_certificate):
    pem, _, _ = localhost_certificate
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; from dataiku_mcp.config import stdio; "
            "print(stdio._write_encrypted_rpc_certificate(sys.stdin.read()))",
        ],
        input=pem,
        capture_output=True,
        text=True,
        check=True,
    )
    path = Path(result.stdout.strip())
    assert not path.exists()


@pytest.mark.parametrize("certificate", [None, ""])
def test_code_studio_without_certificate_uses_default_trust(
    monkeypatch, code_studio_environment, certificate
):
    monkeypatch.setenv("DKU_API_TICKET", "studio-ticket")
    if certificate is not None:
        monkeypatch.setenv("DKU_SERVER_CERT", certificate)
    stdio.initialize_config()
    assert (
        stdio.get_instances()["dataiku-from-code-studio"].encrypted_rpc_cert_path
        is None
    )


def test_code_studio_rejects_malformed_certificate(
    monkeypatch, code_studio_environment
):
    monkeypatch.setenv("DKU_API_TICKET", "studio-ticket")
    monkeypatch.setenv("DKU_SERVER_CERT", "do-not-echo-malformed-certificate")
    with pytest.raises(
        ValueError, match="Invalid Code Studio DKU_SERVER_CERT"
    ) as exc_info:
        stdio.initialize_config()
    assert "do-not-echo-malformed-certificate" not in str(exc_info.value)
