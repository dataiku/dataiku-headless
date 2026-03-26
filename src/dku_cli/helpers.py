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


def resolve_agent(project, agent_ref: str):
    """Resolve an agent by ID or name.

    Tries get_agent(ref) first (by ID). If that raises NotFoundException,
    falls back to listing agents and matching by name.
    Returns a DSSAgent handle.
    """
    try:
        agent = project.get_agent(agent_ref)
        # Verify it exists by fetching settings (get_agent is lazy)
        agent.get_settings()
        return agent
    except Exception as e:
        if (
            "not found" not in str(e).lower()
            and "NotFoundException" not in str(e)
            and "does not exist" not in str(e)
        ):
            raise
    # Fall back to name lookup
    agents = project.list_agents()
    for a in agents:
        if a.get("name", "") == agent_ref:
            return project.get_agent(a.get("id", a["id"]))
    from dku_cli.errors import exit_with_error

    agent_names = [f"  {a.get('id', '')} ({a.get('name', '')})" for a in agents]
    exit_with_error(
        f"Agent '{agent_ref}' not found (checked as both ID and name).",
        code="not_found",
        details=[
            "Available agents:",
            *agent_names,
            "Use the agent ID (left column) or exact name.",
        ]
        if agent_names
        else [
            "No agents found in this project.",
            "Create one with: dku agent create NAME -P PROJECT",
        ],
        status=3,
    )


def resolve_knowledge_bank(project, kb_ref: str):
    """Resolve a knowledge bank by ID or name.

    Tries get_knowledge_bank(ref) first (by ID). If that raises NotFoundException,
    falls back to listing knowledge banks and matching by name.
    Returns a DSSKnowledgeBank handle.
    """
    try:
        kb = project.get_knowledge_bank(kb_ref)
        # Verify it exists by fetching settings (get_knowledge_bank is lazy)
        kb.get_settings()
        return kb
    except Exception as e:
        if (
            "not found" not in str(e).lower()
            and "NotFoundException" not in str(e)
            and "does not exist" not in str(e)
        ):
            raise
    # Fall back to name lookup
    banks = project.list_knowledge_banks()
    for b in banks:
        if b.get("name", "") == kb_ref:
            return project.get_knowledge_bank(b.get("id", b["id"]))
    from dku_cli.errors import exit_with_error

    kb_names = [f"  {b.get('id', '')} ({b.get('name', '')})" for b in banks]
    exit_with_error(
        f"Knowledge bank '{kb_ref}' not found (checked as both ID and name).",
        code="not_found",
        details=[
            "Available knowledge banks:",
            *kb_names,
            "Use the knowledge bank ID (left column) or exact name.",
        ]
        if kb_names
        else [
            "No knowledge banks found in this project.",
            "Create one with: dku knowledge create NAME --embedding-llm LLM_ID -P PROJECT",
        ],
        status=3,
    )


def read_text_input(value: str) -> str:
    """Read text from: raw string, @file.txt path, or stdin if value is '-'.

    Same pattern as set-code but reusable for any text input (prompts, etc.).
    Raises typer.BadParameter on file-not-found.
    """
    if value == "-":
        return sys.stdin.read()
    if value.startswith("@"):
        path = Path(value[1:])
        if not path.exists():
            raise typer.BadParameter(f"File not found: {path}")
        return path.read_text()
    return value


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
