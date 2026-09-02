"""Unit tests for recipe inspection and container execution overrides."""

import asyncio
import json

import pytest

from dataiku_mcp.tools import recipes

from tests.utils.fakes import FakeContext, FakeDSSClient


class _FakeRecipeSettings:
    def __init__(
        self,
        recipe_type: str,
        params: dict | None = None,
        payload: dict | None = None,
    ):
        self.recipe_type = recipe_type
        self.params = params or {}
        self.payload = payload
        self.save_calls = 0

    def get_recipe_raw_definition(self) -> dict:
        return {"type": self.recipe_type}

    def get_recipe_params(self) -> dict:
        return self.params

    def get_json_payload(self) -> dict:
        return self.payload or {}

    def save(self) -> None:
        self.save_calls += 1


class _FakeRecipe:
    def __init__(self, settings: _FakeRecipeSettings):
        self.settings = settings
        self.get_settings_calls = 0

    def get_settings(self) -> _FakeRecipeSettings:
        self.get_settings_calls += 1
        return self.settings


class _FakeProject:
    def __init__(self, recipe: _FakeRecipe):
        self.recipe = recipe

    def get_recipe(self, recipe_name: str) -> _FakeRecipe:
        assert recipe_name == "recipe"
        return self.recipe


def _install_recipe(monkeypatch, settings: _FakeRecipeSettings) -> _FakeRecipe:
    recipe = _FakeRecipe(settings)
    project = _FakeProject(recipe)
    monkeypatch.setattr(
        recipes, "get_dss_client", lambda: FakeDSSClient({"PROJ": project})
    )
    return recipe


def _set_container(container_mode: str, container_config: str | None = None) -> dict:
    return json.loads(
        asyncio.run(
            recipes.set_recipe_container_exec_config(
                "PROJ",
                "recipe",
                container_mode,
                FakeContext(),
                container_config,
            )
        )
    )


def test_set_explicit_container_on_code_recipe(monkeypatch):
    settings = _FakeRecipeSettings(
        "python", params={"containerSelection": {"containerMode": "INHERIT"}}
    )
    recipe = _install_recipe(monkeypatch, settings)

    result = _set_container("EXPLICIT_CONTAINER", "compute-gpu")

    assert result == {
        "project_key": "PROJ",
        "recipe_name": "recipe",
        "recipe_type": "python",
        "container_selection": {
            "containerMode": "EXPLICIT_CONTAINER",
            "containerConf": "compute-gpu",
        },
    }
    assert settings.save_calls == 1
    assert recipe.get_settings_calls == 2


def test_disable_container_in_params_engine_settings(monkeypatch):
    settings = _FakeRecipeSettings(
        "shaker",
        params={
            "engineParams": {
                "maxThreads": 8,
                "containerSelection": {
                    "containerMode": "EXPLICIT_CONTAINER",
                    "containerConf": "compute-cpu",
                },
            }
        },
    )
    _install_recipe(monkeypatch, settings)

    result = _set_container("NONE")

    assert result["container_selection"] == {"containerMode": "NONE"}
    assert settings.params["engineParams"]["maxThreads"] == 8
    assert settings.save_calls == 1


def test_set_explicit_container_in_payload_engine_settings(monkeypatch):
    settings = _FakeRecipeSettings(
        "join",
        payload={
            "engineParams": {
                "lowerCaseSchemaIfEngineRequiresIt": True,
                "containerSelection": {"containerMode": "INHERIT"},
            }
        },
    )
    _install_recipe(monkeypatch, settings)

    result = _set_container("EXPLICIT_CONTAINER", "compute-cpu")

    assert result["container_selection"] == {
        "containerMode": "EXPLICIT_CONTAINER",
        "containerConf": "compute-cpu",
    }
    assert settings.payload["engineParams"]["lowerCaseSchemaIfEngineRequiresIt"] is True
    assert settings.save_calls == 1


@pytest.mark.parametrize(
    ("container_mode", "container_config", "message"),
    [
        ("INVALID", None, "Allowed values"),
        ("EXPLICIT_CONTAINER", None, "container_config"),
        ("EXPLICIT_CONTAINER", " ", "container_config"),
        ("INHERIT", "compute-cpu", "only valid"),
        ("NONE", "compute-cpu", "only valid"),
    ],
)
def test_reject_invalid_container_selection(
    monkeypatch, container_mode, container_config, message
):
    settings = _FakeRecipeSettings(
        "python", params={"containerSelection": {"containerMode": "INHERIT"}}
    )
    _install_recipe(monkeypatch, settings)

    with pytest.raises(ValueError, match=message):
        _set_container(container_mode, container_config)

    assert settings.save_calls == 0


def test_reject_recipe_without_container_selection(monkeypatch):
    settings = _FakeRecipeSettings("download")
    _install_recipe(monkeypatch, settings)

    with pytest.raises(ValueError, match="does not expose"):
        _set_container("NONE")

    assert settings.save_calls == 0
