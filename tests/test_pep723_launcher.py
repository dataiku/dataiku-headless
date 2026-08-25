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

import pytest
from packaging.requirements import Requirement

SCRIPTS = [
    Path(__file__).resolve().parent.parent / "bin" / "run_mcp.py",
    Path(__file__).resolve().parent.parent / "bin" / "run_http_mcp.py",
]


def _inline_metadata(script: Path) -> str:
    """Return the PEP 723 block of the script with its comment prefix removed."""
    block = re.search(
        r"^# /// script$\n(.*?)^# ///$",
        script.read_text(encoding="utf-8"),
        re.DOTALL | re.MULTILINE,
    )
    assert block, f"{script} lost its PEP 723 inline metadata block"
    return "\n".join(
        line.removeprefix("#").strip() for line in block.group(1).splitlines()
    )


def _inline_requirements(script: Path) -> dict:
    array = re.search(
        r"dependencies\s*=\s*\[(.*?)\]", _inline_metadata(script), re.DOTALL
    )
    assert array, f"{script} declares no inline dependencies"
    parsed = [Requirement(spec) for spec in re.findall(r'"([^"]+)"', array.group(1))]
    return {req.name.lower().replace("_", "-"): req for req in parsed}


def _project_requirements() -> dict:
    parsed = [
        Requirement(spec)
        for spec in importlib.metadata.requires("dataiku-headless") or []
    ]
    return {req.name.lower().replace("_", "-"): req for req in parsed}


@pytest.mark.parametrize("script", SCRIPTS)
def test_inline_dependencies_cover_the_same_packages(script):
    assert set(_inline_requirements(script)) == set(_project_requirements()), (
        f"{script} inline dependencies drifted from [project].dependencies "
        "in pyproject.toml"
    )


@pytest.mark.parametrize("script", SCRIPTS)
def test_inline_dependencies_are_pinned(script):
    for name, req in _inline_requirements(script).items():
        specifiers = list(req.specifier)
        assert len(specifiers) == 1 and specifiers[0].operator == "==", (
            f"{name} must be pinned to an exact version in {script}: the "
            "script's direct dependency constraints must be explicit (got "
            f"{str(req.specifier) or 'no specifier'})"
        )


@pytest.mark.parametrize("script", SCRIPTS)
def test_script_lockfile_exists(script):
    assert script.with_suffix(".py.lock").is_file(), (
        f"{script}.lock is required because launchers use uv --locked; "
        "regenerate it with `uv lock --script bin/run_mcp.py`"
    )


@pytest.mark.parametrize("script", SCRIPTS)
def test_inline_pins_satisfy_project_constraints(script):
    project = _project_requirements()
    for name, req in _inline_requirements(script).items():
        pinned = str(req.specifier).removeprefix("==")
        assert project[name].specifier.contains(pinned, prereleases=True), (
            f"bin/run_mcp.py pins {name}=={pinned}, which violates "
            f"'{project[name]}' in pyproject.toml"
        )


@pytest.mark.parametrize("script", SCRIPTS)
def test_inline_requires_python_matches_project(script):
    inline = re.search(r'requires-python\s*=\s*"([^"]+)"', _inline_metadata(script))
    assert inline, f"{script} declares no inline requires-python"

    expected = importlib.metadata.metadata("dataiku-headless")["Requires-Python"]
    assert inline.group(1) == expected
