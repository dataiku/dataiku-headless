"""Independent, read-only reviewability audit of a project after a Cobuild build."""

from fastmcp import Context

from .. import mcp
from .utils.async_executor import run_blocking
from .utils.audit_engine import (
    MAX_AUDIT_IDENTIFIER_CHARS,
    build_payload,
    compact_audit_payload,
    load_context,
    normalize_contract,
    run_bucket,
    run_contract_checks,
    validate_buckets,
)
from .utils.auth import get_dss_client
from .utils.validation import require_non_empty_string as _require_non_empty_string


@mcp.tool()
async def audit_project(
    project_key: str,
    ctx: Context,
    buckets: list[str] | None = None,
    contract: dict | None = None,
) -> str:
    """Run after a Cobuild delegation as a deterministic finish gate — not an
    oracle that proves the build is correct — with a flow-level audit (datasets,
    recipes, zones, wiki): structure, documentation, evidence (real rows). It
    inspects only those flow-level objects — it does not audit scenarios, code
    envs, connections, ML models, or other project settings. Pass
    contract={"outputs":[{"dataset":...,"columns":...,"min_rows":...}]} to assert
    what you delegated. Contract columns/types check a *required subset* of the
    saved schema (the listed columns must exist / match; extra columns never
    fail it), min_rows uses the cached — possibly stale — record-count metric,
    and not_blank checks at most 100 sampled rows; a not_blank check with no
    sample rows errors rather than passing vacuously.

    Read-only: metrics are read from cached values (never recomputed) and row
    samples are bounded. Every failing check names the offending objects and a
    copy-paste fix (a Cobuild delegation prompt, or a named MCP tool such as
    build_datasets). ``buckets`` restricts which of structure/documentation/
    evidence run (default all three). Only FAIL-severity checks fail closed:
    ``passed`` is true only when no ``fail``-severity check fails and no
    FAIL-severity check errored (unreadable evidence marks the payload
    ``incomplete``). WARN-severity checks are advisory — one that cannot run
    ``skip``s (surfaced, never blocking). The payload's ``scope`` field restates
    this flow-level scope. Reviewability conventions (descriptions, zones, empty
    zones, and zero-row graph leaves) are warnings; only DSS consistency errors
    and an explicit caller contract block ``passed``.
    """
    project_key = _require_non_empty_string(project_key, "project_key")
    if len(project_key) > MAX_AUDIT_IDENTIFIER_CHARS:
        raise ValueError(
            f"'project_key' must be <= {MAX_AUDIT_IDENTIFIER_CHARS} characters"
        )
    selected = validate_buckets(buckets)
    normalized_contract = normalize_contract(contract) if contract is not None else None
    client = get_dss_client()

    await ctx.info(
        f"Auditing project {project_key} "
        f"(buckets={', '.join(selected)}"
        f"{'; +contract' if normalized_contract is not None else ''})..."
    )

    try:
        proj = await run_blocking(lambda: client.get_project(project_key))
        actx = await run_blocking(load_context, proj, project_key)
    except Exception as exc:
        raise ValueError(
            f"Could not load audit context for project '{project_key}' "
            f"({type(exc).__name__})"
        ) from exc

    checks = []
    for bucket in selected:
        await ctx.info(f"Auditing {bucket}...")
        checks += await run_blocking(run_bucket, actx, bucket)
    if normalized_contract is not None:
        await ctx.info("Checking delegated contract...")
        checks += await run_blocking(run_contract_checks, actx, normalized_contract)

    return compact_audit_payload(build_payload(project_key, checks, actx.inventory))
