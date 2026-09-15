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

import json
import os
import stat

import pytest

from dataiku_mcp.config import files


def test_read_json_object_reads_utf8_object(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text('{"description": "café"}', encoding="utf-8")

    assert files.read_json_object(path) == {"description": "café"}


def test_read_json_object_rejects_non_object(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text("[]", encoding="utf-8")

    with pytest.raises(ValueError, match="Settings file must be a JSON object"):
        files.read_json_object(path)


def test_write_json_atomic_creates_private_utf8_file(tmp_path):
    path = tmp_path / "nested" / "settings.json"

    files.write_json_atomic(path, {"description": "café"})

    assert json.loads(path.read_text(encoding="utf-8")) == {"description": "café"}
    assert path.read_bytes().endswith(b"\n")
    if os.name != "nt":
        assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_write_json_atomic_removes_temporary_file_when_replace_fails(
    tmp_path, monkeypatch
):
    path = tmp_path / "settings.json"

    def fail_replace(source, destination):
        raise OSError("replace failed")

    monkeypatch.setattr(files.os, "replace", fail_replace)

    with pytest.raises(OSError, match="replace failed"):
        files.write_json_atomic(path, {"value": 1})

    assert not path.exists()
    assert list(tmp_path.glob("config.*.tmp")) == []
