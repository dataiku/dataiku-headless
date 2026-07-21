"""Managed-folder upload requires explicit replacement intent."""

import asyncio
import json

import pytest

from dataiku_mcp.tools import managed_folders


class FakeCtx:
    async def info(self, message, **kwargs):
        return None


class FakeFolder:
    def __init__(self, items):
        self.items = items
        self.list_calls = 0
        self.put_calls = []

    def list_contents(self):
        self.list_calls += 1
        return {"items": self.items}

    def put_file(self, path, handle):
        self.put_calls.append((path, handle.read()))


class FakeProject:
    def __init__(self, folder):
        self.folder = folder

    def get_managed_folder(self, folder_id):
        return self.folder


class FakeClient:
    def __init__(self, folder):
        self.project = FakeProject(folder)

    def get_project(self, project_key):
        return self.project


def run(coro):
    return asyncio.run(coro)


def bind(monkeypatch, folder):
    monkeypatch.setattr(managed_folders, "get_dss_client", lambda: FakeClient(folder))


def test_default_refuses_existing_target_before_upload(monkeypatch, tmp_path):
    local = tmp_path / "payload.bin"
    local.write_bytes(b"new")
    folder = FakeFolder([{"path": "/target.bin"}])
    bind(monkeypatch, folder)

    with pytest.raises(FileExistsError, match="overwrite=true"):
        run(
            managed_folders.upload_file_to_managed_folder(
                "PROJ", "FOLDER", "/target.bin", FakeCtx(), str(local)
            )
        )

    assert folder.list_calls == 1
    assert folder.put_calls == []


def test_default_uploads_when_exact_target_is_absent(monkeypatch, tmp_path):
    local = tmp_path / "payload.bin"
    local.write_bytes(b"new")
    folder = FakeFolder([{"path": "/other.bin"}])
    bind(monkeypatch, folder)

    result = json.loads(
        run(
            managed_folders.upload_file_to_managed_folder(
                "PROJ", "FOLDER", "target.bin", FakeCtx(), str(local)
            )
        )
    )

    assert folder.list_calls == 1
    assert folder.put_calls == [("target.bin", b"new")]
    assert result["overwrite"] is False


def test_explicit_overwrite_skips_preflight_and_replaces(monkeypatch, tmp_path):
    local = tmp_path / "payload.bin"
    local.write_bytes(b"new")
    folder = FakeFolder([{"path": "/target.bin"}])
    bind(monkeypatch, folder)

    result = json.loads(
        run(
            managed_folders.upload_file_to_managed_folder(
                "PROJ",
                "FOLDER",
                "/target.bin",
                FakeCtx(),
                str(local),
                overwrite=True,
            )
        )
    )

    assert folder.list_calls == 0
    assert folder.put_calls == [("/target.bin", b"new")]
    assert result["overwrite"] is True


def test_unreadable_preflight_fails_closed(monkeypatch, tmp_path):
    local = tmp_path / "payload.bin"
    local.write_bytes(b"new")
    folder = FakeFolder([])
    folder.list_contents = lambda: {"items": None}
    bind(monkeypatch, folder)

    with pytest.raises(ValueError, match="Could not verify"):
        run(
            managed_folders.upload_file_to_managed_folder(
                "PROJ", "FOLDER", "target.bin", FakeCtx(), str(local)
            )
        )

    assert folder.put_calls == []


def test_folder_root_is_not_a_file_target(monkeypatch, tmp_path):
    local = tmp_path / "payload.bin"
    local.write_bytes(b"new")
    folder = FakeFolder([])
    bind(monkeypatch, folder)

    with pytest.raises(ValueError, match="folder root"):
        run(
            managed_folders.upload_file_to_managed_folder(
                "PROJ", "FOLDER", "/", FakeCtx(), str(local)
            )
        )

    assert folder.list_calls == 0
    assert folder.put_calls == []
