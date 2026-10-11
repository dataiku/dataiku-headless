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

"""Unit tests for project creation."""

import asyncio
import json

from dataiku_mcp.tools import projects

from tests.utils.fakes import FakeContext


class _RecordingProject:
    def __init__(self):
        self.metadata = {"label": "Sales", "tags": []}
        self.set_calls: list[dict] = []

    def get_metadata(self) -> dict:
        return dict(self.metadata)

    def set_metadata(self, metadata: dict) -> None:
        self.set_calls.append(metadata)
        self.metadata = metadata


class _RecordingFolder:
    id = "folder1"

    def __init__(self):
        self.created: list[tuple] = []

    def create_project(self, project_key, name, owner):
        self.created.append((project_key, name, owner))

    def get_path(self) -> str:
        return "/Team"


class _RecordingClient:
    def __init__(self):
        self.created: list[tuple] = []
        self.project = _RecordingProject()
        self.folder = _RecordingFolder()

    def get_auth_info(self) -> dict:
        return {"authIdentifier": "owner1"}

    def create_project(self, project_key, name, owner, **kwargs):
        self.created.append((project_key, name, owner, kwargs))

    def get_project(self, project_key):
        return self.project

    def get_project_folder(self, folder_id):
        assert folder_id == self.folder.id
        return self.folder


def _install(monkeypatch) -> _RecordingClient:
    client = _RecordingClient()
    monkeypatch.setattr(projects, "get_dss_client", lambda: client)
    return client


def test_create_project_writes_short_desc_not_long_description(monkeypatch):
    client = _install(monkeypatch)

    result = json.loads(
        asyncio.run(
            projects.create_project(
                "PROJ", "Sales", FakeContext(), short_desc="Monthly sales summary."
            )
        )
    )

    assert client.created == [("PROJ", "Sales", "owner1", {})]
    assert client.project.metadata["shortDesc"] == "Monthly sales summary."
    assert "description" not in client.project.metadata
    assert result == {"projectKey": "PROJ", "name": "Sales", "owner": "owner1"}


def test_create_project_without_short_desc_leaves_metadata(monkeypatch):
    client = _install(monkeypatch)

    asyncio.run(projects.create_project("PROJ", "Sales", FakeContext()))

    assert client.created == [("PROJ", "Sales", "owner1", {})]
    assert client.project.set_calls == []


def test_create_project_in_folder_writes_short_desc(monkeypatch):
    client = _install(monkeypatch)

    result = json.loads(
        asyncio.run(
            projects.create_project(
                "PROJ",
                "Sales",
                FakeContext(),
                short_desc="Monthly sales summary.",
                folder_id="folder1",
            )
        )
    )

    assert client.created == []
    assert client.folder.created == [("PROJ", "Sales", "owner1")]
    assert client.project.metadata["shortDesc"] == "Monthly sales summary."
    assert result == {
        "projectKey": "PROJ",
        "name": "Sales",
        "owner": "owner1",
        "folder_id": "folder1",
        "folder_path": "/Team",
    }
