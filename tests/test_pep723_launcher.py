# Copyright 2026 Dataiku
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

"""The PEP 723 server script must stay in lockstep with the project's metadata.

``bin/run_mcp.py`` declares its own dependencies inline so a harness can start
the server through ``uv run --quiet --locked --script`` instead of a pre-built environment. That
duplicated dependency list silently rots when ``pyproject.toml`` changes, and
the failure only surfaces at server startup on a user's machine — so pin it
down here instead.

The script pins exact versions while ``[project].dependencies`` stays a range,
so the two are checked for compatibility rather than equality: same package set,
and every pin has to satisfy the project's specifier for that package. Its
adjacent lockfile captures the full direct and transitive resolution.
"""

import importlib.metadata
import re
from pathlib import Path

from packaging.requirements import Requirement

SCRIPT = Path(__file__).resolve().parent.parent / "bin" / "run_mcp.py"
SCRIPT_LOCK = SCRIPT.with_suffix(".py.lock")


def _inline_metadata() -> str:
    """Return the PEP 723 block of the script with its comment prefix removed."""
    block = re.search(
        r"^# /// script$\n(.*?)^# ///$",
        SCRIPT.read_text(encoding="utf-8"),
        re.DOTALL | re.MULTILINE,
    )
    assert block, "bin/run_mcp.py lost its PEP 723 inline metadata block"
    return "\n".join(
        line.removeprefix("#").strip() for line in block.group(1).splitlines()
    )


def _inline_requirements() -> dict:
    array = re.search(r"dependencies\s*=\s*\[(.*?)\]", _inline_metadata(), re.DOTALL)
    assert array, "bin/run_mcp.py declares no inline dependencies"
    parsed = [Requirement(spec) for spec in re.findall(r'"([^"]+)"', array.group(1))]
    return {req.name.lower().replace("_", "-"): req for req in parsed}


def _project_requirements() -> dict:
    parsed = [
        Requirement(spec)
        for spec in importlib.metadata.requires("dataiku-headless") or []
    ]
    return {req.name.lower().replace("_", "-"): req for req in parsed}


def test_inline_dependencies_cover_the_same_packages():
    assert set(_inline_requirements()) == set(_project_requirements()), (
        "bin/run_mcp.py inline dependencies drifted from [project].dependencies "
        "in pyproject.toml"
    )


def test_inline_dependencies_are_pinned():
    for name, req in _inline_requirements().items():
        specifiers = list(req.specifier)
        assert len(specifiers) == 1 and specifiers[0].operator == "==", (
            f"{name} must be pinned to an exact version in bin/run_mcp.py: the "
            "script's direct dependency constraints must be explicit (got "
            f"{str(req.specifier) or 'no specifier'})"
        )


def test_script_lockfile_exists():
    assert SCRIPT_LOCK.is_file(), (
        "bin/run_mcp.py.lock is required because launchers use uv --locked; "
        "regenerate it with `uv lock --script bin/run_mcp.py`"
    )


def test_inline_pins_satisfy_project_constraints():
    project = _project_requirements()
    for name, req in _inline_requirements().items():
        pinned = str(req.specifier).removeprefix("==")
        assert project[name].specifier.contains(pinned, prereleases=True), (
            f"bin/run_mcp.py pins {name}=={pinned}, which violates "
            f"'{project[name]}' in pyproject.toml"
        )


def test_inline_requires_python_matches_project():
    inline = re.search(r'requires-python\s*=\s*"([^"]+)"', _inline_metadata())
    assert inline, "bin/run_mcp.py declares no inline requires-python"

    expected = importlib.metadata.metadata("dataiku-headless")["Requires-Python"]
    assert inline.group(1) == expected
