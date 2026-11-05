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
from dataikuapi.dss.recipe import CodeRecipeCreator

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
        recipes.create_r_recipe(
            "P",
            "r1",
            "x <- 1",
            "out",
            FakeContext(),
            ["a"],
            output_connection="test_store",
        )
    )
    project.new_recipe.assert_called_once_with("r", "r1")
    creator.with_input.assert_called_once_with("a")
    if exists:
        creator.with_output.assert_called_once_with("out")
    else:
        creator.with_new_output_dataset.assert_called_once_with("out", "test_store")
    creator.create.assert_called_once()
    assert result["output_created"] is not exists


def test_create_r_recipe_requires_connection_before_creating_output(monkeypatch):
    project = _project(monkeypatch)
    project.get_dataset.return_value.exists.return_value = False
    with pytest.raises(ValueError, match="output_connection"):
        asyncio.run(recipes.create_r_recipe("P", "r1", "x", "out", FakeContext()))
    creator = project.new_recipe.return_value.with_script.return_value
    creator.with_new_output_dataset.assert_not_called()
    creator.create.assert_not_called()


def _failing_recipe_project(monkeypatch, existing_output=False):
    project = _project(monkeypatch)
    # Use the real SDK creator: with_new_output_dataset creates the dataset
    # immediately, before create_recipe can reject a missing input.
    project.new_recipe.side_effect = lambda kind, name: CodeRecipeCreator(
        name, kind, project
    )
    project.get_dataset.return_value.exists.return_value = existing_output
    project.create_recipe.side_effect = RuntimeError("private exception details")
    return project


def test_failed_recipe_creation_removes_only_its_new_output(monkeypatch):
    project = _failing_recipe_project(monkeypatch)
    with pytest.raises(ValueError, match="new output dataset was removed"):
        asyncio.run(
            recipes.create_r_recipe(
                "P", "r1", "x", "out", FakeContext(), ["missing"], "test_store"
            )
        )
    project.new_managed_dataset_creation_helper.return_value.create.assert_called_once_with(
        overwrite=False
    )
    project.get_dataset.return_value.delete.assert_called_once_with(drop_data=False)


def test_failed_recipe_creation_preserves_existing_output(monkeypatch):
    project = _failing_recipe_project(monkeypatch, existing_output=True)
    result = _load(recipes.create_r_recipe("P", "r1", "x", "out", FakeContext()))
    assert result["status"] == "partial_failure"
    assert result["output_created"] is False
    assert result["recipe_created"] is None
    project.get_dataset.return_value.delete.assert_not_called()
    assert "private exception details" not in json.dumps(result)


@pytest.mark.parametrize("direction", ["inputs", "outputs"])
def test_failed_recipe_creation_preserves_output_referenced_by_another_recipe(
    monkeypatch, direction
):
    project = _failing_recipe_project(monkeypatch)
    project.list_recipes.side_effect = [
        [],
        [{"name": "another", direction: {"main": {"items": [{"ref": "P.out"}]}}}],
    ]
    result = _load(
        recipes.create_r_recipe(
            "P", "r1", "x", "out", FakeContext(), output_connection="test_store"
        )
    )
    assert result["status"] == "partial_failure"
    project.get_dataset.return_value.delete.assert_not_called()


def test_lost_recipe_creation_response_preserves_committed_recipe_output(monkeypatch):
    project = _failing_recipe_project(monkeypatch)
    project.list_recipes.side_effect = [[], [{"name": "r1"}]]
    result = _load(
        recipes.create_r_recipe(
            "P", "r1", "x", "out", FakeContext(), output_connection="test_store"
        )
    )
    assert result["status"] == "partial_failure"
    assert result["recipe_name"] == "r1"
    project.get_dataset.return_value.delete.assert_not_called()


