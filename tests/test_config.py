import pytest

from dataiku_mcp.config import request, stdio


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
