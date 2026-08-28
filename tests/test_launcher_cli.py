"""The unified launcher requires an explicit, unambiguous transport."""

import os
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "bin" / "run_mcp.py"


def _environment_with_invalid_stdio_config(tmp_path: Path) -> dict[str, str]:
    config_path = tmp_path / "invalid-config.json"
    config_path.write_text("{")
    return os.environ | {"DKU_CONFIG_FILE": str(config_path)}


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
