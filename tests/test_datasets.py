"""Tests for uploaded-dataset creation safeguards."""

import asyncio
import json

import pytest

from dataiku_mcp.tools import datasets
from tests.utils.fakes import FakeContext


class _FakeProject:
    def __init__(self, *, has_existing_dataset: bool):
        self.has_existing_dataset = has_existing_dataset
        self.create_called = False
        self.existing_dataset = _ExistingDataset()

    def list_datasets(self) -> list[dict]:
        return [{"name": "existing"}] if self.has_existing_dataset else []

    def create_upload_dataset(self, dataset_name: str, connection: str):
        self.create_called = True
        return _CreatedDataset()

    def get_dataset(self, dataset_name: str):
        assert dataset_name == "existing"
        return self.existing_dataset


class _ExistingDataset:
    def __init__(self):
        self.deleted = False

    def delete(self) -> None:
        self.deleted = True


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
    assert project.existing_dataset.deleted is False


def test_existing_dataset_is_replaced_when_overwrite_is_requested(
    monkeypatch, tmp_path
):
    project = _FakeProject(has_existing_dataset=True)
    monkeypatch.setattr(datasets, "get_dss_client", lambda: _FakeClient(project))
    source_file = tmp_path / "source.csv"
    source_file.write_text("value\n1\n", encoding="utf-8")

    asyncio.run(
        datasets.create_upload_dataset(
            "PROJECT",
            "existing",
            str(source_file),
            FakeContext(),
            connection="upload-connection",
            overwrite=True,
        )
    )

    assert project.existing_dataset.deleted is True
    assert project.create_called is True


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
