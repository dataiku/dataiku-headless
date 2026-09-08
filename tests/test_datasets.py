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

"""Tests for uploaded-dataset creation and dataset export safeguards."""

import asyncio
import json

import pytest

from dataiku_mcp.tools import datasets
from dataiku_mcp.tools.datasets import _serialize_csv_value
from tests.utils.fakes import FakeContext


class _FakeProject:
    def __init__(self, *, has_existing_dataset: bool):
        self.has_existing_dataset = has_existing_dataset
        self.create_called = False

    def list_datasets(self) -> list[dict]:
        return [{"name": "existing"}] if self.has_existing_dataset else []

    def create_upload_dataset(self, dataset_name: str, connection: str):
        self.create_called = True
        return _CreatedDataset()


class _Settings:
    def __init__(self):
        self.saved = False

    def save(self) -> None:
        self.saved = True


class _CreatedDataset:
    def __init__(self):
        self.uploaded = None
        self.settings = _Settings()

    def uploaded_add_file(self, handle, filename: str) -> None:
        self.uploaded = (filename, handle.read())

    def autodetect_settings(self) -> _Settings:
        return self.settings

    def get_schema(self) -> dict:
        return {"columns": [{"name": "value", "type": "bigint"}]}


class _FakeClient:
    def __init__(self, project: _FakeProject):
        self.project = project

    def get_project(self, project_key: str) -> _FakeProject:
        assert project_key == "PROJECT"
        return self.project


def test_invalid_upload_file_does_not_create_a_dataset(monkeypatch, tmp_path):
    project = _FakeProject(has_existing_dataset=True)
    monkeypatch.setattr(datasets, "get_dss_client", lambda: _FakeClient(project))

    with pytest.raises(FileNotFoundError):
        asyncio.run(
            datasets.create_upload_dataset(
                "PROJECT",
                "new-dataset",
                str(tmp_path / "missing.csv"),
                FakeContext(),
                connection="upload-connection",
            )
        )

    assert project.create_called is False


def test_existing_dataset_is_not_replaced(monkeypatch, tmp_path):
    project = _FakeProject(has_existing_dataset=True)
    monkeypatch.setattr(datasets, "get_dss_client", lambda: _FakeClient(project))
    source_file = tmp_path / "source.csv"
    source_file.write_text("value\n1\n", encoding="utf-8")

    with pytest.raises(ValueError, match="Dataset 'existing' already exists"):
        asyncio.run(
            datasets.create_upload_dataset(
                "PROJECT",
                "existing",
                str(source_file),
                FakeContext(),
                connection="upload-connection",
            )
        )

    assert project.create_called is False


def test_new_upload_dataset_is_created_from_the_source_file(monkeypatch, tmp_path):
    project = _FakeProject(has_existing_dataset=False)
    monkeypatch.setattr(datasets, "get_dss_client", lambda: _FakeClient(project))
    source_file = tmp_path / "source.csv"
    source_file.write_text("value\n1\n", encoding="utf-8")

    result = json.loads(
        asyncio.run(
            datasets.create_upload_dataset(
                "PROJECT",
                "new-dataset",
                str(source_file),
                FakeContext(),
                connection="upload-connection",
            )
        )
    )

    assert project.create_called is True
    assert result == {
        "filename": "source.csv",
        "column_count": 1,
        "columns": {"columns": ["name", "type"], "rows": [["value", "bigint"]]},
    }


@pytest.mark.parametrize(
    "value",
    ["=1+1", "+1+1", "-1+1", "@SUM(A1:A2)", "\t=1+1", "\r=1+1", " =1+1"],
)
def test_csv_export_escapes_formula_prefixes_when_requested(value):
    assert _serialize_csv_value(value, spreadsheet_safe=True) == "'" + value


@pytest.mark.parametrize("value", ["plain text", "'already safe", 12, 1.5])
def test_csv_export_leaves_safe_values_unchanged(value):
    assert _serialize_csv_value(value, spreadsheet_safe=True) == value


def test_csv_export_serializes_null_as_empty_cell():
    assert _serialize_csv_value(None, spreadsheet_safe=True) == ""


def test_csv_export_preserves_raw_formula_text_by_default():
    assert _serialize_csv_value("=1+1", spreadsheet_safe=False) == "=1+1"


def test_csv_export_escapes_formula_text_when_requested():
    assert _serialize_csv_value("=1+1", spreadsheet_safe=True) == "'=1+1"
