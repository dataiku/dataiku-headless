#!/usr/bin/env python3
"""Provision a plain-Python environment for the Dataiku MCP server and start it.

This is tier 2 of ``launcher.sh``: the path taken when the host has no uv but
does have a Python new enough for ``run_mcp.py``'s ``requires-python``. It builds
a venv under the plugin's data directory, pip-installs the dependencies from that
same PEP 723 block, and replaces itself with the server.

It does not look for uv or npx — ``launcher.sh`` owns tier selection, and being a
Python program, this file cannot run before a Python has already been found. Run
it directly only when you know the interpreter is suitable:

    python3 bin/launcher.py

Exiting with ``PROVISION_UNAVAILABLE`` (69) means "this runtime cannot host the
server" — too old an interpreter, no ``ensurepip``, an unwritable data directory.
``launcher.sh`` treats that status, and only that status, as permission to try
the next tier; any other non-zero status is the server's own and is passed
through untouched.

stdout belongs to the MCP JSON-RPC stream; everything this file prints goes to
stderr.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SERVER = HERE / "run_mcp.py"

# CLAUDE_PLUGIN_DATA is the harness-provided directory that survives plugin
# updates — the documented home for exactly this kind of generated venv. Outside
# a plugin install it falls back to a dot-dir beside the checkout.
PLUGIN_ROOT = Path(os.environ.get("CLAUDE_PLUGIN_ROOT") or HERE.parent)
DATA_DIR = Path(os.environ.get("CLAUDE_PLUGIN_DATA") or PLUGIN_ROOT / ".deps")
VENV_DIR = DATA_DIR / "venv"

PROVISION_UNAVAILABLE = 69  # EX_UNAVAILABLE; kept in sync with launcher.sh
FALLBACK_MIN_PYTHON = (3, 10)


def log(message: str) -> None:
    print(f"[dataiku-headless] {message}", file=sys.stderr)


def read_inline_metadata() -> str:
    """Return the PEP 723 block of the server script, comment prefix stripped."""
    block = re.search(
        r"^# /// script$\n(.*?)^# ///$",
        SERVER.read_text(encoding="utf-8"),
        re.DOTALL | re.MULTILINE,
    )
    if not block:
        return ""
    # tomllib would be the obvious parser, but it lands in 3.11 and this script
    # has to run on the 3.10 the server itself supports.
    return "\n".join(line.lstrip("#").strip() for line in block.group(1).splitlines())


def read_dependencies() -> list[str]:
    array = re.search(
        r"dependencies\s*=\s*\[(.*?)\]", read_inline_metadata(), re.DOTALL
    )
    return re.findall(r'"([^"]+)"', array.group(1)) if array else []


def read_min_python() -> tuple[int, int]:
    """Lowest Python the server accepts, from its inline ``requires-python``."""
    match = re.search(
        r'requires-python\s*=\s*">=\s*(\d+)\.(\d+)"', read_inline_metadata()
    )
    return (int(match.group(1)), int(match.group(2))) if match else FALLBACK_MIN_PYTHON


def venv_python() -> Path:
    bin_dir = "Scripts" if os.name == "nt" else "bin"
    return VENV_DIR / bin_dir / ("python.exe" if os.name == "nt" else "python")


def provision() -> Path | None:
    """Return an interpreter with the server's dependencies installed."""
    interpreter = venv_python()
    dependencies = read_dependencies()
    # Keyed on the dependency list, so bumping a pin reinstalls; kept inside the
    # venv, so a rebuilt venv is never mistaken for a provisioned one.
    marker = VENV_DIR / ".installed"
    stamp = "\n".join(dependencies)

    try:
        if not interpreter.exists():
            log("uv not found — creating a virtual environment (first run only)")
            VENV_DIR.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run(
                [sys.executable, "-m", "venv", str(VENV_DIR)],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
        if not marker.exists() or marker.read_text(encoding="utf-8") != stamp:
            log(f"installing {len(dependencies)} dependencies with pip")
            subprocess.run(
                [str(interpreter), "-m", "pip", "install", "--quiet", *dependencies],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
            marker.write_text(stamp, encoding="utf-8")
    except subprocess.CalledProcessError as error:
        detail = (error.stderr or b"").decode(errors="replace").strip().splitlines()
        log(f"python venv bootstrap failed: {detail[-1] if detail else error}")
        return None
    except OSError as error:
        log(f"python venv bootstrap failed: {error}")
        return None

    return interpreter


def main() -> int:
    minimum = read_min_python()
    if sys.version_info[:2] < minimum:
        log(
            f"{sys.executable} is Python {sys.version_info[0]}.{sys.version_info[1]}; "
            f"the server needs >= {minimum[0]}.{minimum[1]}"
        )
        return PROVISION_UNAVAILABLE

    interpreter = provision()
    if interpreter is None:
        return PROVISION_UNAVAILABLE

    log("starting via python venv")
    argv = [str(interpreter), str(SERVER)]
    try:
        if os.name == "nt":  # no exec semantics worth relying on; stay a parent
            return subprocess.run(argv).returncode
        os.execv(argv[0], argv)
    except OSError as error:
        # The venv exists but its interpreter will not start. Report it as an
        # unusable runtime so launcher.sh moves on instead of giving up.
        log(f"could not start {interpreter}: {error}")
        return PROVISION_UNAVAILABLE
    return 0


if __name__ == "__main__":
    sys.exit(main())
