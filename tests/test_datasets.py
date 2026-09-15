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

from dataiku_mcp.config import request
from dataiku_mcp.tools import datasets
from dataiku_mcp.tools.datasets import _serialize_csv_value
from tests.utils.fakes import FakeContext


class _FakeProject:
    def __init__(self, *, has_existing_dataset: bool):
        self.has_existing_dataset = has_existing_dataset
        self.create_called = False
        self.created_dataset = None

    def list_datasets(self) -> list[dict]:
        return [{"name": "existing"}] if self.has_existing_dataset else []

    def create_upload_dataset(self, dataset_name: str, connection: str):
        self.create_called = True
        self.created_dataset = _CreatedDataset()
        return self.created_dataset


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
                FakeContext(),
                "upload-connection",
                filepath=str(tmp_path / "missing.csv"),
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
                FakeContext(),
                "upload-connection",
                filepath=str(source_file),
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
                FakeContext(),
                "upload-connection",
                filepath=str(source_file),
            )
        )
    )

    assert project.create_called is True
    assert result == {
        "filename": "source.csv",
        "column_count": 1,
        "columns": {"columns": ["name", "type"], "rows": [["value", "bigint"]]},
    }


def test_upload_dataset_accepts_bounded_rows(monkeypatch):
    project = _FakeProject(has_existing_dataset=False)
    monkeypatch.setattr(datasets, "get_dss_client", lambda: _FakeClient(project))

    result = json.loads(
        asyncio.run(
            datasets.create_upload_dataset(
                "PROJECT",
                "new-dataset",
                FakeContext(),
                "upload-connection",
                columns=["name", "active", "count", "missing"],
                rows=[["Ada", True, 3, None]],
            )
        )
    )

    assert project.created_dataset.uploaded == (
        "new-dataset.csv",
        b"name,active,count,missing\r\nAda,true,3,\r\n",
    )
    assert result["filename"] == "new-dataset.csv"


@pytest.mark.parametrize(
    ("columns", "rows", "message"),
    [
        ([], [], "'columns' must be a non-empty list"),
        (["value"], [["one", "two"]], r"'rows\[0\]' must contain exactly 1 values"),
        (["value"], [[{"not": "scalar"}]], "Upload rows only support scalar"),
    ],
)
def test_upload_dataset_validates_rows_before_creating_dataset(
    monkeypatch, columns, rows, message
):
    project = _FakeProject(has_existing_dataset=False)
    monkeypatch.setattr(datasets, "get_dss_client", lambda: _FakeClient(project))

    with pytest.raises(ValueError, match=message):
        asyncio.run(
            datasets.create_upload_dataset(
                "PROJECT",
                "new-dataset",
                FakeContext(),
                "upload-connection",
                columns=columns,
                rows=rows,
            )
        )

    assert project.create_called is False


def test_upload_dataset_rejects_more_than_maximum_rows(monkeypatch):
    project = _FakeProject(has_existing_dataset=False)
    monkeypatch.setattr(datasets, "get_dss_client", lambda: _FakeClient(project))

    with pytest.raises(ValueError, match="at most 10000 rows"):
        asyncio.run(
            datasets.create_upload_dataset(
                "PROJECT",
                "new-dataset",
                FakeContext(),
                "upload-connection",
                columns=["value"],
                rows=[["value"]] * 10_001,
            )
        )

    assert project.create_called is False


def test_upload_dataset_removes_temporary_file_when_row_validation_fails(monkeypatch):
    created_paths = []
    named_temporary_file = datasets.tempfile.NamedTemporaryFile

    def track_temporary_file(*args, **kwargs):
        temporary_file = named_temporary_file(*args, **kwargs)
        created_paths.append(temporary_file.name)
        return temporary_file

    monkeypatch.setattr(datasets.tempfile, "NamedTemporaryFile", track_temporary_file)

    with pytest.raises(ValueError, match=r"'rows\[0\]' must contain exactly 1 values"):
        datasets._write_upload_rows_to_temp_csv("dataset", ["value"], [["one", "two"]])

    assert created_paths
    assert all(not datasets.os.path.exists(path) for path in created_paths)


def test_http_upload_dataset_rejects_filepath_before_file_access(monkeypatch):
    token = request.bind_http_identity("https://idp.example", "alice")
    monkeypatch.setattr(
        datasets,
        "_create_uploaded_dataset_from_file",
        lambda **kwargs: pytest.fail("local file helper must not run"),
    )
    try:
        with pytest.raises(ValueError, match="filepath.*unavailable in HTTP mode"):
            asyncio.run(
                datasets.create_upload_dataset(
                    "PROJECT",
                    "new-dataset",
                    FakeContext(),
                    "upload-connection",
                    filepath="/server/secret.csv",
                )
            )
    finally:
        request.reset_http_identity(token)


def test_http_upload_dataset_accepts_rows(monkeypatch):
    project = _FakeProject(has_existing_dataset=False)
    monkeypatch.setattr(datasets, "get_dss_client", lambda: _FakeClient(project))
    token = request.bind_http_identity("https://idp.example", "alice")
    try:
        asyncio.run(
            datasets.create_upload_dataset(
                "PROJECT",
                "new-dataset",
                FakeContext(),
                "upload-connection",
                columns=["value"],
                rows=[["safe"]],
            )
        )
    finally:
        request.reset_http_identity(token)

    assert project.created_dataset.uploaded == ("new-dataset.csv", b"value\r\nsafe\r\n")


def test_http_export_dataset_rejects_before_path_resolution(monkeypatch):
    token = request.bind_http_identity("https://idp.example", "alice")
    monkeypatch.setattr(
        datasets.os.path,
        "realpath",
        lambda path: pytest.fail("path resolution must not run"),
    )
    try:
        with pytest.raises(
            ValueError, match="export_dataset is unavailable in HTTP mode"
        ):
            asyncio.run(
                datasets.export_dataset(
                    "PROJECT", "dataset", "/server/output.csv", FakeContext()
                )
            )
    finally:
        request.reset_http_identity(token)


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
