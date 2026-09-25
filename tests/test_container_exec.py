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

"""Unit tests for container execution overrides across object types."""

import asyncio
import copy
import json

import pytest

from dataiku_mcp.tools import container_exec

from tests.utils.fakes import FakeContext, FakeDSSClient


class _FakeServerObject:
    """Server-side state for one object, handed out as detached settings copies.

    ``get_settings`` returns a copy, so a mutation only becomes visible to a
    later read once ``save`` commits it. That makes the tool's post-save
    read-back depend on the write actually happening, instead of observing the
    dict the tool just mutated in memory.
    """

    def __init__(self, settings_class, state: dict):
        self.settings_class = settings_class
        self.state = state
        self.save_calls = 0
        self.get_settings_calls = 0
        self.raise_on_save: Exception | None = None

    def get_settings(self):
        self.get_settings_calls += 1
        return self.settings_class(self, copy.deepcopy(self.state))

    def commit(self, state: dict) -> None:
        if self.raise_on_save is not None:
            raise self.raise_on_save
        self.save_calls += 1
        self.state = copy.deepcopy(state)


class _FakeRecipeSettings:
    """Stands in for recipe settings, which expose params and a JSON payload."""

    def __init__(self, server: _FakeServerObject, state: dict):
        self.server = server
        self.state = state

    def get_recipe_raw_definition(self) -> dict:
        return {"type": self.state["type"]}

    def get_recipe_params(self) -> dict:
        return self.state.get("params") or {}

    def get_json_payload(self) -> dict:
        payload = self.state.get("payload")
        if payload == "NOT_JSON":
            raise json.JSONDecodeError("Expecting value", "", 0)
        if payload == "UNAVAILABLE":
            raise RuntimeError("Dataiku is unavailable")
        return payload or {}

    def save(self) -> None:
        self.server.commit(self.state)


class _FakeRawSettings:
    """Stands in for the settings handles that expose one raw settings dict."""

    def __init__(self, server: _FakeServerObject, state: dict):
        self.server = server
        self.state = state

    def get_raw(self) -> dict:
        return self.state

    def save(self) -> None:
        self.server.commit(self.state)


def _recipe(state: dict) -> _FakeServerObject:
    return _FakeServerObject(_FakeRecipeSettings, state)


def _raw(state: dict) -> _FakeServerObject:
    return _FakeServerObject(_FakeRawSettings, state)


class _FakeAnalysis:
    def __init__(self, mltask_ids: list[str], mltask: _FakeServerObject):
        self.analysis_id = "analysis"
        self.mltask_ids = mltask_ids
        self.mltask = mltask
        self.list_ml_tasks_calls = 0

    def list_ml_tasks(self) -> dict:
        self.list_ml_tasks_calls += 1
        return {"mlTasks": [{"mlTaskId": task_id} for task_id in self.mltask_ids]}

    def get_ml_task(self, mltask_id: str) -> _FakeServerObject:
        assert mltask_id == self.mltask_ids[0]
        return self.mltask


class _FakeProject:
    def __init__(self, **objects):
        self.objects = objects

    def get_recipe(self, recipe_name: str):
        assert recipe_name == "object"
        return self.objects["recipe"]

    def get_analysis(self, analysis_id: str):
        assert analysis_id == "object"
        return self.objects["analysis"]

    def get_webapp(self, webapp_id: str):
        assert webapp_id == "object"
        return self.objects["webapp"]

    def get_knowledge_bank(self, knowledge_bank_id: str):
        assert knowledge_bank_id == "object"
        return self.objects["knowledge_bank"]

    def get_agent_tool(self, agent_tool_id: str):
        assert agent_tool_id == "object"
        return self.objects["agent_tool"]


def _install(monkeypatch, project: _FakeProject) -> None:
    monkeypatch.setattr(
        container_exec, "get_dss_client", lambda: FakeDSSClient({"PROJ": project})
    )


def _install_recipe(monkeypatch, state: dict) -> _FakeServerObject:
    recipe = _recipe(state)
    _install(monkeypatch, _FakeProject(recipe=recipe))
    return recipe


def _install_code_recipe(monkeypatch) -> _FakeServerObject:
    return _install_recipe(
        monkeypatch,
        {
            "type": "python",
            "params": {"containerSelection": {"containerMode": "INHERIT"}},
        },
    )


def _set_container(
    object_type: str, container_mode: str, container_config: str | None = None
) -> dict:
    return json.loads(
        asyncio.run(
            container_exec.set_container_exec_config(
                "PROJ",
                object_type,
                "object",
                container_mode,
                FakeContext(),
                container_config,
            )
        )
    )


