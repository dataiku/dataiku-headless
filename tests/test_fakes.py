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

"""Contract tests for shared fake Dataiku test infrastructure."""

from tests.utils.fakes import FakeDSSClient, FakeProject


def test_fake_dss_client_returns_registered_project():
    project = FakeProject()
    client = FakeDSSClient({"PROJ": project})

    assert client.get_project("PROJ") is project


def test_fake_dss_client_unknown_project_key_fails():
    client = FakeDSSClient({"PROJ": FakeProject()})

    try:
        client.get_project("OTHER")
    except KeyError as exc:
        assert "OTHER" in str(exc)
    else:
        raise AssertionError("Expected unknown fake project lookup to fail")


def test_fake_project_set_variables_records_calls_and_updates_state():
    project = FakeProject({"standard": {"old": "x"}, "local": {}})
    payload = {"standard": {"new": "y"}, "local": {"env": "dev"}}

    project.set_variables(payload)

    assert project.set_calls == [payload]
    assert project.variables == payload


def test_fake_project_get_variables_returns_detached_copy():
    project = FakeProject({"standard": {"x": 1}, "local": {}})

    result = project.get_variables()
    result["standard"]["x"] = 2

    assert project.variables == {"standard": {"x": 1}, "local": {}}
