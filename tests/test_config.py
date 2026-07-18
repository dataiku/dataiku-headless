"""Tests for configuration resolution, strict env parsing, dead-config removal,
and the conversation store's inter-process lock + fail-closed corruption handling.

Deterministic and hermetic: no network. The config search order is exercised by
pointing ``DKU_CONFIG_DIR``, the working directory, and ``$HOME`` at ``tmp_path``.
"""

import dataclasses
import json
import os

import pytest

from dataiku_mcp import config
from dataiku_mcp.tools.utils.conversation_store import (
    ConversationStore,
    ConversationStoreError,
)


# --------------------------------------------------------------------------- #
# Fixtures / helpers
# --------------------------------------------------------------------------- #


@pytest.fixture(autouse=True)
def _isolate(monkeypatch, tmp_path):
    """Neutralise ambient config so every test starts from a clean slate."""
    for var in (
        "DKU_CONFIG_DIR",
        "DKU_DSS_URL",
        "DKU_API_KEY",
        "DKU_INSTANCE_NAME",
        "DKU_NO_CHECK_CERTIFICATE",
        "XDG_CONFIG_HOME",
    ):
        monkeypatch.delenv(var, raising=False)
    # A dedicated HOME so the ~/.config fallback is testable and never hits the
    # real user config.
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    # Snapshot + restore the module-level registry mutated by load_dss_instances.
    saved = (dict(config._instances), config._current_instance_name)
    yield
    config._instances, config._current_instance_name = saved


def _write_config(path, instances, default_instance=""):
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"default_instance": default_instance, "dss_instances": instances}
    path.write_text(json.dumps(payload))


# --------------------------------------------------------------------------- #
# Finding 8: config-file resolution for installed packages
# --------------------------------------------------------------------------- #


def test_config_dir_env_takes_precedence(monkeypatch, tmp_path):
    cfg_dir = tmp_path / "cfgdir"
    _write_config(cfg_dir / "config.json", {"a": {"url": "http://a", "api_key": "k"}})
    monkeypatch.setenv("DKU_CONFIG_DIR", str(cfg_dir))
    # Even with a cwd config present, the env dir wins.
    monkeypatch.chdir(tmp_path)
    _write_config(
        tmp_path / ".dataiku" / "config.json", {"b": {"url": "http://b", "api_key": "k"}}
    )

    assert config.resolve_config_file() == cfg_dir / "config.json"


def test_cwd_dataiku_used_when_no_env(monkeypatch, tmp_path):
    work = tmp_path / "work"
    _write_config(
        work / ".dataiku" / "config.json", {"c": {"url": "http://c", "api_key": "k"}}
    )
    monkeypatch.chdir(work)

    assert config.resolve_config_file() == work / ".dataiku" / "config.json"


def test_home_config_fallback(monkeypatch, tmp_path):
    home = tmp_path / "home"
    _write_config(
        home / ".config" / "dataiku-headless" / "config.json",
        {"d": {"url": "http://d", "api_key": "k"}},
    )
    # cwd has no .dataiku/config.json.
    empty = tmp_path / "empty"
    empty.mkdir()
    monkeypatch.chdir(empty)

    resolved = config.resolve_config_file()
    assert resolved == home / ".config" / "dataiku-headless" / "config.json"


def test_first_existing_hit_wins(monkeypatch, tmp_path):
    # DKU_CONFIG_DIR is set but has no file -> fall through to the cwd file.
    empty_cfg_dir = tmp_path / "cfgdir"
    empty_cfg_dir.mkdir()
    monkeypatch.setenv("DKU_CONFIG_DIR", str(empty_cfg_dir))
    work = tmp_path / "work"
    _write_config(
        work / ".dataiku" / "config.json", {"e": {"url": "http://e", "api_key": "k"}}
    )
    monkeypatch.chdir(work)

    assert config.resolve_config_file() == work / ".dataiku" / "config.json"


