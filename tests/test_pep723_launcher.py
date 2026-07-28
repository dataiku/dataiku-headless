"""The PEP 723 launcher must stay in lockstep with the project's metadata.

``bin/run_mcp.py`` declares its own dependencies inline so a harness can start
the server with a throwaway uv (``npx -y @manzt/uv@… run --quiet …``) instead of
a pre-built environment. That duplicated dependency list silently rots when
``pyproject.toml`` changes, and the failure only surfaces at server startup on a
user's machine — so pin it down here instead.
"""

import importlib.metadata
import re
from pathlib import Path

LAUNCHER = Path(__file__).resolve().parent.parent / "bin" / "run_mcp.py"

# Runtime dependencies the launcher deliberately leaves out because serving MCP
# does not need them (``typer`` only backs the ``dataiku-headless`` CLI).
LAUNCHER_OMITS = {"typer"}


def _inline_metadata() -> str:
    """Return the PEP 723 block of the launcher with its comment prefix removed."""
    block = re.search(
        r"^# /// script$\n(.*?)^# ///$",
        LAUNCHER.read_text(encoding="utf-8"),
        re.DOTALL | re.MULTILINE,
    )
    assert block, "bin/run_mcp.py lost its PEP 723 inline metadata block"
    return "\n".join(
        line.removeprefix("#").strip() for line in block.group(1).splitlines()
    )


def _requirement_name(spec: str) -> str:
    return re.split(r"[\s<>=!~;\[]", spec, maxsplit=1)[0].lower().replace("_", "-")


def test_inline_dependencies_match_project_dependencies():
    array = re.search(r"dependencies\s*=\s*\[(.*?)\]", _inline_metadata(), re.DOTALL)
    assert array, "bin/run_mcp.py declares no inline dependencies"
    inline = set(re.findall(r'"([^"]+)"', array.group(1)))

    expected = {
        spec
        for spec in importlib.metadata.requires("dataiku-headless") or []
        if _requirement_name(spec) not in LAUNCHER_OMITS
    }

    assert inline == expected, (
        "bin/run_mcp.py inline dependencies drifted from [project].dependencies "
        "in pyproject.toml"
    )


def test_inline_requires_python_matches_project():
    inline = re.search(r'requires-python\s*=\s*"([^"]+)"', _inline_metadata())
    assert inline, "bin/run_mcp.py declares no inline requires-python"

    expected = importlib.metadata.metadata("dataiku-headless")["Requires-Python"]
    assert inline.group(1) == expected
