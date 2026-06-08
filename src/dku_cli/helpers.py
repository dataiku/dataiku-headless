"""Shared helpers — eliminate duplication across commands."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import typer

import dataikuapi

from dku_cli.client import (
    get_client,
    get_govern_client,
    probe_node_type,
    resolve_auth,
    resolve_node_type,
)
from dku_cli.config import get_default_project


# Node types that support project-scoped commands (flow, datasets, recipes…).
PROJECT_NODE_TYPES = {"DESIGN", "AUTOMATION"}


def _has_auth_overrides(opts: dict) -> bool:
    """Whether the command is targeting auth that may differ from stored profile metadata."""
    return bool(
        opts.get("url")
        or opts.get("api_key")
        or os.environ.get("DKU_URL")
        or os.environ.get("DKU_API_KEY")
    )


def _resolve_target_node_type(opts: dict) -> str | None:
    """Resolve node type for the actual auth target, not just stored profile metadata."""
    profile = opts.get("profile")
    if not _has_auth_overrides(opts):
        return resolve_node_type(profile=profile)

    try:
        resolved_url, resolved_key = resolve_auth(
            url=opts.get("url"),
            api_key=opts.get("api_key"),
            profile=profile,
        )
    except Exception:
        return None

    probed = probe_node_type(resolved_url, resolved_key)
    if probed is not None:
        return probed
    return resolve_node_type(profile=profile)


def require_node_type(
    ctx: typer.Context | None,
    allowed: set[str],
    command_hint: str | None = None,
) -> None:
    """Refuse the command if the active profile is the wrong DSS node type.

    Emits a prescriptive error and exits non-zero when the profile's node type
    is known and not in ``allowed``. If the node type is unknown (legacy profile
    pre node-type tracking) we let the command proceed — the underlying API
    will still 404 but that is no worse than today.

    Args:
        ctx: Typer context — used to resolve the active profile.
        allowed: Uppercase node types accepted by the caller
            (e.g. ``{"DESIGN", "AUTOMATION"}`` or ``{"GOVERN"}``).
        command_hint: Optional alternate command to suggest
            (e.g. ``"dku govern artifact list"`` for Govern nodes).
    """
    opts = (ctx.obj if ctx is not None else {}) or {}
    nt = _resolve_target_node_type(opts)
    if nt is None or nt in allowed:
        return

    from dku_cli.errors import exit_with_error

    nice_allowed = ", ".join(sorted(allowed))
    details: list[str] = [
        f"Active profile node type: {nt}",
        f"This command requires: {nice_allowed}",
    ]
    if nt == "GOVERN":
        details.append("")
        details.append(
            "Govern nodes do not have projects, datasets, recipes, or flows."
        )
        details.append("Use the dedicated governance surface instead:")
        details.append(f"  {command_hint}" if command_hint else "  dku govern --help")
        details.append("")
        details.append("Or switch profile with: dku auth switch <design-profile>")
    else:
        details.append("")
        details.append(
            f"Switch profile with: dku auth switch <profile-on-{nice_allowed.lower()}-node>"
        )
        if command_hint:
            details.append(f"Or try: {command_hint}")

    exit_with_error(
        f"Command not available on {nt} nodes.",
        code="wrong_node_type",
        details=details,
        status=4,
    )


def resolve_project(project: str | None, ctx: typer.Context | None = None) -> str:
    """Resolve project key: --project flag > DKU_PROJECT env > config default.

    Also enforces the node-type guard: project-scoped commands require a
    DESIGN or AUTOMATION node. Passing ``ctx`` lets the guard read the
    active profile; legacy callers that omit ``ctx`` still get the env/flag
    resolution (backwards compatible).

    Raises typer.BadParameter if nothing found.
    """
    # Node-type guard runs before the project lookup so agents see the real
    # problem ("wrong node type") instead of a spurious "no project set".
    if ctx is not None:
        require_node_type(ctx, PROJECT_NODE_TYPES)

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


_CLIENT_OPTS = ("url", "api_key", "profile")


def get_client_from_ctx(
    ctx: typer.Context,
    *,
    allowed_node_types: set[str] | None = None,
) -> dataikuapi.DSSClient:
    """Extract global opts from ctx.obj and return authenticated DSSClient.

    By default refuses GOVERN nodes with a prescriptive error — GOVERN has no
    projects, datasets, or recipes and a raw 404 from the API tells agents
    nothing useful. Cross-node commands (whoami, user, group, admin/logs)
    opt into broader node support via ``allowed_node_types``.

    Args:
        ctx: Typer context — provides global opts (url, api_key, profile).
        allowed_node_types: Override the default (``PROJECT_NODE_TYPES``).
            Pass ``None`` or ``{"DESIGN","AUTOMATION","GOVERN","DEPLOYER","API"}``
            for commands that work on every node type. Pass a narrower set
            (e.g. ``{"DESIGN","AUTOMATION"}``) to restrict further.

    Filters to the keys `get_client()` accepts so non-auth globals
    (e.g. `dangerous`) in ctx.obj don't crash the client constructor.
    """
    if allowed_node_types is None:
        allowed_node_types = PROJECT_NODE_TYPES
    require_node_type(ctx, allowed_node_types)
    opts = ctx.obj or {}
    return get_client(**{k: opts[k] for k in _CLIENT_OPTS if k in opts})


# Commands that work on every DSS node type (whoami, admin instance-info, etc).
ALL_NODE_TYPES = {"DESIGN", "AUTOMATION", "GOVERN", "DEPLOYER", "API"}


def get_govern_client_from_ctx(ctx: typer.Context):
    """Extract global opts from ctx.obj and return authenticated GovernClient.

    Also enforces that the active profile is a GOVERN node — commands under
    ``dku govern`` only make sense against a Govern node.
    """
    require_node_type(ctx, {"GOVERN"})
    opts = ctx.obj or {}
    return get_govern_client(**{k: opts[k] for k in _CLIENT_OPTS if k in opts})


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


def resolve_build_output_types(project, refs):
    """Map build output refs to (resolved_ref, object_type) for the job builder.

    Recipe outputs (``get_flat_output_refs()``) and ``dku job run --target`` give
    bare refs. ``JobDefinitionBuilder.with_output`` defaults ``object_type`` to
    DATASET server-side, so managed-folder / saved-model / knowledge-bank /
    evaluation-store outputs error with "dataset <id> does not exist". Classify
    each ref by checking the project's folders, saved models, knowledge banks
    and evaluation stores once, resolving names to IDs where needed.

    Cross-project refs ("PROJECT.id") are left as-is and treated as DATASET
    (recipe outputs are always local; cross-project build targets are uncommon
    and DATASET is the safe default).

    :returns: list of (resolved_ref, object_type) tuples, one per input ref.
    """
    # Folders + saved models are cheap single list calls and are needed to tell
    # a dataset apart from them, so classify against those first (preserving the
    # original folder → saved-model precedence). A ref confirmed to be a plain
    # dataset then short-circuits to DATASET, so the two expensive lookups
    # (knowledge banks + evaluation stores) are deferred and never issued on the
    # hot path where every output is a folder/model/dataset (e.g.
    # `dku job run --target my_dataset`). Resolution precedence is unchanged:
    # folders → saved models → knowledge banks → evaluation stores → DATASET
    # (datasets, KBs and eval stores live in disjoint namespaces, so the
    # dataset short-circuit cannot steal a ref that would have been a KB/MES).
    folders = project.list_managed_folders()
    models = project.list_saved_models()
    folder_ids = {f.get("id") for f in folders}
    folder_by_name = {f.get("name"): f.get("id") for f in folders if f.get("name")}
    model_ids = {m.get("id") for m in models}
    model_by_name = {m.get("name"): m.get("id") for m in models if m.get("name")}

    _deferred: dict[str, tuple[set, dict]] = {}

    def _datasets() -> tuple[set, dict]:
        # Cheap single list call used only to short-circuit a known dataset to
        # DATASET before paying the KB/eval-store round-trips. Tolerate older
        # DSS / failures by treating the project as having no listable datasets,
        # which falls through to the KB → MES → DATASET path (original behavior).
        if "ds" not in _deferred:
            try:
                datasets = project.list_datasets()
                ids = {d.get("name") for d in datasets if d.get("name")}
            except Exception:
                ids = set()
            _deferred["ds"] = (ids, {})
        return _deferred["ds"]

    def _kbs() -> tuple[set, dict]:
        # Knowledge banks build as RETRIEVABLE_KNOWLEDGE — the exact type
        # DSSKnowledgeBank.build() posts. Without this, embed recipe outputs
        # fall through to DATASET and the job fails with the misleading
        # "dataset <id> does not exist". The endpoint may be absent on older
        # DSS — treat lookup failures as "project has none".
        if "kb" not in _deferred:
            try:
                kbs = project.list_knowledge_banks()  # listitems extend dict
                ids = {kb.get("id") for kb in kbs}
                by_name = {kb.get("name"): kb.get("id") for kb in kbs if kb.get("name")}
            except Exception:
                ids, by_name = set(), {}
            _deferred["kb"] = (ids, by_name)
        return _deferred["kb"]

    def _stores() -> tuple[set, dict]:
        # Evaluation stores build as MODEL_EVALUATION_STORE — the type
        # DSSEvaluationStore.build() posts; same DATASET-fallthrough hazard as
        # knowledge banks. Quirk: public list_evaluation_stores() returns
        # handles whose names need one get_settings() call each (N+1); the raw
        # fetch returns {id, name, mesFlavor} dicts in a single call. The
        # endpoint may be absent on older DSS — tolerate failures.
        if "mes" not in _deferred:
            try:
                stores = project._fetch_evaluation_stores(flavor=None)
                ids = {s.get("id") for s in stores}
                by_name = {s.get("name"): s.get("id") for s in stores if s.get("name")}
            except Exception:
                ids, by_name = set(), {}
            _deferred["mes"] = (ids, by_name)
        return _deferred["mes"]

    resolved: list[tuple[str, str]] = []
    for ref in refs:
        if ref in folder_ids:
            resolved.append((ref, "MANAGED_FOLDER"))
            continue
        if ref in folder_by_name:
            resolved.append((folder_by_name[ref], "MANAGED_FOLDER"))
            continue
        if ref in model_ids:
            resolved.append((ref, "SAVED_MODEL"))
            continue
        if ref in model_by_name:
            resolved.append((model_by_name[ref], "SAVED_MODEL"))
            continue
        ds_ids, _ = _datasets()
        if ref in ds_ids:
            # Known dataset — short-circuit before the expensive KB/MES probes.
            resolved.append((ref, "DATASET"))
            continue
        kb_ids, kb_by_name = _kbs()
        if ref in kb_ids:
            resolved.append((ref, "RETRIEVABLE_KNOWLEDGE"))
            continue
        if ref in kb_by_name:
            resolved.append((kb_by_name[ref], "RETRIEVABLE_KNOWLEDGE"))
            continue
        mes_ids, mes_by_name = _stores()
        if ref in mes_ids:
            resolved.append((ref, "MODEL_EVALUATION_STORE"))
            continue
        if ref in mes_by_name:
            resolved.append((mes_by_name[ref], "MODEL_EVALUATION_STORE"))
            continue
        resolved.append((ref, "DATASET"))
    return resolved


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
