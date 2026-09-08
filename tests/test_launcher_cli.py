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

"""The unified launcher requires an explicit, unambiguous transport."""

import runpy
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "bin" / "run_mcp.py"
SETUP_SKILL = (
    Path(__file__).resolve().parent.parent
    / "skills"
    / "dataiku-headless-setup"
    / "SKILL.md"
)


def _install_fake_launcher_modules(monkeypatch) -> list[tuple]:
    events = []
    dotenv_module = ModuleType("dotenv")
    dataiku_mcp_module = ModuleType("dataiku_mcp")

    def load_dotenv(path: Path, *, override: bool) -> None:
        events.append(("load_dotenv", path, override))

    dotenv_module.load_dotenv = load_dotenv
    dataiku_mcp_module.run_stdio_server = lambda path: events.append(
        ("run", "stdio", path)
    )
    dataiku_mcp_module.run_http_server = lambda path: events.append(
        ("run", "http", path)
    )
    monkeypatch.setitem(sys.modules, "dotenv", dotenv_module)
    monkeypatch.setitem(sys.modules, "dataiku_mcp", dataiku_mcp_module)
    return events


def test_launcher_loads_dotenv_before_importing_and_running_server(monkeypatch):
    events = _install_fake_launcher_modules(monkeypatch)
    monkeypatch.setattr(
        sys,
        "argv",
        [str(SCRIPT), "--transport", "http", "--settings-path", "/tmp/http.json"],
    )

    runpy.run_path(str(SCRIPT), run_name="__main__")

    assert events == [
        ("load_dotenv", SCRIPT.parent.parent / ".env", False),
        ("run", "http", Path("/tmp/http.json")),
    ]


def test_launcher_validates_arguments_before_loading_dotenv(monkeypatch):
    events = _install_fake_launcher_modules(monkeypatch)
    monkeypatch.setattr(sys, "argv", [str(SCRIPT)])

    with pytest.raises(SystemExit):
        runpy.run_path(str(SCRIPT), run_name="__main__")

    assert events == []


def test_launcher_requires_transport_before_importing_the_server():
    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2
    assert "--transport" in result.stderr


def test_launcher_passes_settings_path_to_stdio(monkeypatch):
    events = _install_fake_launcher_modules(monkeypatch)
    monkeypatch.setattr(
        sys,
        "argv",
        [str(SCRIPT), "--transport", "stdio", "--settings-path", "/tmp/stdio.json"],
    )

    runpy.run_path(str(SCRIPT), run_name="__main__")

    assert events == [
        ("load_dotenv", SCRIPT.parent.parent / ".env", False),
        ("run", "stdio", Path("/tmp/stdio.json")),
    ]


def test_launcher_help_does_not_import_the_server():
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--help"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "--transport" in result.stdout
    assert "--settings-path" in result.stdout


def test_setup_skill_warmup_commands_select_stdio_transport():
    commands = [
        line
        for line in SETUP_SKILL.read_text(encoding="utf-8").splitlines()
        if "uv run " in line and "run_mcp.py" in line
    ]

    assert len(commands) == 2
    assert all("--transport stdio" in command for command in commands)