def test_no_config_anywhere_returns_none(monkeypatch, tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    monkeypatch.chdir(empty)
    assert config.resolve_config_file() is None
    # And loading yields an empty registry rather than erroring.
    assert config._load_instances_from_config() == {
        "default_instance": "",
        "instances": {},
    }


def test_load_dss_instances_reads_resolved_config(monkeypatch, tmp_path):
    cfg_dir = tmp_path / "cfgdir"
    _write_config(
        cfg_dir / "config.json",
        {"prod": {"url": "http://prod", "api_key": "secret", "description": "Prod"}},
        default_instance="prod",
    )
    monkeypatch.setenv("DKU_CONFIG_DIR", str(cfg_dir))

    config.load_dss_instances()
    instances = config.get_instances()
    assert set(instances) == {"prod"}
    assert config.get_current_instance_name() == "prod"
    assert instances["prod"].url == "http://prod"


def test_dotenv_path_precedence(monkeypatch, tmp_path):
    cfg_dir = tmp_path / "cfgdir"
    cfg_dir.mkdir()
    (cfg_dir / ".env").write_text("X=1")
    monkeypatch.setenv("DKU_CONFIG_DIR", str(cfg_dir))
    monkeypatch.chdir(tmp_path)
    assert config.resolve_dotenv_path() == cfg_dir / ".env"


# --------------------------------------------------------------------------- #
# Finding 9: strict DKU_NO_CHECK_CERTIFICATE parsing (fail closed)
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("value", ["true", "TRUE", "1", "yes", "Yes"])
def test_no_check_certificate_truthy(value):
    assert config._parse_no_check_certificate(value) is True


@pytest.mark.parametrize("value", ["false", "False", "0", "no", "", "  "])
def test_no_check_certificate_falsy(value):
    assert config._parse_no_check_certificate(value) is False


@pytest.mark.parametrize("value", ["flase", "maybe", "2", "off", "on", "y"])
def test_no_check_certificate_rejects_garbage(value):
    with pytest.raises(ValueError, match="Allowed values"):
        config._parse_no_check_certificate(value)


def test_env_instance_rejects_bad_no_check_certificate(monkeypatch):
    monkeypatch.setenv("DKU_DSS_URL", "http://x")
    monkeypatch.setenv("DKU_NO_CHECK_CERTIFICATE", "notabool")
    with pytest.raises(ValueError, match="Allowed values"):
        config._load_instance_from_env_vars()


# --------------------------------------------------------------------------- #
# Finding 10: dead default-* config fields are gone
# --------------------------------------------------------------------------- #


def test_dssinstance_has_no_dead_default_fields():
    field_names = {f.name for f in dataclasses.fields(config.DSSInstance)}
    assert field_names == {
        "name",
        "url",
        "api_key",
        "no_check_certificate",
        "source",
        "description",
    }


def test_dead_default_keys_in_config_are_ignored(monkeypatch, tmp_path):
    cfg_dir = tmp_path / "cfgdir"
    _write_config(
        cfg_dir / "config.json",
        {
            "prod": {
                "url": "http://prod",
                "api_key": "k",
                # Legacy keys that must now be silently ignored, not crash.
                "default_connection": "conn",
                "default_llm": "llm",
            }
        },
    )
    monkeypatch.setenv("DKU_CONFIG_DIR", str(cfg_dir))

    loaded = config._load_instances_from_config()
    inst = loaded["instances"]["prod"]
    assert inst.url == "http://prod"
    assert not hasattr(inst, "default_connection")
    assert not hasattr(inst, "default_llm")


def test_dead_default_env_vars_not_read(monkeypatch):
    monkeypatch.setenv("DKU_DSS_URL", "http://x")
    monkeypatch.setenv("DKU_DEFAULT_CONNECTION", "should-not-appear")
    monkeypatch.setenv("DKU_DEFAULT_LLM", "should-not-appear")
    inst = config._load_instance_from_env_vars()
    assert not hasattr(inst, "default_connection")
    assert not hasattr(inst, "default_llm")


# --------------------------------------------------------------------------- #
# Finding 6: conversation store inter-process lock + fail-closed corruption
# --------------------------------------------------------------------------- #


def test_missing_store_is_empty(tmp_path):
    store = ConversationStore(tmp_path / "conversations.json")
    assert store.all() == {}
    assert store.read("nope") is None


def test_upsert_creates_lock_sidecar_and_persists(tmp_path):
    path = tmp_path / "conversations.json"
    store = ConversationStore(path)
    store.upsert("c1", {"project_key": "PROJ", "pending_confirmation_id": None})
    assert store.read("c1") == {"project_key": "PROJ", "pending_confirmation_id": None}
    # The inter-process flock sidecar exists next to the store.
    assert (tmp_path / "conversations.json.lock").exists()


def test_corrupt_json_fails_closed_and_quarantines(tmp_path):
    path = tmp_path / "conversations.json"
    path.write_text("{not valid json")
    store = ConversationStore(path)

    with pytest.raises(ConversationStoreError) as excinfo:
        store.all()

    # The corrupt file was moved aside (not silently overwritten)...
    backups = list(tmp_path.glob("conversations.json.corrupt-*"))
    assert len(backups) == 1
    assert str(backups[0]) in str(excinfo.value)
    assert not path.exists()


def test_non_object_json_fails_closed(tmp_path):
    path = tmp_path / "conversations.json"
    path.write_text("[1, 2, 3]")
    store = ConversationStore(path)
    with pytest.raises(ConversationStoreError):
        store.read("x")
    assert list(tmp_path.glob("conversations.json.corrupt-*"))


def test_store_recovers_after_quarantine(tmp_path):
    path = tmp_path / "conversations.json"
    path.write_text("garbage{")
    store = ConversationStore(path)
    with pytest.raises(ConversationStoreError):
        store.all()
    # After the bad file is quarantined, a fresh write starts a clean store.
    store.upsert("c1", {"project_key": "PROJ"})
    assert store.read("c1") == {"project_key": "PROJ"}


def test_record_outcome_and_mark_in_flight(tmp_path):
    path = tmp_path / "conversations.json"
    store = ConversationStore(path)
    store.upsert("c1", {"project_key": "PROJ", "pending_confirmation_id": None})

    store.mark_in_flight("c1")
    assert store.read("c1")["last_result_status"] == "in_flight"

    store.record_outcome("c1", "needs_confirmation", "cid-7")
    rec = store.read("c1")
    assert rec["last_result_status"] == "needs_confirmation"
    assert rec["pending_confirmation_id"] == "cid-7"

    # No-op for an unknown conversation (never injects an orphan record).
    store.mark_in_flight("ghost")
    store.record_outcome("ghost", "completed", None)
    assert store.read("ghost") is None


def test_store_file_permissions_are_0600(tmp_path):
    import stat

    path = tmp_path / "conversations.json"
    store = ConversationStore(path)
    store.upsert("c1", {"project_key": "PROJ"})
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600


# --------------------------------------------------------------------------- #
# Wave-2 Finding 7: config-file no_check_certificate is strictly parsed
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "value,expected",
    [(True, True), (False, False), ("true", True), ("false", False), ("yes", True)],
)
def test_config_no_check_certificate_strict(monkeypatch, tmp_path, value, expected):
    cfg_dir = tmp_path / "cfgdir"
    _write_config(
        cfg_dir / "config.json",
        {"i": {"url": "http://i", "api_key": "k", "no_check_certificate": value}},
    )
    monkeypatch.setenv("DKU_CONFIG_DIR", str(cfg_dir))

    loaded = config._load_instances_from_config()
    assert loaded["instances"]["i"].no_check_certificate is expected


