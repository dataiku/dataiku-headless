"""The unified launcher requires an explicit, unambiguous transport."""

import os
import runpy
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "bin" / "run_mcp.py"


def _environment_with_invalid_stdio_config(tmp_path: Path) -> dict[str, str]:
    config_path = tmp_path / "invalid-config.json"
    config_path.write_text("{")
    return os.environ | {"DKU_CONFIG_FILE": str(config_path)}


def _install_fake_launcher_modules(monkeypatch) -> list[tuple]:
    events = []
    dotenv_module = ModuleType("dotenv")
    dataiku_mcp_module = ModuleType("dataiku_mcp")

    def load_dotenv(path: Path, *, override: bool) -> None:
        events.append(("load_dotenv", path, override))

    dotenv_module.load_dotenv = load_dotenv
    dataiku_mcp_module.run_stdio_server = lambda: events.append(("run", "stdio"))
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
        [str(SCRIPT), "--transport", "http", "--http-settings", "/tmp/http.json"],
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


def test_launcher_requires_transport_before_importing_the_server(tmp_path):
    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        capture_output=True,
        text=True,
        check=False,
        env=_environment_with_invalid_stdio_config(tmp_path),
    )

    assert result.returncode == 2
    assert "--transport" in result.stderr


def test_launcher_rejects_http_settings_for_stdio_before_importing_the_server(tmp_path):
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--transport",
            "stdio",
            "--http-settings",
            "/tmp/http.json",
        ],
        capture_output=True,
        text=True,
        check=False,
        env=_environment_with_invalid_stdio_config(tmp_path),
    )

    assert result.returncode == 2
    assert "--http-settings requires --transport http" in result.stderr


def test_launcher_help_does_not_import_the_server(tmp_path):
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--help"],
        capture_output=True,
        text=True,
        check=False,
        env=_environment_with_invalid_stdio_config(tmp_path),
    )

    assert result.returncode == 0
    assert "--transport" in result.stdout