@pytest.mark.parametrize("stage", ["list", "delete"])
def test_failed_recipe_cleanup_returns_recoverable_output_identity(monkeypatch, stage):
    project = _failing_recipe_project(monkeypatch)
    if stage == "list":
        project.list_recipes.side_effect = [[], RuntimeError("private")]
    else:
        project.get_dataset.return_value.delete.side_effect = RuntimeError("private")
    result = _load(
        recipes.create_r_recipe(
            "P", "r1", "x", "out", FakeContext(), output_connection="test_store"
        )
    )
    assert result["status"] == "partial_failure"
    assert result["output_created"] is True
    assert result["output_dataset"] == "out"
    assert "private" not in json.dumps(result)


def test_uncertain_output_creation_does_not_delete_unowned_dataset(monkeypatch):
    project = _project(monkeypatch)
    project.get_dataset.return_value.exists.return_value = False
    creator = project.new_recipe.return_value.with_script.return_value
    creator.with_new_output_dataset.side_effect = RuntimeError("private")
    result = _load(
        recipes.create_r_recipe(
            "P", "r1", "x", "out", FakeContext(), output_connection="test_store"
        )
    )
    assert result["status"] == "partial_failure"
    assert result["output_created"] is None
    assert result["recipe_created"] is False
    creator.create.assert_not_called()
    project.get_dataset.return_value.delete.assert_not_called()


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
    assert result == {
        "webapp_id": "W1",
        "name": "app",
        "backend_future_id": "F1",
        "code_saved": True,
        "backend_startup_status": "requested",
    }


@pytest.mark.parametrize("operation", ["create", "update"])
@pytest.mark.parametrize("stage", ["read", "save", "start"])
def test_shiny_partial_failure_retains_app_identity_and_save_outcome(
    monkeypatch, operation, stage
):
    project = _project(monkeypatch)
    _webapp(project, "SHINY")
    app = project.get_webapp.return_value
    failure = RuntimeError("private apiKey=not-for-output")
    if stage == "read":
        app.get_settings.side_effect = failure
    elif stage == "save":
        app.get_settings.return_value.save.side_effect = failure
    else:
        app.start_or_restart_backend.side_effect = failure
    if operation == "create":
        result = _load(
            webapps.create_shiny_webapp("P", "app", "ui", "server", FakeContext())
        )
        project.create_webapp.assert_called_once()
    else:
        result = _load(webapps.update_shiny_webapp("P", "W1", FakeContext(), ui="new"))
        project.create_webapp.assert_not_called()
    assert result["webapp_id"] == "W1"
    assert result["status"] == "partial_failure"
    assert result["code_saved"] is {"read": False, "save": None, "start": True}[stage]
    assert result["backend_startup_status"] == (
        "unknown" if stage == "start" else "not_attempted"
    )
    if stage != "start":
        app.start_or_restart_backend.assert_not_called()
    assert "private" not in json.dumps(result)


def test_update_shiny_webapp_keeps_omitted_code(monkeypatch):
    project = _project(monkeypatch)
    raw = _webapp(project, "SHINY", {"ui": "old", "server": "kept"})
    asyncio.run(webapps.update_shiny_webapp("P", "W1", FakeContext(), ui="new"))
    assert raw["params"] == {"ui": "new", "server": "kept"}
    project.get_webapp.return_value.start_or_restart_backend.assert_called_once()


def test_update_shiny_webapp_without_code_only_restarts(monkeypatch):
    project = _project(monkeypatch)
    raw = _webapp(project, "SHINY", {"ui": "kept", "server": "kept"})
    asyncio.run(webapps.update_shiny_webapp("P", "W1", FakeContext()))
    assert raw["params"] == {"ui": "kept", "server": "kept"}
    project.get_webapp.return_value.start_or_restart_backend.assert_called_once()
    project.get_webapp.return_value.get_settings.return_value.save.assert_not_called()


def test_update_shiny_webapp_refuses_other_webapp_types(monkeypatch):
    project = _project(monkeypatch)
    _webapp(project, "DASH")
    with pytest.raises(ValueError, match="Cobuild"):
        asyncio.run(webapps.update_shiny_webapp("P", "W1", FakeContext(), ui="x"))
    project.get_webapp.return_value.start_or_restart_backend.assert_not_called()
