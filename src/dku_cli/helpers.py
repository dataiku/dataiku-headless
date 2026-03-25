"""Shared helpers — eliminate duplication across commands."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import typer

import dataikuapi

from dku_cli.client import get_client
from dku_cli.config import get_default_project


def resolve_project(project: str | None) -> str:
    """Resolve project key: --project flag > DKU_PROJECT env > config default.

    Raises typer.BadParameter if nothing found.
    """
    if project:
        return project
    env_proj = os.environ.get("DKU_PROJECT")
    if env_proj:
        return env_proj
    cfg_proj = get_default_project()
    if cfg_proj:
        return cfg_proj
    raise typer.BadParameter(
        "No project specified. Use --project, DKU_PROJECT env var, or set a default."
    )


def get_client_from_ctx(ctx: typer.Context) -> dataikuapi.DSSClient:
    """Extract global opts from ctx.obj and return authenticated DSSClient."""
    opts = ctx.obj or {}
    return get_client(**opts)


def read_json_input(value: str | None) -> dict | None:
    """Parse JSON from: raw string, @file.json path, or stdin if value is '-'.

    Returns None if value is None.
    Raises typer.BadParameter on invalid JSON (clean error for agents/scripts).
    """
    if value is None:
        return None
    try:
        if value == "-":
            return json.load(sys.stdin)
        if value.startswith("@"):
            path = Path(value[1:])
            if not path.exists():
                raise typer.BadParameter(f"File not found: {path}")
            return json.loads(path.read_text())
        return json.loads(value)
    except json.JSONDecodeError as exc:
        source = (
            "stdin"
            if value == "-"
            else f"'{value[:80]}...'"
            if len(value) > 80
            else f"'{value}'"
        )
        raise typer.BadParameter(f"Invalid JSON from {source}: {exc}") from exc
