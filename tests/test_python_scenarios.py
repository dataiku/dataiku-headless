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

"""Unit tests for Python-script scenario creation, script edits, and inspection."""

import asyncio
import copy
import json

import pytest
import requests
from dataikuapi.utils import DataikuException
from fastmcp import Client

from dataiku_mcp import mcp
from dataiku_mcp.config import stdio
from dataiku_mcp.config.models import DSSInstance
from dataiku_mcp.tools import scenarios

from tests.utils.fakes import FakeContext

SAMPLE_SCRIPT = "# Dataiku sample script\nscenario.build_dataset('example')\n"
SCRIPT = (
    "from dataiku.scenario import Scenario\nScenario().set_scenario_variables(x=1)\n"
)


class _FakeScenario:
    """Server-side scenario state, handed out as detached settings copies.

    Saving mirrors the SDK: the definition is written first, then the script, so
    a failure between the two leaves the earlier write in place.
    """

    def __init__(self, definition: dict, script: str | None):
        self.id = definition["id"]
        self.definition = definition
        self.script = script
        self.definition_saves = 0
        self.script_saves = 0
        self.raise_on_definition_save: Exception | None = None
        self.raise_on_script_save: Exception | None = None
        self.stored_script_override: str | None = None

    def get_settings(self):
        return _FakeScenarioSettings(self, copy.deepcopy(self.definition), self.script)


class _FakeScenarioSettings:
    def __init__(self, server: _FakeScenario, definition: dict, script: str | None):
        self.server = server
        self.definition = definition
        self._script = script

    def get_raw(self) -> dict:
        return self.definition

    @property
    def code(self) -> str:
        if self.definition["type"] != "custom_python":
            raise AttributeError("step-based settings have no code")
        return self._script

    @code.setter
    def code(self, script: str) -> None:
        if self.definition["type"] != "custom_python":
            raise AttributeError("step-based settings have no code")
        self._script = script

    def save(self) -> None:
        server = self.server
        if server.raise_on_definition_save is not None:
            raise server.raise_on_definition_save
        server.definition_saves += 1
        server.definition = copy.deepcopy(self.definition)
        if self.definition["type"] != "custom_python":
            return
        if server.raise_on_script_save is not None:
            raise server.raise_on_script_save
        server.script_saves += 1
        server.script = (
            server.stored_script_override
            if server.stored_script_override is not None
            else self._script
        )


class _FakeProject:
    def __init__(self):
        self.scenarios: dict[str, _FakeScenario] = {}
        self.create_calls: list[tuple] = []
        self.raise_on_create: Exception | None = None
        self.prepare_created = None

    def create_scenario(self, scenario_name, type, definition=None):
        self.create_calls.append((scenario_name, type, copy.deepcopy(definition)))
        if self.raise_on_create is not None:
            raise self.raise_on_create
        scenario = _FakeScenario(
            {
                **definition,
                "id": "NIGHTLY_CHECK",
                "name": scenario_name,
                "type": type,
                "projectKey": "PROJ",
            },
            SAMPLE_SCRIPT,
        )
        if self.prepare_created is not None:
            self.prepare_created(scenario)
        self.scenarios[scenario.id] = scenario
        return scenario

    def get_scenario(self, scenario_id: str) -> _FakeScenario:
        return self.scenarios[scenario_id]


class _FakeClient:
    def __init__(self, project: _FakeProject):
        self.project = project

    def get_project(self, project_key: str) -> _FakeProject:
        assert project_key == "PROJ"
        return self.project


def _install(monkeypatch) -> _FakeProject:
    project = _FakeProject()
    monkeypatch.setattr(scenarios, "get_dss_client", lambda: _FakeClient(project))
    return project


def _existing(project: _FakeProject, scenario_type: str = "custom_python"):
    definition = {
        "id": "WEEKLY",
        "projectKey": "PROJ",
        "name": "Weekly refresh",
        "type": scenario_type,
        "active": True,
        "tags": ["ops"],
        "shortDesc": "Kept",
        "params": {"envSelection": {"envMode": "INHERIT"}}
        if scenario_type == "custom_python"
        else {"steps": [{"type": "build_flowitem"}]},
        "triggers": [{"type": "temporal", "active": True}],
        "reporters": [{"messaging": {"type": "mail-scenario"}}],
    }
    scenario = _FakeScenario(
        definition, "print('old')\n" if scenario_type == "custom_python" else None
    )
    project.scenarios[scenario.id] = scenario
    return scenario


def _create(name: str = "Nightly check", script: str = SCRIPT) -> dict:
    return json.loads(
        asyncio.run(
            scenarios.create_python_scenario("PROJ", name, script, FakeContext())
        )
    )


def _set_script(script: str = SCRIPT, scenario_id: str = "WEEKLY") -> dict:
    return json.loads(
        asyncio.run(
            scenarios.set_python_scenario_script(
                "PROJ", scenario_id, script, FakeContext()
            )
        )
    )


def test_create_makes_an_inactive_trigger_free_python_scenario(monkeypatch):
    project = _install(monkeypatch)

    result = _create()

    assert project.create_calls == [
        (
            "Nightly check",
            "custom_python",
            {"params": {}, "active": False, "triggers": [], "reporters": []},
        )
    ]
    assert result == {
        "status": "python_scenario_created",
        "project_key": "PROJ",
        "scenario_id": "NIGHTLY_CHECK",
        "name": "Nightly check",
        "type": "custom_python",
        "active": False,
        "trigger_count": 0,
    }
    assert project.scenarios["NIGHTLY_CHECK"].script == SCRIPT


