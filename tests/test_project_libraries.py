"""Project-library reads stay bounded, explicit, and safe under hostile input."""

import asyncio
import json

import pytest

from dataiku_mcp.tools import project_libraries


class FakeCtx:
    async def info(self, message, **kwargs):
        return None


class FakeFile:
    children = None

    def __init__(self, name, content=b""):
        self.name = name
        self.content = content

    def read(self, as_type="str"):
        if as_type == "bytes":
            return self.content
        return self.content.decode("utf-8")


class FakeFolder:
    def __init__(self, name, children=None):
        self.name = name
        self.children = list(children or [])

    def list(self):
        return sorted(self.children, key=lambda item: item.name)


class FakeLibrary:
    def __init__(self, children):
        self.root = FakeFolder("/", children)

    def _resolve(self, path):
        if path == "/":
            return self.root
        node = self.root
        for component in path.strip("/").split("/"):
            if node.children is None:
                return None
            node = next(
                (item for item in node.children if item.name == component),
                None,
            )
            if node is None:
                return None
        return node

    def get_folder(self, path):
        node = self._resolve(path)
        if node is not None and node.children is None:
            raise ValueError(f"{path} is a file")
        return node

    def get_file(self, path):
        node = self._resolve(path)
        if node is not None and node.children is not None:
            raise ValueError(f"{path} is a folder")
        return node


class FakeProjectGit:
    def __init__(self, references):
        self.references = references

    def list_libraries(self):
        return {"gitReferences": self.references}


class FakeProject:
    def __init__(self, library, references=None):
        self.library = library
        self.references = references or {}

    def get_library(self):
        return self.library

    def get_project_git(self):
        return FakeProjectGit(self.references)


class FakeClient:
    def __init__(self, project):
        self.project = project

    def get_project(self, project_key):
        return self.project


def run(coro):
    return asyncio.run(coro)


def bind(monkeypatch, children, references=None):
    project = FakeProject(FakeLibrary(children), references)
    monkeypatch.setattr(
        project_libraries,
        "get_dss_client",
        lambda: FakeClient(project),
    )


def test_source_filter_cannot_bypass_visited_node_limit(monkeypatch):
    external = FakeFolder(
        "external",
        [FakeFile(f"file-{index}.py", b"pass") for index in range(5)],
    )
    bind(
        monkeypatch,
        [external, FakeFile("internal.py", b"pass")],
        references={"external": {"remote": "origin"}},
    )

    result = json.loads(
        run(
            project_libraries.list_project_library(
                "PROJ",
                FakeCtx(),
                source="internal",
                max_visited_nodes=3,
            )
        )
    )

    assert result["visited_nodes"] == 3
    assert result["items"]["rows"] == []
    assert result["truncated"] is True
    assert result["truncation_reasons"] == ["max_visited_nodes"]


def test_list_reports_depth_truncation(monkeypatch):
    bind(
        monkeypatch,
        [FakeFolder("one", [FakeFolder("two", [FakeFile("deep.py", b"pass")])])],
    )

    result = json.loads(
        run(
            project_libraries.list_project_library(
                "PROJ", FakeCtx(), max_depth=1
            )
        )
    )

    assert result["items"]["rows"] == [["/one", "folder", "internal", None]]
    assert result["truncation_reasons"] == ["max_depth"]


def test_read_clips_on_a_utf8_boundary_and_reports_full_size(monkeypatch):
    bind(monkeypatch, [FakeFile("unicode.txt", "éZ".encode())])

    result = json.loads(
        run(
            project_libraries.read_project_library_file(
                "PROJ", "/unicode.txt", FakeCtx(), max_bytes=2
            )
        )
    )

    assert result == {
        "path": "/unicode.txt",
        "content": "é",
        "size_bytes": 3,
        "returned_bytes": 2,
        "truncated": True,
    }


def test_read_rejects_malformed_utf8(monkeypatch):
    bind(monkeypatch, [FakeFile("binary.dat", b"\xff")])

    with pytest.raises(ValueError, match="not valid UTF-8"):
        run(
            project_libraries.read_project_library_file(
                "PROJ", "/binary.dat", FakeCtx()
            )
        )


def test_search_reports_every_reason_results_are_incomplete(monkeypatch):
    bind(
        monkeypatch,
        [
            FakeFile("a.txt", b"x" * 20),
            FakeFile("b.txt", b"needle"),
            FakeFile("c.txt", b"needle"),
        ],
    )

    result = json.loads(
        run(
            project_libraries.search_project_library(
                "PROJ",
                "needle",
                FakeCtx(),
                max_files=2,
                max_file_bytes=10,
            )
        )
    )

    assert result["matches"]["rows"] == [["/b.txt", 1, "needle"]]
    assert result["files_attempted"] == 2
    assert result["files_read"] == 2
    assert result["files_searched"] == 1
    assert result["skipped_files"]["oversized"] == 1
    assert result["truncated"] is True
    assert result["truncation_reasons"] == ["max_files", "oversized_files"]


def test_regex_timeout_stops_search_and_is_visible(monkeypatch):
    bind(monkeypatch, [FakeFile("code.py", b"some text")])

    class TimeoutPattern:
        def search(self, value, timeout):
            raise TimeoutError("regex timed out")

    monkeypatch.setattr(project_libraries.regex, "compile", lambda *args, **kwargs: TimeoutPattern())

    result = json.loads(
        run(
            project_libraries.search_project_library(
                "PROJ", ".*", FakeCtx(), is_regex=True
            )
        )
    )

    assert result["matches"]["rows"] == []
    assert result["truncated"] is True
    assert result["truncation_reasons"] == ["regex_timeout"]


def test_python_validation_is_bounded_and_reports_syntax_failure(monkeypatch):
    bind(monkeypatch, [])

    result = json.loads(
        run(
            project_libraries.validate_project_library_file(
                "PROJ", "/broken.py", FakeCtx(), content="def broken("
            )
        )
    )
    assert result["is_valid"] is False
    assert result["syntax_error"]["line"] == 1

    with pytest.raises(ValueError, match="exceeds the 5-byte"):
        run(
            project_libraries.validate_project_library_file(
                "PROJ", "/large.py", FakeCtx(), content="123456", max_bytes=5
            )
        )


def test_final_library_response_has_a_hard_serialized_ceiling(monkeypatch):
    bind(
        monkeypatch,
        [FakeFile(f"{'long' * 20}-{index}.txt", b"text") for index in range(20)],
    )
    monkeypatch.setattr(project_libraries, "_MAX_RESPONSE_BYTES", 500)

    raw = run(project_libraries.list_project_library("PROJ", FakeCtx()))
    result = json.loads(raw)

    assert len(raw.encode("utf-8")) <= 500
    assert result["truncated"] is True
    assert result["truncation_reason"] == "max_response_bytes"