def test_set_explicit_container_on_code_recipe(monkeypatch):
    recipe = _install_code_recipe(monkeypatch)

    result = _set_container("recipe", "EXPLICIT_CONTAINER", "compute-gpu")

    assert result == {
        "project_key": "PROJ",
        "object_type": "recipe",
        "object_id": "object",
        "container_selection": {
            "containerMode": "EXPLICIT_CONTAINER",
            "containerConf": "compute-gpu",
        },
    }
    assert recipe.state["params"]["containerSelection"] == {
        "containerMode": "EXPLICIT_CONTAINER",
        "containerConf": "compute-gpu",
    }
    assert recipe.save_calls == 1
    assert recipe.get_settings_calls == 2


def test_disable_container_in_params_engine_settings(monkeypatch):
    recipe = _install_recipe(
        monkeypatch,
        {
            "type": "shaker",
            "params": {
                "engineParams": {
                    "maxThreads": 8,
                    "containerSelection": {
                        "containerMode": "EXPLICIT_CONTAINER",
                        "containerConf": "compute-cpu",
                    },
                }
            },
        },
    )

    result = _set_container("recipe", "NONE")

    assert result["container_selection"] == {"containerMode": "NONE"}
    assert recipe.state["params"]["engineParams"]["maxThreads"] == 8
    assert recipe.save_calls == 1


def test_set_explicit_container_in_payload_engine_settings(monkeypatch):
    recipe = _install_recipe(
        monkeypatch,
        {
            "type": "join",
            "payload": {
                "engineParams": {
                    "lowerCaseSchemaIfEngineRequiresIt": True,
                    "containerSelection": {"containerMode": "INHERIT"},
                }
            },
        },
    )

    result = _set_container("recipe", "EXPLICIT_CONTAINER", "compute-cpu")

    assert result["container_selection"] == {
        "containerMode": "EXPLICIT_CONTAINER",
        "containerConf": "compute-cpu",
    }
    assert recipe.state["payload"]["engineParams"]["lowerCaseSchemaIfEngineRequiresIt"]
    assert recipe.save_calls == 1


def test_non_json_payload_reports_no_override(monkeypatch):
    """A sync or plugin recipe's payload is not JSON; that must not leak a decode error."""
    recipe = _install_recipe(monkeypatch, {"type": "sync", "payload": "NOT_JSON"})

    with pytest.raises(ValueError, match="does not expose"):
        _set_container("recipe", "NONE")

    assert recipe.save_calls == 0


def test_payload_read_failure_propagates(monkeypatch):
    recipe = _install_recipe(monkeypatch, {"type": "sync", "payload": "UNAVAILABLE"})

    with pytest.raises(RuntimeError, match="Dataiku is unavailable"):
        _set_container("recipe", "NONE")

    assert recipe.save_calls == 0


def test_reject_recipe_with_ambiguous_container_locations(monkeypatch):
    recipe = _install_recipe(
        monkeypatch,
        {
            "type": "grouping",
            "params": {"containerSelection": {"containerMode": "INHERIT"}},
            "payload": {
                "engineParams": {"containerSelection": {"containerMode": "NONE"}}
            },
        },
    )

    with pytest.raises(ValueError, match="several places"):
        _set_container("recipe", "NONE")

    assert recipe.save_calls == 0


def test_set_explicit_container_on_ml_task(monkeypatch):
    mltask = _raw(
        {
            "backendType": "PY_MEMORY",
            "envSelection": {"envMode": "USE_BUILTIN_MODE"},
            "containerSelection": {"containerMode": "INHERIT"},
        }
    )
    analysis = _FakeAnalysis(["task1"], mltask)
    _install(monkeypatch, _FakeProject(analysis=analysis))

    result = _set_container("ml_task", "EXPLICIT_CONTAINER", "training-gpu")

    assert result == {
        "project_key": "PROJ",
        "object_type": "ml_task",
        "object_id": "object",
        "mltask_id": "task1",
        "container_selection": {
            "containerMode": "EXPLICIT_CONTAINER",
            "containerConf": "training-gpu",
        },
    }
    assert mltask.state["envSelection"] == {"envMode": "USE_BUILTIN_MODE"}
    assert mltask.save_calls == 1
    # the identifier is resolved once, not again for the post-save read-back
    assert analysis.list_ml_tasks_calls == 1


def test_reject_analysis_without_single_ml_task(monkeypatch):
    mltask = _raw({"containerSelection": {"containerMode": "INHERIT"}})
    analysis = _FakeAnalysis(["task1", "task2"], mltask)
    _install(monkeypatch, _FakeProject(analysis=analysis))

    with pytest.raises(ValueError, match="Expected exactly 1 ML task"):
        _set_container("ml_task", "NONE")

    assert mltask.save_calls == 0


