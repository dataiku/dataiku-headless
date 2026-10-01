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

"""HTTP requests must not invoke local filesystem upload helpers."""

import asyncio

import pytest

from dataiku_mcp.config import request
from dataiku_mcp.tools import managed_folders, project_libraries
from tests.utils.fakes import FakeContext


def _run_as_http(callback):
    token = request.bind_http_identity("https://idp.example", "alice")
    try:
        return callback()
    finally:
        request.reset_http_identity(token)


def test_http_managed_folder_upload_rejects_before_blocking_work(monkeypatch):
    monkeypatch.setattr(
        managed_folders,
        "run_blocking",
        lambda *args: pytest.fail("local upload must not start blocking work"),
    )

    with pytest.raises(
        ValueError, match="upload_file_to_managed_folder is unavailable"
    ):
        _run_as_http(
            lambda: asyncio.run(
                managed_folders.upload_file_to_managed_folder(
                    "PROJECT", "folder", "target.csv", FakeContext(), "/server/file.csv"
                )
            )
        )


def test_http_project_library_upload_rejects_before_local_read(monkeypatch):
    monkeypatch.setattr(
        project_libraries,
        "_read_local_file_bytes",
        lambda path: pytest.fail("local file helper must not run"),
    )

    with pytest.raises(ValueError, match="write_project_library_file is unavailable"):
        _run_as_http(
            lambda: asyncio.run(
                project_libraries.write_project_library_file(
                    "PROJECT", "/code.py", "/server/code.py", FakeContext()
                )
            )
        )
