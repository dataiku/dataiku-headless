"""Independent, read-only reviewability audit of a project after a Cobuild build."""

from fastmcp import Context

from .. import mcp
from .utils.async_executor import run_blocking
from .utils.audit_engine import (
    build_payload,
    load_context,
    normalize_contract,
    run_bucket,
    run_contract_checks,
    validate_buckets,
)
from .utils.auth import get_dss_client
from .utils.serialization import compact_json
from .utils.validation import require_non_empty_string as _require_non_empty_string


@mcp.tool()
async def audit_project(
    project_key: str,
    ctx: Context,
    buckets: list[str] | None = None,
    contract: dict | None = None,
) -> str:
    """Run after a Cobuild delegation to independently verify the work: structure,
    documentation, evidence (real rows), maintainability. Pass
    contract={"outputs":[{"dataset":...,"columns":...,"min_rows":...}]} to assert
    what you delegated.

    Read-only: metrics are read from cached values (never recomputed) and row
    samples are bounded. Every failing check names the offending objects and a
    copy-paste fix (a Cobuild delegation prompt, or a named MCP tool such as
    build_datasets). ``buckets`` restricts which of structure/documentation/
    evidence/maintainability run (default all four). ``passed`` is true only when
    no ``fail``-severity check fails; warnings are advisory.
    """
    project_key = _require_non_empty_string(project_key, "project_key")
    selected = validate_buckets(buckets)
    normalized_contract = normalize_contract(contract) if contract is not None else None

    await ctx.info(
        f"Auditing project {project_key} "
        f"(buckets={', '.join(selected)}"
        f"{'; +contract' if normalized_contract is not None else ''})..."
    )

    proj = await run_blocking(lambda: get_dss_client().get_project(project_key))
    actx = await run_blocking(load_context, proj, project_key)

    checks = []
    for bucket in selected:
        await ctx.info(f"Auditing {bucket}...")
        checks += await run_blocking(run_bucket, actx, bucket)
    if normalized_contract is not None:
        await ctx.info("Checking delegated contract...")
        checks += await run_blocking(run_contract_checks, actx, normalized_contract)

    return compact_json(build_payload(project_key, checks, actx.inventory))
