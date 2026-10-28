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

"""Tests for the direct R recipe and Shiny webapp writes that Cobuild cannot build."""

import asyncio
import json
from unittest.mock import MagicMock

import pytest

from dataiku_mcp.tools import recipes, webapps
from tests.utils.fakes import FakeContext


def _project(monkeypatch) -> MagicMock:
    project = MagicMock()
    project.list_recipes.return_value = []
    client = MagicMock()
    client.get_project.return_value = project
    monkeypatch.setattr(recipes, "get_dss_client", lambda: client)
    monkeypatch.setattr(webapps, "get_dss_client", lambda: client)
    return project


def _recipe_settings(project, recipe_type: str) -> MagicMock:
    settings = project.get_recipe.return_value.get_settings.return_value
    raw = {"type": recipe_type, "inputs": {"main": {"items": []}}}
    settings.get_recipe_raw_definition.return_value = raw
    settings.get_recipe_inputs.return_value = raw["inputs"]
    return settings


def _webapp(project, webapp_type: str, params: dict | None = None) -> dict:
    webapp = project.get_webapp.return_value
    project.create_webapp.return_value = webapp
    webapp.webapp_id = "W1"
    webapp.start_or_restart_backend.return_value.job_id = "F1"
    raw = {"name": "app", "type": webapp_type, "params": params or {}}
    webapp.get_settings.return_value.get_raw.return_value = raw
    return raw


def _load(coro) -> dict:
    return json.loads(asyncio.run(coro))


@pytest.mark.parametrize("exists", [False, True])
def test_create_r_recipe_wires_inputs_and_output(monkeypatch, exists):
    project = _project(monkeypatch)
    project.get_dataset.return_value.exists.return_value = exists
    creator = project.new_recipe.return_value.with_script.return_value
    result = _load(
        recipes.create_r_recipe("P", "r1", "x <- 1", "out", FakeContext(), ["a"])
    )
    project.new_recipe.assert_called_once_with("r", "r1")
    creator.with_input.assert_called_once_with("a")
    if exists:
        creator.with_output.assert_called_once_with("out")
    else:
        creator.with_new_output_dataset.assert_called_once_with(
            "out", "filesystem_managed"
        )
    creator.create.assert_called_once()
    assert result["output_created"] is not exists


def test_create_r_recipe_rejects_existing_name_before_creating(monkeypatch):
    project = _project(monkeypatch)
    project.list_recipes.return_value = [{"name": "r1"}]
    with pytest.raises(ValueError, match="update_r_recipe"):
        asyncio.run(recipes.create_r_recipe("P", "r1", "x", "out", FakeContext()))
    project.new_recipe.assert_not_called()


def test_update_r_recipe_replaces_code_and_inputs(monkeypatch):
    settings = _recipe_settings(_project(monkeypatch), "r")
    result = _load(
        recipes.update_r_recipe("P", "r1", FakeContext(), code="y", inputs=["a", "b"])
    )
    settings.set_code.assert_called_once_with("y")
    settings.save.assert_called_once()
    assert result["inputs"] == ["a", "b"]


def test_update_r_recipe_refuses_other_recipe_types(monkeypatch):
    settings = _recipe_settings(_project(monkeypatch), "python")
    with pytest.raises(ValueError, match="Cobuild"):
        asyncio.run(recipes.update_r_recipe("P", "r1", FakeContext(), code="x"))
    settings.save.assert_not_called()


def test_update_r_recipe_requires_a_change():
    with pytest.raises(ValueError, match="code, inputs"):
        asyncio.run(recipes.update_r_recipe("P", "r1", FakeContext()))


def test_create_shiny_webapp_writes_code_and_starts_backend(monkeypatch):
    project = _project(monkeypatch)
    raw = _webapp(project, "SHINY")
    result = _load(
        webapps.create_shiny_webapp("P", "app", "ui", "server", FakeContext())
    )
    project.create_webapp.assert_called_once_with("app", "SHINY")
    assert raw["params"] == {"ui": "ui", "server": "server"}
    assert result == {"webapp_id": "W1", "name": "app", "backend_future_id": "F1"}


def test_update_shiny_webapp_keeps_omitted_code(monkeypatch):
    project = _project(monkeypatch)
    raw = _webapp(project, "SHINY", {"ui": "old", "server": "kept"})
    asyncio.run(webapps.update_shiny_webapp("P", "W1", FakeContext(), ui="new"))
    assert raw["params"] == {"ui": "new", "server": "kept"}
    project.get_webapp.return_value.start_or_restart_backend.assert_called_once()


def test_update_shiny_webapp_refuses_other_webapp_types(monkeypatch):
    project = _project(monkeypatch)
    _webapp(project, "DASH")
    with pytest.raises(ValueError, match="Cobuild"):
        asyncio.run(webapps.update_shiny_webapp("P", "W1", FakeContext(), ui="x"))
    project.get_webapp.return_value.start_or_restart_backend.assert_not_called()
