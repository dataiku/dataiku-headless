"""Configuration resolution and runtime-isolation regression tests."""

from __future__ import annotations

import asyncio
import contextvars
import dataclasses
import json

import pytest

from dataiku_mcp import config
from dataiku_mcp.tools import instances
from dataiku_mcp.tools.utils.async_executor import run_blocking


@pytest.fixture(autouse=True)
def isolate_config(monkeypatch, tmp_path):
    """Keep tests independent from the developer's real DSS configuration."""
    for variable in (
        "DKU_CONFIG_DIR",
        "DKU_DSS_URL",
        "DKU_API_KEY",
        "DKU_INSTANCE_NAME",
        "DKU_NO_CHECK_CERTIFICATE",
        "DKU_DEFAULT_CONNECTION",
        "DKU_DEFAULT_FOLDER_CONNECTION",
        "DKU_DEFAULT_LLM",
        "DKU_DEFAULT_EMBEDDING_LLM",
        "XDG_CONFIG_HOME",
    ):
        monkeypatch.delenv(variable, raising=False)

    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))

    with config._registry_lock:
        saved_instances = dict(config._instances)
        saved_current = config._current_instance_name
    yield
    with config._registry_lock:
        config._instances = saved_instances
        config._current_instance_name = saved_current


def write_config(path, instances, default_instance=""):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {"default_instance": default_instance, "dss_instances": instances}
        ),
        encoding="utf-8",
    )


def test_config_dir_takes_precedence(monkeypatch, tmp_path):
    configured = tmp_path / "configured"
    write_config(
        configured / "config.json",
        {"chosen": {"url": "https://chosen", "api_key": "secret"}},
    )
    write_config(
        tmp_path / ".dataiku" / "config.json",
        {"cwd": {"url": "https://cwd", "api_key": "secret"}},
    )
    monkeypatch.setenv("DKU_CONFIG_DIR", str(configured))
    monkeypatch.chdir(tmp_path)

    assert config.resolve_config_file() == configured / "config.json"


def test_missing_config_dir_falls_through_to_cwd(monkeypatch, tmp_path):
    configured = tmp_path / "configured"
    configured.mkdir()
    local = tmp_path / ".dataiku" / "config.json"
    write_config(local, {"cwd": {"url": "https://cwd", "api_key": "secret"}})
    monkeypatch.setenv("DKU_CONFIG_DIR", str(configured))
    monkeypatch.chdir(tmp_path)

    assert config.resolve_config_file() == local


def test_xdg_config_home_is_honored(monkeypatch, tmp_path):
    xdg_home = tmp_path / "xdg"
    candidate = xdg_home / "dataiku-headless" / "config.json"
    write_config(
        candidate,
        {"xdg": {"url": "https://xdg", "api_key": "secret"}},
    )
    empty_cwd = tmp_path / "empty"
    empty_cwd.mkdir()
    monkeypatch.chdir(empty_cwd)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg_home))

    assert config.resolve_config_file() == candidate


def test_home_dot_config_is_the_xdg_default(monkeypatch, tmp_path):
    candidate = (
        tmp_path / "home" / ".config" / "dataiku-headless" / "config.json"
    )
    write_config(
        candidate,
        {"home": {"url": "https://home", "api_key": "secret"}},
    )
    empty_cwd = tmp_path / "empty"
    empty_cwd.mkdir()
    monkeypatch.chdir(empty_cwd)

    assert config.resolve_config_file() == candidate


def test_dotenv_uses_the_same_precedence(monkeypatch, tmp_path):
    configured = tmp_path / "configured"
    configured.mkdir()
    dotenv = configured / ".env"
    dotenv.write_text("DKU_DSS_URL=https://example", encoding="utf-8")
    monkeypatch.setenv("DKU_CONFIG_DIR", str(configured))

    assert config.resolve_dotenv_path() == dotenv