def test_refused_create_propagates_and_creates_nothing(monkeypatch):
    project = _install(monkeypatch)
    project.raise_on_create = DataikuException(
        "LicenseRestrictionException: Python scenarios are not available"
    )

    with pytest.raises(DataikuException, match="not available"):
        _create()

    assert project.scenarios == {}


def test_unanswered_create_tells_the_caller_to_check_before_retrying(monkeypatch):
    project = _install(monkeypatch)
    project.raise_on_create = requests.ConnectionError("connection reset")

    with pytest.raises(RuntimeError, match="list_scenarios before retrying"):
        _create()


@pytest.mark.parametrize(
    "failure",
    [
        "definition",
        "script",
    ],
)
def test_script_failure_after_create_reports_the_scenario_as_unconfirmed(
    monkeypatch, failure
):
    project = _install(monkeypatch)

    def fail(scenario):
        error = DataikuException("You may not write code")
        if failure == "definition":
            scenario.raise_on_definition_save = error
        else:
            scenario.raise_on_script_save = error

    project.prepare_created = fail

    result = _create()

    assert result["status"] == "python_scenario_script_unconfirmed"
    assert result["scenario_id"] == "NIGHTLY_CHECK"
    assert result["error_type"] == "DataikuException"
    assert "set_python_scenario_script" in result["hint"]
    assert "Do not run it" in result["hint"]
    created = project.scenarios["NIGHTLY_CHECK"]
    assert created.script == SAMPLE_SCRIPT
    assert created.definition["active"] is False
    assert created.definition["triggers"] == []


def test_unmatched_script_read_back_is_not_reported_as_created(monkeypatch):
    project = _install(monkeypatch)
    project.prepare_created = lambda scenario: setattr(
        scenario, "stored_script_override", "print('other')\n"
    )

    result = _create()

    assert result["status"] == "python_scenario_script_unconfirmed"
    assert "error" not in result


def test_set_script_replaces_only_the_script(monkeypatch):
    project = _install(monkeypatch)
    scenario = _existing(project)
    before = copy.deepcopy(scenario.definition)

    result = _set_script()

    assert result == {
        "project_key": "PROJ",
        "scenario_id": "WEEKLY",
        "name": "Weekly refresh",
        "type": "custom_python",
        "active": True,
        "trigger_count": 1,
    }
    assert scenario.script == SCRIPT
    assert scenario.definition == before
    assert (scenario.definition_saves, scenario.script_saves) == (1, 1)


def test_set_script_refuses_a_step_based_scenario(monkeypatch):
    project = _install(monkeypatch)
    scenario = _existing(project, "step_based")

    with pytest.raises(ValueError, match="'step_based' scenario"):
        _set_script()

    assert scenario.definition_saves == 0


def test_set_script_refused_by_dataiku_keeps_the_old_script(monkeypatch):
    project = _install(monkeypatch)
    scenario = _existing(project)
    scenario.raise_on_definition_save = DataikuException("You may not write code")

    with pytest.raises(DataikuException, match="may not write code"):
        _set_script()

    assert scenario.script == "print('old')\n"


def test_set_script_unmatched_read_back_raises(monkeypatch):
    project = _install(monkeypatch)
    scenario = _existing(project)
    scenario.stored_script_override = "print('other')\n"

    with pytest.raises(RuntimeError, match="repeating this call is safe"):
        _set_script()


@pytest.mark.parametrize(
    ("call", "message"),
    [
        (lambda: _create(name=" "), "name"),
        (lambda: _create(script=" \n"), "script"),
        (lambda: _set_script(script=""), "script"),
        (lambda: _set_script(scenario_id=" "), "scenario_id"),
    ],
)
def test_blank_arguments_are_refused_without_dataiku_calls(monkeypatch, call, message):
    monkeypatch.setattr(
        scenarios, "get_dss_client", lambda: pytest.fail("No SDK call is allowed")
    )

    with pytest.raises(ValueError, match=message):
        call()


def _get_settings(scenario_id: str = "WEEKLY") -> dict:
    return json.loads(
        asyncio.run(scenarios.get_scenario_settings("PROJ", scenario_id, FakeContext()))
    )


def test_get_settings_includes_the_python_script(monkeypatch):
    project = _install(monkeypatch)
    scenario = _existing(project)

    assert _get_settings() == {**scenario.definition, "script": "print('old')\n"}


def test_get_settings_leaves_step_based_scenarios_unchanged(monkeypatch):
    project = _install(monkeypatch)
    scenario = _existing(project, "step_based")

    assert _get_settings() == scenario.definition


def test_mcp_dispatch_creates_on_design(monkeypatch):
    monkeypatch.setattr(
        stdio,
        "_current_instance",
        DSSInstance(
            name="design",
            url="https://example.com",
            api_key="private-key",
            api_ticket=None,
            instance_type="design",
            source="config",
            no_check_certificate=False,
        ),
    )
    project = _install(monkeypatch)

    async def dispatch():
        async with Client(mcp) as client:
            return await client.call_tool(
                "create_python_scenario",
                {"project_key": "PROJ", "name": "Nightly check", "script": SCRIPT},
            )

    result = asyncio.run(dispatch())
    assert json.loads(result.content[0].text)["status"] == "python_scenario_created"
    assert project.scenarios["NIGHTLY_CHECK"].script == SCRIPT
