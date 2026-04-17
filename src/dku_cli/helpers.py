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


def resolve_semantic_model(project, sm_ref: str):
    """Resolve a semantic model by ID or name.

    Tries get_semantic_model(ref) first (by ID). If that raises NotFoundException,
    falls back to listing semantic models and matching by name.
    Returns a DSSSemanticModel handle.
    """
    try:
        sm = project.get_semantic_model(sm_ref)
        # Verify it exists by fetching definition (get_semantic_model is lazy)
        sm._get_definition()
        return sm
    except Exception as e:
        if (
            "not found" not in str(e).lower()
            and "NotFoundException" not in str(e)
            and "does not exist" not in str(e)
        ):
            raise
    # Fall back to name lookup
    models = project.list_semantic_models()
    for m in models:
        if m.get("name", "") == sm_ref:
            return project.get_semantic_model(m.get("id", m["id"]))
    from dku_cli.errors import exit_with_error

    sm_names = [f"  {m.get('id', '')} ({m.get('name', '')})" for m in models]
    exit_with_error(
        f"Semantic model '{sm_ref}' not found (checked as both ID and name).",
        code="not_found",
        details=[
            "Available semantic models:",
            *sm_names,
            "Use the semantic model ID (left column) or exact name.",
        ]
        if sm_names
        else [
            "No semantic models found in this project.",
            "Create one with: dku semantic-model create NAME -P PROJECT",
        ],
        status=3,
    )


def resolve_agent_review(project, review_ref: str):
    """Resolve an agent review by ID or name.

    Tries get_agent_review(ref) first (by ID). If that raises NotFoundException,
    falls back to listing reviews and matching by name.
    Returns a DSSAgentReview handle.
    """
    try:
        review = project.get_agent_review(review_ref)
        # get_agent_review returns a fully populated object (not lazy)
        return review
    except Exception as e:
        if (
            "not found" not in str(e).lower()
            and "NotFoundException" not in str(e)
            and "does not exist" not in str(e)
        ):
            raise
    # Fall back to name lookup
    reviews = project.list_agent_reviews()
    for r in reviews:
        if getattr(r, "name", "") == review_ref:
            return project.get_agent_review(r.id)
    from dku_cli.errors import exit_with_error

    review_names = [f"  {r.id} ({r.name})" for r in reviews]
    exit_with_error(
        f"Agent review '{review_ref}' not found (checked as both ID and name).",
        code="not_found",
        details=[
            "Available agent reviews:",
            *review_names,
            "Use the review ID (left column) or exact name.",
        ]
        if review_names
        else [
            "No agent reviews found in this project.",
            "Create one with: dku agent-review create NAME -P PROJECT",
        ],
        status=3,
    )


def resolve_folder(project, folder_ref: str):
    """Resolve a managed folder by ID or name.

    Tries get_managed_folder(ref) first (by ID). If that raises NotFoundException,
    falls back to listing managed folders and matching by name.
    Returns a DSSManagedFolder handle.
    """
    try:
        folder = project.get_managed_folder(folder_ref)
        # Verify it exists by fetching settings (get_managed_folder is lazy)
        folder.get_settings()
        return folder
    except Exception as e:
        if (
            "not found" not in str(e).lower()
            and "NotFoundException" not in str(e)
            and "does not exist" not in str(e)
        ):
            raise
    # Fall back to name lookup
    folders = project.list_managed_folders()
    for f in folders:
        if f.get("name", "") == folder_ref:
            return project.get_managed_folder(f.get("id"))
    from dku_cli.errors import exit_with_error

    folder_names = [f"  {f.get('id', '')} ({f.get('name', '')})" for f in folders]
    exit_with_error(
        f"Managed folder '{folder_ref}' not found (checked as both ID and name).",
        code="not_found",
        details=[
            "Available managed folders:",
            *folder_names,
            "Use the folder ID (left column) or exact name.",
        ]
        if folder_names
        else [
            "No managed folders found in this project.",
            "Create one with: dku folder create NAME -P PROJECT",
        ],
        status=3,
    )


def resolve_saved_model(project, model_ref: str):
    """Resolve a saved model by ID or name.

    Tries get_saved_model(ref).get_settings() first (by ID). If that raises,
    falls back to listing saved models and matching by name.
    Returns a DSSSavedModel handle.
    """
    try:
        model = project.get_saved_model(model_ref)
        model.get_settings()
        return model
    except Exception as e:
        if (
            "not found" not in str(e).lower()
            and "NotFoundException" not in str(e)
            and "does not exist" not in str(e)
        ):
            raise
    models = project.list_saved_models()
    for m in models:
        if m.get("name", "") == model_ref:
            return project.get_saved_model(m.get("id"))
    from dku_cli.errors import exit_with_error

    model_names = [f"  {m.get('id', '')} ({m.get('name', '')})" for m in models]
    exit_with_error(
        f"Saved model '{model_ref}' not found (checked as both ID and name).",
        code="not_found",
        details=[
            "Available saved models:",
            *model_names,
            "Use the saved model ID (left column) or exact name.",
        ]
        if model_names
        else [
            "No saved models found in this project.",
            "Train one with: dku ml create-prediction / create-clustering + train + deploy.",
        ],
        status=3,
    )