@pytest.mark.parametrize("value", ["true", "TRUE", "1", "yes", " Yes "])
def test_tls_opt_out_accepts_explicit_true_tokens(value):
    assert config._parse_no_check_certificate(value) is True


@pytest.mark.parametrize("value", ["false", "False", "0", "no", "", "  "])
def test_tls_opt_out_accepts_explicit_false_tokens(value):
    assert config._parse_no_check_certificate(value) is False


@pytest.mark.parametrize("value", ["flase", "maybe", "2", "on", "off"])
def test_tls_opt_out_rejects_ambiguous_values(value):
    with pytest.raises(ValueError, match="Allowed values"):
        config._parse_no_check_certificate(value)


@pytest.mark.parametrize(
    ("value", "expected"),
    [(True, True), (False, False), ("true", True), ("false", False), (None, False)],
)
def test_config_file_tls_values_are_strict(value, expected):
    assert (
        config._coerce_no_check_certificate(value, instance_name="prod")
        is expected
    )


@pytest.mark.parametrize("value", [2, [], {}, "flase"])
def test_config_file_tls_rejects_invalid_types(value):
    with pytest.raises(ValueError, match="instance 'prod'"):
        config._coerce_no_check_certificate(value, instance_name="prod")


def test_dead_default_fields_are_removed():
    assert {field.name for field in dataclasses.fields(config.DSSInstance)} == {
        "name",
        "url",
        "api_key",
        "no_check_certificate",
        "source",
        "description",
    }


def test_legacy_default_keys_are_ignored(monkeypatch, tmp_path):
    configured = tmp_path / "configured"
    write_config(
        configured / "config.json",
        {
            "prod": {
                "url": "https://prod",
                "api_key": "secret",
                "default_connection": "unused",
                "default_folder_connection": "unused",
                "default_llm": "unused",
                "default_embedding_llm": "unused",
            }
        },
    )
    monkeypatch.setenv("DKU_CONFIG_DIR", str(configured))

    loaded = config._load_instances_from_config()["instances"]["prod"]
    assert not hasattr(loaded, "default_connection")
    assert not hasattr(loaded, "default_llm")


def test_registry_reads_are_snapshots():
    instance = config.DSSInstance(
        name="one",
        url="https://one",
        api_key="secret",
        no_check_certificate=False,
        source="test",
    )
    with config._registry_lock:
        config._instances = {"one": instance}
        config._current_instance_name = "one"

    snapshot = config.get_instances()
    snapshot.clear()

    assert set(config.get_instances()) == {"one"}
    assert config.get_current_instance() is instance


def test_client_callers_can_hold_an_immutable_instance_snapshot():
    one = config.DSSInstance(
        name="one",
        url="https://one",
        api_key="one-key",
        no_check_certificate=False,
        source="test",
    )
    two = dataclasses.replace(one, name="two", url="https://two", api_key="two-key")
    with config._registry_lock:
        config._instances = {"one": one, "two": two}
        config._current_instance_name = "one"

    captured = config.get_current_instance()
    config.switch_instance("two")

    assert captured is one
    assert captured.url == "https://one"
    assert config.get_current_instance() is two


def test_run_blocking_propagates_request_context():
    marker = contextvars.ContextVar("marker", default="missing")

    async def exercise():
        marker.set("request-value")
        return await run_blocking(marker.get)

    assert asyncio.run(exercise()) == "request-value"


def test_get_current_instance_exposes_only_public_identity(monkeypatch):
    current = config.DSSInstance(
        name="prod",
        url="https://prod",
        api_key="super-secret",
        no_check_certificate=True,
        source="/private/home/.config/dataiku-headless/config.json",
        description="Production",
    )
    monkeypatch.setattr(config, "get_current_instance", lambda: current)

    payload = json.loads(asyncio.run(instances.get_current_instance(None)))

    assert payload == {
        "name": "prod",
        "url": "https://prod",
        "description": "Production",
    }
