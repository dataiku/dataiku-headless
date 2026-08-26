"""The unified launcher requires an explicit, unambiguous transport."""

import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "bin" / "run_mcp.py"


def test_launcher_requires_transport_before_importing_the_server():
    result = subprocess.run(
        [sys.executable, str(SCRIPT)], capture_output=True, text=True, check=False
    )

    assert result.returncode == 2
    assert "--transport" in result.stderr


def test_launcher_rejects_http_settings_for_stdio_before_importing_the_server():
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
    )

    assert result.returncode == 2
    assert "--http-settings requires --transport http" in result.stderr
