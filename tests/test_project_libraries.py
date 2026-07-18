"""Tests for the read bounds on the project-library tools.

Caller-supplied bounds (``max_items`` / ``max_depth`` / ``max_bytes``) must be
clamped down to the hard server ceilings, never bypassable, and the whole-file
read must truncate at the applied cap with correct metadata. A tiny fake DSS
library drives the real async tools via a patched ``get_dss_client``.
"""

import asyncio
import json

from dataiku_mcp.tools import project_libraries as pl


# --------------------------------------------------------------------------- #
# Fakes
# --------------------------------------------------------------------------- #
class FakeFile:
    def __init__(self, content):
        self._content = content

    def read(self, as_type=None):
        if as_type == "bytes":
            return self._content.encode("utf-8")
        return self._content


class FakeItem:
    """A node in the library tree: a file (children=None) or folder (children=list)."""

    def __init__(self, name, children=None):
        self.name = name
        self.children = children

    def list(self):
        return self.children or []


class FakeLibrary:
    def __init__(self, root, files):
        self.root = root
        self._files = files  # normalized path -> content

    def get_folder(self, path):
        # The tools only call this to test "is it a file?" — say yes for files.
        if path in self._files:
            raise Exception(f"{path} is a file")
        raise Exception(f"Folder not found: {path}")

    def get_file(self, path):
        if path in self._files:
            return FakeFile(self._files[path])
        raise Exception(f"File not found: {path}")


class FakeProject:
    def __init__(self, library):
        self._library = library

    def get_library(self):
        return self._library

    def get_project_git(self):
        # External-library config is intentionally unavailable here; source="all"
        # tolerates it (items are reported with source "unknown").
        raise Exception("no git support")


class FakeClient:
    def __init__(self, project):
        self._project = project

    def get_project(self, key):
        return self._project


class FakeCtx:
    def __init__(self):
        self.infos = []

    async def info(self, message, **kwargs):
        self.infos.append(message)


def _bind(monkeypatch, library):
    monkeypatch.setattr(pl, "get_dss_client", lambda: FakeClient(FakeProject(library)))


# --------------------------------------------------------------------------- #
# read_project_library_file: max_bytes clamp + truncation
# --------------------------------------------------------------------------- #
def test_read_clamps_max_bytes_to_ceiling_and_truncates(monkeypatch):
    # A file larger than the ceiling, with a caller asking for far more than the
    # ceiling allows.
    content = "a" * (pl.MAX_READ_MAX_BYTES + 50)
    library = FakeLibrary(FakeItem("", []), {"/big.txt": content})
    _bind(monkeypatch, library)

    result = asyncio.run(
        pl.read_project_library_file("PROJ", "/big.txt", FakeCtx(), max_bytes=5_000_000)
    )
    payload = json.loads(result)
    assert payload["truncated"] is True
    # Clamped down to the hard ceiling, not the requested 5_000_000.
    assert payload["max_bytes"] == pl.MAX_READ_MAX_BYTES
    assert payload["bytes_total"] == len(content.encode("utf-8"))
    assert payload["bytes_returned"] == pl.MAX_READ_MAX_BYTES
    assert len(payload["content"].encode("utf-8")) == pl.MAX_READ_MAX_BYTES


def test_read_small_file_is_not_truncated(monkeypatch):
    library = FakeLibrary(FakeItem("", []), {"/small.txt": "hello"})
    _bind(monkeypatch, library)
    payload = json.loads(
        asyncio.run(pl.read_project_library_file("PROJ", "/small.txt", FakeCtx()))
    )
    assert payload["content"] == "hello"
    assert "truncated" not in payload


# --------------------------------------------------------------------------- #
# list_project_library: max_items / max_depth clamp
# --------------------------------------------------------------------------- #
def test_list_clamps_max_items_to_ceiling(monkeypatch):
    # A flat root of more files than the ceiling allows.
    files = [FakeItem(f"f{i}.txt", None) for i in range(pl.MAX_LIST_MAX_ITEMS + 1)]
    root = FakeItem("", files)
    _bind(monkeypatch, FakeLibrary(root, {}))

    payload = json.loads(
        asyncio.run(
            pl.list_project_library("PROJ", FakeCtx(), max_items=1_000_000)
        )
    )
    assert payload["truncated"] is True
    # Reported bound is the clamped ceiling, not the requested 1_000_000.
    assert payload["max_items"] == pl.MAX_LIST_MAX_ITEMS
    assert len(payload["items"]["rows"]) == pl.MAX_LIST_MAX_ITEMS


def test_list_clamps_max_depth_to_ceiling(monkeypatch):
    # A chain deeper than the depth ceiling.
    node = FakeItem("leaf.txt", None)
    for i in range(pl.MAX_LIST_MAX_DEPTH + 10):
        node = FakeItem(f"d{i}", [node])
    root = FakeItem("", [node])
    _bind(monkeypatch, FakeLibrary(root, {}))

    payload = json.loads(
        asyncio.run(
            pl.list_project_library("PROJ", FakeCtx(), max_depth=1000, max_items=1_000_000)
        )
    )
    assert payload["truncated"] is True
    assert payload["max_depth"] == pl.MAX_LIST_MAX_DEPTH
