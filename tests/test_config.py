import json
from pathlib import Path

import pytest

from dataiku_mcp.config import request, stdio
from dataiku_mcp.config.models import DSSInstance, StdioConfig, StdioDSSInstanceConfig


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    monkeypatch.setattr(stdio, "_settings_path", tmp_path / "stdio-config.json")
    monkeypatch.setattr(stdio, "_current_instance", None)
    for variable in (
        "DKU_DSS_URL",
        "DKU_API_KEY",
        "DKU_INSTANCE_NAME",
        "DKU_NO_CHECK_CERTIFICATE",
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
    settings_path = tmp_path / ".dataiku" / "stdio-config.json"
    settings_path.parent.mkdir()
    settings_path.write_text("{}")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(stdio, "_settings_path", None)

    assert stdio.get_settings_path() == settings_path


def test_stdio_config_rejects_non_object():
    stdio.get_settings_path().write_text("[]", encoding="utf-8")

    with pytest.raises(
        ValueError,
        match="Stdio instance configuration must be a JSON object",
    ):
        stdio.get_instances()


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


@pytest.mark.parametrize("api_key", [None, ""])
def test_stdio_environment_requires_api_key(monkeypatch, api_key):
    monkeypatch.setenv("DKU_DSS_URL", "https://dev.example.com")
    if api_key is not None:
        monkeypatch.setenv("DKU_API_KEY", api_key)

    with pytest.raises(ValueError, match="Invalid stdio environment settings"):
        stdio.get_instances()


def test_stdio_environment_uses_validated_instance(monkeypatch):
    monkeypatch.setenv("DKU_DSS_URL", "https://dev.example.com")
    monkeypatch.setenv("DKU_API_KEY", "api-key")

    instance = stdio.get_instances()["dss-env"]

    assert instance.url == "https://dev.example.com"
    assert instance.api_key == "api-key"
    assert instance.source == "environment"


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
    stdio.initialize_current_instance()

    result = stdio.delete_instance_from_config("first")

    assert result["default_instance"] == "second"
    assert stdio.get_current_instance().name == "second"


def test_deleting_only_active_instance_clears_current_instance():
    add_instance("only", set_default=True)
    stdio.initialize_current_instance()

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
    stdio.initialize_current_instance()

    stdio.delete_instance_from_config("inactive")

    assert stdio.get_current_instance().name == "active"