@pytest.mark.parametrize("value", ["garbage", "flase", 2, [], "maybe"])
def test_config_no_check_certificate_rejects_garbage(monkeypatch, tmp_path, value):
    cfg_dir = tmp_path / "cfgdir"
    _write_config(
        cfg_dir / "config.json",
        {"badinst": {"url": "http://i", "api_key": "k", "no_check_certificate": value}},
    )
    monkeypatch.setenv("DKU_CONFIG_DIR", str(cfg_dir))

    with pytest.raises(ValueError, match="no_check_certificate"):
        config._load_instances_from_config()


def test_config_no_check_certificate_missing_defaults_false(monkeypatch, tmp_path):
    cfg_dir = tmp_path / "cfgdir"
    _write_config(cfg_dir / "config.json", {"i": {"url": "http://i", "api_key": "k"}})
    monkeypatch.setenv("DKU_CONFIG_DIR", str(cfg_dir))

    loaded = config._load_instances_from_config()
    assert loaded["instances"]["i"].no_check_certificate is False


# --------------------------------------------------------------------------- #
# Wave-2 Finding 8: $XDG_CONFIG_HOME is honored for the home-tier candidate
# --------------------------------------------------------------------------- #


def test_xdg_config_home_honored_for_config(monkeypatch, tmp_path):
    xdg = tmp_path / "xdg"
    _write_config(
        xdg / "dataiku-headless" / "config.json",
        {"x": {"url": "http://x", "api_key": "k"}},
    )
    monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg))
    empty = tmp_path / "empty"
    empty.mkdir()
    monkeypatch.chdir(empty)

    assert config.resolve_config_file() == xdg / "dataiku-headless" / "config.json"