def resolve_recipe_input_ref(project, ref: str, explicit_type: str | None = None):
    """Resolve a recipe input ref to (kind, resolved_ref) where kind is one of
    "DATASET", "MANAGED_FOLDER", "SAVED_MODEL".

    If explicit_type is given, only that kind is tried (and resolution failure
    aborts via exit_with_error with prescriptive guidance).

    With no explicit_type, tries dataset → folder → saved model in order and
    returns the first match. If more than one kind matches, aborts with an
    ambiguity error so the caller can disambiguate via --type.
    """
    from dku_cli.errors import exit_with_error

    kind = (explicit_type or "").upper() or None

    def _try_dataset():
        # Dataset names are the canonical dataset ref — no ID/name distinction.
        try:
            project.get_dataset(ref).get_definition()
            return ref
        except Exception as e:
            if (
                "not found" in str(e).lower()
                or "NotFoundException" in str(e)
                or "does not exist" in str(e)
            ):
                return None
            raise

    def _try_folder():
        # Use list-match — folders have distinct ID/name; get_managed_folder is
        # lazy and get_settings() doesn't reliably raise on MagicMocks/tests.
        for f in project.list_managed_folders():
            if f.get("id") == ref or f.get("name", "") == ref:
                return f.get("id")
        return None

    def _try_model():
        for m in project.list_saved_models():
            if m.get("id") == ref or m.get("name", "") == ref:
                return m.get("id")
        return None

    if kind == "DATASET":
        resolved = _try_dataset()
        if resolved is None:
            exit_with_error(
                f"Dataset '{ref}' not found in this project.",
                code="not_found",
                details=[
                    "List datasets: dku dataset list -P PROJ",
                    "If this is a folder, pass --type MANAGED_FOLDER.",
                    "If this is a saved model, pass --type SAVED_MODEL.",
                ],
                status=3,
            )
        return "DATASET", resolved
    if kind == "MANAGED_FOLDER":
        resolved = _try_folder()
        if resolved is None:
            exit_with_error(
                f"Managed folder '{ref}' not found in this project.",
                code="not_found",
                details=["List folders: dku folder list -P PROJ"],
                status=3,
            )
        return "MANAGED_FOLDER", resolved
    if kind == "SAVED_MODEL":
        resolved = _try_model()
        if resolved is None:
            exit_with_error(
                f"Saved model '{ref}' not found in this project.",
                code="not_found",
                details=["List saved models: dku ml models -P PROJ"],
                status=3,
            )
        return "SAVED_MODEL", resolved

    # Auto-detect
    matches = []
    ds = _try_dataset()
    if ds is not None:
        matches.append(("DATASET", ds))
    fd = _try_folder()
    if fd is not None:
        matches.append(("MANAGED_FOLDER", fd))
    sm = _try_model()
    if sm is not None:
        matches.append(("SAVED_MODEL", sm))

    if not matches:
        exit_with_error(
            f"'{ref}' is not a dataset, managed folder, or saved model in this project.",
            code="not_found",
            details=[
                "List candidates:",
                "  dku dataset list -P PROJ",
                "  dku folder list -P PROJ",
                "  dku ml models -P PROJ",
                "Folders and saved models must be referenced by their ID (or unique name).",
            ],
            status=3,
        )
    if len(matches) > 1:
        exit_with_error(
            f"'{ref}' is ambiguous — matches multiple object types: "
            f"{', '.join(k for k, _ in matches)}.",
            code="ambiguous",
            details=[
                "Disambiguate with --type DATASET|MANAGED_FOLDER|SAVED_MODEL.",
            ],
            status=3,
        )
    return matches[0]


def update_taggable_metadata(
    settings,
    description: str | None = None,
    short_desc: str | None = None,
    tags: str | None = None,
) -> None:
    """Update description/short_desc/tags on a DSSTaggableObjectSettings and save.

    Works with Dashboard, Insight, SavedModel, and Agent settings objects
    that extend DSSTaggableObjectSettings.

    Args:
        settings: A DSSTaggableObjectSettings-based settings object with save().
        description: Long description text, or None to leave unchanged.
        short_desc: Short description text, or None to leave unchanged.
        tags: Comma-separated tag string, or None to leave unchanged.
    """
    if description is not None:
        settings.description = description
    if short_desc is not None:
        settings.short_description = short_desc
    if tags is not None:
        settings.tags = [t.strip() for t in tags.split(",") if t.strip()]
    settings.save()


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