def test_set_container_on_webapp_backend(monkeypatch):
    webapp = _raw(
        {
            "id": "object",
            "type": "BOKEH",
            "apiKey": "secret",
            "params": {
                "autoStartBackend": True,
                "infra": {
                    "containerSelection": {
                        "containerMode": "EXPLICIT_CONTAINER",
                        "containerConf": "eks-default",
                    }
                },
            },
        }
    )
    _install(monkeypatch, _FakeProject(webapp=webapp))

    result = _set_container("webapp", "INHERIT")

    assert result == {
        "project_key": "PROJ",
        "object_type": "webapp",
        "object_id": "object",
        "container_selection": {"containerMode": "INHERIT"},
    }
    assert webapp.state["apiKey"] == "secret"
    assert webapp.state["params"]["autoStartBackend"] is True
    assert webapp.save_calls == 1


def test_set_container_on_knowledge_bank(monkeypatch):
    bank = _raw(
        {
            "id": "object",
            "vectorStoreType": "CHROMA",
            "envSelection": {"envMode": "USE_BUILTIN_MODE"},
            "containerExecSelection": {"containerMode": "INHERIT"},
        }
    )
    _install(monkeypatch, _FakeProject(knowledge_bank=bank))

    result = _set_container("knowledge_bank", "EXPLICIT_CONTAINER", "compute-cpu")

    assert result == {
        "project_key": "PROJ",
        "object_type": "knowledge_bank",
        "object_id": "object",
        "container_selection": {
            "containerMode": "EXPLICIT_CONTAINER",
            "containerConf": "compute-cpu",
        },
    }
    assert bank.state["envSelection"] == {"envMode": "USE_BUILTIN_MODE"}
    assert bank.save_calls == 1


def test_set_container_on_agent_tool(monkeypatch):
    tool = _raw(
        {
            "id": "object",
            "type": "InlinePython",
            "params": {
                "code": "print(1)",
                "containerExecSelection": {
                    "containerMode": "EXPLICIT_CONTAINER",
                    "containerConf": "compute-cpu",
                },
            },
        }
    )
    _install(monkeypatch, _FakeProject(agent_tool=tool))

    result = _set_container("agent_tool", "NONE")

    assert result == {
        "project_key": "PROJ",
        "object_type": "agent_tool",
        "object_id": "object",
        "container_selection": {"containerMode": "NONE"},
    }
    assert tool.state["params"]["code"] == "print(1)"
    assert tool.save_calls == 1


def test_rejected_save_leaves_the_object_untouched(monkeypatch):
    """Dataiku refuses the write for a tool whose plugin type it cannot resolve."""
    tool = _raw(
        {
            "type": "Custom_agent_tool_missing_plugin",
            "params": {"containerExecSelection": {"containerMode": "NONE"}},
        }
    )
    tool.raise_on_save = RuntimeError("Unknown tool type")
    _install(monkeypatch, _FakeProject(agent_tool=tool))

    with pytest.raises(RuntimeError, match="Unknown tool type"):
        _set_container("agent_tool", "INHERIT")

    assert tool.state["params"]["containerExecSelection"] == {"containerMode": "NONE"}
    assert tool.save_calls == 0


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
    recipe = _install_code_recipe(monkeypatch)

    with pytest.raises(ValueError, match=message):
        _set_container("recipe", container_mode, container_config)

    assert recipe.save_calls == 0


@pytest.mark.parametrize("object_type", ["scenario", "saved_model"])
def test_reject_unknown_object_type(monkeypatch, object_type):
    recipe = _install_code_recipe(monkeypatch)

    with pytest.raises(ValueError, match="object_type"):
        _set_container(object_type, "NONE")

    assert recipe.save_calls == 0


@pytest.mark.parametrize(
    ("object_type", "state"),
    [
        ("webapp", {"type": "STANDARD", "params": {}}),
        ("knowledge_bank", {"vectorStoreType": "CHROMA"}),
        ("agent_tool", {"type": "DatasetRowLookup", "params": {}}),
    ],
)
def test_reject_raw_object_without_container_selection(monkeypatch, object_type, state):
    server = _raw(state)
    _install(monkeypatch, _FakeProject(**{object_type: server}))

    with pytest.raises(ValueError, match="does not expose"):
        _set_container(object_type, "NONE")

    assert server.save_calls == 0


def test_reject_recipe_without_container_selection(monkeypatch):
    recipe = _install_recipe(monkeypatch, {"type": "download", "params": {}})

    with pytest.raises(ValueError, match="does not expose"):
        _set_container("recipe", "NONE")

    assert recipe.save_calls == 0


def test_reject_ml_task_without_container_selection(monkeypatch):
    mltask = _raw({"backendType": "PY_MEMORY"})
    _install(monkeypatch, _FakeProject(analysis=_FakeAnalysis(["task1"], mltask)))

    with pytest.raises(ValueError, match="does not expose"):
        _set_container("ml_task", "NONE")

    assert mltask.save_calls == 0