def test_xdg_config_home_honored_for_dotenv(monkeypatch, tmp_path):
    xdg = tmp_path / "xdg"
    (xdg / "dataiku-headless").mkdir(parents=True)
    (xdg / "dataiku-headless" / ".env").write_text("X=1")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg))
    empty = tmp_path / "empty"
    empty.mkdir()
    monkeypatch.chdir(empty)

    assert config.resolve_dotenv_path() == xdg / "dataiku-headless" / ".env"


def test_xdg_default_is_home_dot_config(monkeypatch, tmp_path):
    # With XDG_CONFIG_HOME unset, the home-tier default remains ~/.config.
    home = tmp_path / "home"
    _write_config(
        home / ".config" / "dataiku-headless" / "config.json",
        {"d": {"url": "http://d", "api_key": "k"}},
    )
    monkeypatch.setenv("HOME", str(home))
    empty = tmp_path / "empty"
    empty.mkdir()
    monkeypatch.chdir(empty)

    assert config.resolve_config_file() == home / ".config" / "dataiku-headless" / "config.json"


# --------------------------------------------------------------------------- #
# Wave-2 Finding 6: the store lock is bounded (times out, never hangs)
# --------------------------------------------------------------------------- #


def test_store_lock_times_out_when_held(tmp_path, monkeypatch):
    import fcntl

    monkeypatch.setattr(
        "dataiku_mcp.tools.utils.conversation_store.STORE_LOCK_TIMEOUT_SECONDS", 0.3
    )
    path = tmp_path / "conversations.json"
    store = ConversationStore(path)
    store.upsert("c1", {"project_key": "PROJ"})  # creates the .lock sidecar

    lock_path = tmp_path / "conversations.json.lock"
    holder = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0o600)
    fcntl.flock(holder, fcntl.LOCK_EX)  # a "wedged peer" holds the flock
    try:
        with pytest.raises(ConversationStoreError, match="Timed out"):
            store.read("c1")
    finally:
        fcntl.flock(holder, fcntl.LOCK_UN)
        os.close(holder)

    # Once released, the store works again.
    assert store.read("c1") == {"project_key": "PROJ"}


# --------------------------------------------------------------------------- #
# Wave-2 Finding 9: quarantine is unique per corruption and honest on failure
# --------------------------------------------------------------------------- #


def test_quarantine_unique_across_same_second(tmp_path):
    path = tmp_path / "conversations.json"
    store = ConversationStore(path)

    path.write_text("{bad-1")
    with pytest.raises(ConversationStoreError):
        store.all()
    path.write_text("{bad-2")
    with pytest.raises(ConversationStoreError):
        store.all()

    # Two corruptions in the same second do not overwrite each other.
    backups = list(tmp_path.glob("conversations.json.corrupt-*"))
    assert len(backups) == 2


def test_quarantine_failure_reports_not_moved(tmp_path, monkeypatch):
    path = tmp_path / "conversations.json"
    path.write_text("{bad json")
    store = ConversationStore(path)

    def _boom(*_a, **_k):
        raise OSError("cannot move")

    monkeypatch.setattr(
        "dataiku_mcp.tools.utils.conversation_store.os.replace", _boom
    )

    with pytest.raises(ConversationStoreError, match="could NOT be quarantined"):
        store.all()
    # The corrupt file is still in place — never falsely reported as moved.
    assert path.exists()
