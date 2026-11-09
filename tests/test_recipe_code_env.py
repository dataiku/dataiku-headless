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

"""Unit tests for selecting a Python recipe's code environment."""

import asyncio
import copy
import json

import pytest
from fastmcp import Client

from dataiku_mcp import mcp
from dataiku_mcp.config import stdio
from dataiku_mcp.config.models import DSSInstance
from dataiku_mcp.tools import recipes

from tests.utils.fakes import FakeContext, FakeDSSClient

CODE = "import dataiku\nprint('unchanged')\n"
ENVS = [
    {"envName": "py-analytics", "envLang": "PYTHON"},
    {"envName": "r-only", "envLang": "R"},
]


class _FakeRecipe:
    """Server-side recipe state, handed out as detached settings copies.

    A mutation only becomes visible to a later read once ``save`` commits it,
    so the tool's post-save read-back proves the write happened.
    """

    def __init__(self, state: dict):
        self.state = state
        self.save_calls = 0
        self.raise_on_save: Exception | None = None

    def get_settings(self):
        return _FakeRecipeSettings(self, copy.deepcopy(self.state))


class _FakeRecipeSettings:
    def __init__(self, server: _FakeRecipe, state: dict):
        self.server = server
        self.state = state

    def get_recipe_raw_definition(self) -> dict:
        return self.state["recipe"]

    def get_recipe_params(self):
        return self.state["recipe"].get("params")

    def save(self) -> None:
        if self.server.raise_on_save is not None:
            raise self.server.raise_on_save
        self.server.save_calls += 1
        self.server.state = copy.deepcopy(self.state)


class _FakeProject:
    def __init__(self, recipe: _FakeRecipe):
        self.recipe = recipe

    def get_recipe(self, recipe_name: str) -> _FakeRecipe:
        assert recipe_name == "compute_scores"
        return self.recipe


class _FakeClient(FakeDSSClient):
    def __init__(self, recipe: _FakeRecipe, envs: list[dict]):
        super().__init__({"PROJ": _FakeProject(recipe)})
        self.envs = envs
        self.list_code_envs_calls = 0

    def list_code_envs(self) -> list[dict]:
        self.list_code_envs_calls += 1
        return copy.deepcopy(self.envs)


def _recipe_state(recipe_type: str = "python", params: dict | None = None) -> dict:
    if params is None:
        params = {
            "envSelection": {"envMode": "INHERIT"},
            "containerSelection": {"containerMode": "NONE"},
            "skipPrerunValidate": False,
        }
    return {
        "recipe": {
            "name": "compute_scores",
            "type": recipe_type,
            "params": params,
            "inputs": {"main": {"items": [{"ref": "raw_scores"}]}},
            "outputs": {"main": {"items": [{"ref": "scores", "appendMode": False}]}},
            "tags": ["kept"],
        },
        "payload": CODE,
    }


def _install(monkeypatch, state: dict, envs: list[dict] = ENVS):
    recipe = _FakeRecipe(state)
    client = _FakeClient(recipe, envs)
    monkeypatch.setattr(recipes, "get_dss_client", lambda: client)
    return recipe, client


def _set_env(env_mode: str, env_name: str | None = None) -> dict:
    return json.loads(
        asyncio.run(
            recipes.set_recipe_code_env(
                "PROJ", "compute_scores", env_mode, FakeContext(), env_name
            )
        )
    )


def test_explicit_env_changes_only_the_selection(monkeypatch):
    state = _recipe_state()
    before = copy.deepcopy(state)
    recipe, client = _install(monkeypatch, state)

    result = _set_env("EXPLICIT_ENV", "py-analytics")

    assert result == {
        "project_key": "PROJ",
        "recipe_name": "compute_scores",
        "previous_env_selection": {"envMode": "INHERIT"},
        "env_selection": {"envMode": "EXPLICIT_ENV", "envName": "py-analytics"},
    }
    expected = copy.deepcopy(before)
    expected["recipe"]["params"]["envSelection"] = {
        "envMode": "EXPLICIT_ENV",
        "envName": "py-analytics",
    }
    assert recipe.state == expected
    assert recipe.save_calls == 1
    assert client.list_code_envs_calls == 1


@pytest.mark.parametrize("env_mode", ["INHERIT", "USE_BUILTIN_MODE"])
def test_non_explicit_modes_clear_the_env_name(monkeypatch, env_mode):
    state = _recipe_state()
    state["recipe"]["params"]["envSelection"] = {
        "envMode": "EXPLICIT_ENV",
        "envName": "py-analytics",
    }
    recipe, client = _install(monkeypatch, state)

    result = _set_env(env_mode)

    assert result["previous_env_selection"] == {
        "envMode": "EXPLICIT_ENV",
        "envName": "py-analytics",
    }
    assert result["env_selection"] == {"envMode": env_mode}
    assert recipe.state["recipe"]["params"]["envSelection"] == {"envMode": env_mode}
    assert recipe.state["payload"] == CODE
    assert recipe.save_calls == 1
    # Only an explicit name needs the environment catalog.
    assert client.list_code_envs_calls == 0


