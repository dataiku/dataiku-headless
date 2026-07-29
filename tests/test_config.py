import pytest

from dataiku_mcp import config


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "_config_file", tmp_path / "config.json")
    monkeypatch.setattr(config, "_current_instance", None)
    for variable in (
        "DKU_DSS_URL",
        "DKU_API_KEY",
        "DKU_INSTANCE_NAME",
        "DKU_NO_CHECK_CERTIFICATE",
    ):
        monkeypatch.delenv(variable, raising=False)


def add_instance(name: str, *, set_default: bool = False) -> None:
    config.add_instance_to_config(
        name,
        f"https://{name}.example.com",
        f"{name}-api-key",
        set_default=set_default,
    )


def test_deleting_active_default_switches_to_next_instance():
    add_instance("first", set_default=True)
    add_instance("second")
    config.initialize_current_instance()

    result = config.delete_instance_from_config("first")

    assert result["default_instance"] == "second"
    assert config.get_current_instance().name == "second"


def test_deleting_only_active_instance_clears_current_instance():
    add_instance("only", set_default=True)
    config.initialize_current_instance()

    config.delete_instance_from_config("only")

    with pytest.raises(config.NoConfiguredInstancesError):
        config.get_current_instance()


def test_deleting_inactive_instance_preserves_current_instance():
    add_instance("active", set_default=True)
    add_instance("inactive")
    config.initialize_current_instance()

    config.delete_instance_from_config("inactive")

    assert config.get_current_instance().name == "active"
