"""Bounds on project-library reads: tree walk and single-file content.

These never touch the network — ``get_dss_client`` is replaced by a fake library
whose folders/files are canned Python objects. The contract under test is that a
large or deep library tree and a large file are both bounded before returning.
"""

from __future__ import annotations

import asyncio
import json

from dataiku_mcp.tools import project_libraries


class FakeCtx:
    async def info(self, _message, **_kwargs):
        return None


class FakeItem:
    """A library node: ``children is None`` -> file, a list -> folder."""

    def __init__(self, name, children=None, content=""):
        self.name = name
        self.children = children
        self._content = content

    def list(self):
        return self.children or []

    def read(self):
        return self._content


class FakeGit:
    def list_libraries(self):
        # No external git references -> every item is "internal".
        return {}


class FakeLibrary:
    def __init__(self, root, files=None):
        self.root = root
        self._files = files or {}

    def get_folder(self, path):
        if path in self._files:
            raise Exception(f"{path} is a file")
        raise Exception(f"{path} not found")

    def get_file(self, path):
        if path not in self._files:
            raise Exception(f"{path} not found")
        return FakeItem(path.rsplit("/", 1)[-1], content=self._files[path])


class FakeProject:
    def __init__(self, library):
        self._library = library

    def get_library(self):
        return self._library

    def get_project_git(self):
        return FakeGit()


class FakeClient:
    def __init__(self, library):
        self._project = FakeProject(library)

    def get_project(self, _key):
        return self._project


def _bind(monkeypatch, library):
    monkeypatch.setattr(
        project_libraries, "get_dss_client", lambda: FakeClient(library)
    )


def run(coro):
    return asyncio.run(coro)


def _wide_tree(width):
    return FakeItem("root", children=[FakeItem(f"f{i}.py") for i in range(width)])


def _deep_tree(depth):
    def build(d):
        if d == 0:
            return [FakeItem("leaf.py")]
        return [FakeItem(f"sub{d}", children=build(d - 1))]

    return FakeItem("root", children=build(depth))


def test_list_is_bounded_by_max_items(monkeypatch):
    _bind(monkeypatch, FakeLibrary(_wide_tree(50)))

    res = json.loads(
        run(
            project_libraries.list_project_library(
                "PROJ", FakeCtx(), max_items=10
            )
        )
    )

    assert res["truncated"] is True
    assert res["max_items"] == 10
    assert len(res["items"]["rows"]) == 10


def test_list_is_bounded_by_max_depth(monkeypatch):
    _bind(monkeypatch, FakeLibrary(_deep_tree(10)))

    res = json.loads(
        run(
            project_libraries.list_project_library(
                "PROJ", FakeCtx(), max_depth=2
            )
        )
    )

    assert res["truncated"] is True
    assert res["max_depth"] == 2
    # No path deeper than the applied max_depth appears.
    depths = [row[0].count("/") for row in res["items"]["rows"]]
    assert max(depths) <= 2


def test_list_small_tree_is_not_truncated(monkeypatch):
    _bind(monkeypatch, FakeLibrary(_wide_tree(3)))

    res = json.loads(
        run(project_libraries.list_project_library("PROJ", FakeCtx()))
    )

    assert "truncated" not in res
    assert len(res["items"]["rows"]) == 3


def test_read_clips_a_large_file_on_a_byte_boundary(monkeypatch):
    big = "a" * 5000
    _bind(monkeypatch, FakeLibrary(FakeItem("root"), files={"/big.txt": big}))

    res = json.loads(
        run(
            project_libraries.read_project_library_file(
                "PROJ", "/big.txt", FakeCtx(), max_bytes=1000
            )
        )
    )

    assert res["truncated"] is True
    assert res["max_bytes"] == 1000
    assert res["bytes_total"] == 5000
    assert res["bytes_returned"] == 1000
    assert res["content"] == "a" * 1000


def test_read_small_file_is_returned_whole(monkeypatch):
    _bind(monkeypatch, FakeLibrary(FakeItem("root"), files={"/small.txt": "hello"}))

    res = json.loads(
        run(
            project_libraries.read_project_library_file(
                "PROJ", "/small.txt", FakeCtx()
            )
        )
    )

    assert res["content"] == "hello"
    assert "truncated" not in res
