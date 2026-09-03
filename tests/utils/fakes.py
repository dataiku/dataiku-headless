# Copyright 2026 Dataiku
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

"""Shared fakes for tool unit tests.

Tool tests must run without a live Dataiku connection (same constraint as
``test_smoke.py``), so tests monkeypatch ``get_dss_client`` in the module under
test with a ``FakeDSSClient`` built here and drive the tool functions directly.
"""

import json


class FakeContext:
    """Stands in for the FastMCP ``Context`` argument of tool functions."""

    async def info(self, message: str) -> None:
        pass


class FakeProject:
    def __init__(self, variables: dict | None = None):
        self.variables = (
            variables if variables is not None else {"standard": {}, "local": {}}
        )
        self.set_calls: list[dict] = []

    def get_variables(self) -> dict:
        return json.loads(json.dumps(self.variables))

    def set_variables(self, obj: dict) -> None:
        self.set_calls.append(obj)
        self.variables = json.loads(json.dumps(obj))


class FakeDSSClient:
    def __init__(self, projects: dict[str, FakeProject] | None = None):
        self.projects = projects or {}

    def get_project(self, project_key: str) -> FakeProject:
        if project_key not in self.projects:
            raise KeyError(f"Unknown fake project: {project_key}")
        return self.projects[project_key]