@pytest.mark.parametrize("env_name", ["missing-env", "r-only"])
def test_unknown_or_non_python_env_is_refused_before_saving(monkeypatch, env_name):
    recipe, _ = _install(monkeypatch, _recipe_state())

    with pytest.raises(ValueError, match="No Python code environment"):
        _set_env("EXPLICIT_ENV", env_name)

    assert recipe.save_calls == 0
    assert recipe.state == _recipe_state()


@pytest.mark.parametrize(
    "recipe_type", ["r", "pyspark", "sql_query", "sync", "CustomCode_scorer"]
)
def test_only_python_recipes_are_supported(monkeypatch, recipe_type):
    recipe, client = _install(monkeypatch, _recipe_state(recipe_type))

    with pytest.raises(ValueError, match=f"'{recipe_type}' recipe"):
        _set_env("EXPLICIT_ENV", "py-analytics")

    assert recipe.save_calls == 0
    assert client.list_code_envs_calls == 0


@pytest.mark.parametrize("params", [{}, None, {"envSelection": "INHERIT"}])
def test_recipe_without_a_selection_is_refused(monkeypatch, params):
    state = _recipe_state(params=params)
    if params is None:
        del state["recipe"]["params"]
    recipe, _ = _install(monkeypatch, state)

    with pytest.raises(ValueError, match="does not expose"):
        _set_env("INHERIT")

    assert recipe.save_calls == 0


@pytest.mark.parametrize(
    ("env_mode", "env_name", "message"),
    [
        ("EXPLICIT_ENV", None, "env_name"),
        ("EXPLICIT_ENV", " ", "env_name"),
        ("INHERIT", "py-analytics", "only valid"),
        ("USE_BUILTIN_MODE", "py-analytics", "only valid"),
    ],
)
def test_invalid_arguments_are_refused_without_dataiku_calls(
    monkeypatch, env_mode, env_name, message
):
    monkeypatch.setattr(
        recipes, "get_dss_client", lambda: pytest.fail("No SDK call is allowed")
    )

    with pytest.raises(ValueError, match=message):
        _set_env(env_mode, env_name)


def test_rejected_save_leaves_the_recipe_untouched(monkeypatch):
    """Dataiku refuses a save when the project prevents overrides or the user lacks use."""
    recipe, _ = _install(monkeypatch, _recipe_state())
    recipe.raise_on_save = RuntimeError("Selection of code env is prevented")

    with pytest.raises(RuntimeError, match="prevented"):
        _set_env("EXPLICIT_ENV", "py-analytics")

    assert recipe.state == _recipe_state()


def _instance(instance_type: str) -> DSSInstance:
    return DSSInstance(
        name=instance_type,
        url="https://example.com",
        api_key="private-key",
        api_ticket=None,
        instance_type=instance_type,
        source="config",
        no_check_certificate=False,
    )


def test_mcp_schema_rejects_unknown_env_mode(monkeypatch):
    monkeypatch.setattr(stdio, "_current_instance", _instance("design"))
    monkeypatch.setattr(
        recipes, "get_dss_client", lambda: pytest.fail("No SDK call is allowed")
    )

    async def dispatch():
        async with Client(mcp) as client:
            return await client.call_tool(
                "set_recipe_code_env",
                {
                    "project_key": "PROJ",
                    "recipe_name": "compute_scores",
                    "env_mode": "EXPLICIT_CONTAINER",
                },
                raise_on_error=False,
            )

    result = asyncio.run(dispatch())
    assert result.is_error
    assert "env_mode" in result.content[0].text


def test_mcp_dispatch_saves_on_design(monkeypatch):
    monkeypatch.setattr(stdio, "_current_instance", _instance("design"))
    recipe, _ = _install(monkeypatch, _recipe_state())

    async def dispatch():
        async with Client(mcp) as client:
            return await client.call_tool(
                "set_recipe_code_env",
                {
                    "project_key": "PROJ",
                    "recipe_name": "compute_scores",
                    "env_mode": "USE_BUILTIN_MODE",
                },
            )

    result = asyncio.run(dispatch())
    assert json.loads(result.content[0].text)["env_selection"] == {
        "envMode": "USE_BUILTIN_MODE"
    }
    assert recipe.save_calls == 1
