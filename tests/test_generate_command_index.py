"""Tests for scripts/generate_command_index.py.

The script is not an importable package, so load it from its path.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location(
    "generate_command_index", ROOT / "scripts" / "generate_command_index.py"
)
gen = importlib.util.module_from_spec(_SPEC)
assert _SPEC.loader is not None
_SPEC.loader.exec_module(gen)


def test_categories_cover_every_real_group():
    """Every group the live CLI exposes must be assigned to a category."""
    import typer.main

    from dku_cli.main import app
    from dku_cli.spec import full_index

    root = typer.main.get_command(app)
    index = full_index(root)
    gen._render(index)  # raises SystemExit if coverage is stale


def test_render_errors_on_uncategorized_group():
    with pytest.raises(SystemExit, match="Uncategorized"):
        gen._render({"unknown-group": {"help": "x", "commands": {}}})


def test_render_errors_on_stale_category_entry():
    index = {
        name: {"help": "x", "commands": {}}
        for _, names in gen.CATEGORIES
        for name in names
    }
    original = gen.CATEGORIES
    gen.CATEGORIES = original + [("Ghost", ["ghost-group"])]
    try:
        with pytest.raises(SystemExit, match="no longer exist"):
            gen._render(index)
    finally:
        gen.CATEGORIES = original


def test_render_output_matches_committed_file():
    """Fails if a command was added/changed without regenerating the index."""
    import typer.main

    from dku_cli.main import app
    from dku_cli.spec import full_index

    root = typer.main.get_command(app)
    index = full_index(root)
    rendered = gen._render(index)
    committed = gen.OUTPUT.read_text(encoding="utf-8")
    assert rendered == committed, (
        "references/command-index.md is stale — run "
        "`uv run python scripts/generate_command_index.py`"
    )
