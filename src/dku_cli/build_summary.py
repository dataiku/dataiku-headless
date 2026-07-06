"""Post-build verification summary for --wait build commands.

Prints one line per built dataset — `◆ Built X: N rows, M cols` — so a
successful build carries proof in the same turn instead of a bare exit 0.
Silent success (a build that "worked" but wrote 0 rows, or wrote an
all-string schema that breaks the next aggregation) is the single most
common agent failure mode; surfacing rows/cols at the moment of success
converts it into immediate, same-turn feedback.

Row count resolution ladder, cheapest-first and bounded:

1. COUNT_RECORDS metric, only if computed at/after the job started. (Most
   datasets do NOT auto-compute it on build — live-verified — so this tier
   usually only fires when dataset metrics are configured to auto-compute.
   A stale value would be a confident lie, so freshness is mandatory.)
2. SQL-backed datasets: `SELECT COUNT(*)` on the resolved physical table.
3. A capped streaming count (first ``_PROBE_CAP`` rows): exact for the
   typical agent-built dataset, "≥cap" for big ones — bounded transfer
   either way, and always distinguishes the critical 0-rows case.

Every step is best-effort: a verification error must never fail a build
that succeeded.
"""

from __future__ import annotations

import contextlib
import time
from typing import Any

from dku_cli.output import info, success, warn

# Clock-skew allowance when deciding whether a COUNT_RECORDS metric was
# computed by *this* build: client clock (job start capture) vs server
# clock (metric timestamp) can drift a little.
_FRESHNESS_SLACK_MS = 10_000


def snapshot_schemas(
    proj: Any, targets: list[tuple[str, str]]
) -> dict[str, dict[str, str]]:
    """Capture ``{dataset: {column: storage_type}}`` for DATASET targets, pre-build.

    Used to report what ``--auto-update-schema`` actually changed (added,
    removed, or retyped columns) so an auto-applied schema update is never
    silent — the failure mode Dataiku's docs warn against, and the reason
    schema update is "on by default but reported". Best-effort: a snapshot
    error must never affect the build.
    """
    snap: dict[str, dict[str, str]] = {}
    for ref, object_type in targets:
        if object_type != "DATASET":
            continue
        try:
            ds_def = proj.get_dataset(ref).get_definition()
            cols = ds_def.get("schema", {}).get("columns", [])
            snap[ref] = {c.get("name"): c.get("type") for c in cols}
        except Exception:
            pass  # Best-effort — a missing pre-build schema just skips the delta.
    return snap


def _emit_schema_delta(name: str, prev: dict[str, str], columns: list[dict]) -> None:
    """Report what auto-update changed vs the pre-build schema (silent if unchanged)."""
    cur = {c.get("name"): c.get("type") for c in columns}
    added = [c for c in cur if c not in prev]
    removed = [c for c in prev if c not in cur]
    retyped = [
        f"{c} {prev[c]}->{cur[c]}" for c in cur if c in prev and prev[c] != cur[c]
    ]
    if not (added or removed or retyped):
        return
    parts = []
    if added:
        parts.append("added " + ", ".join(added))
    if removed:
        parts.append("removed " + ", ".join(removed))
    if retyped:
        parts.append("retyped " + ", ".join(retyped))
    info(f"{name}: schema auto-updated ({'; '.join(parts)})")


def _fresh_metric_count(ds, job_start_ms: int) -> int | None:
    """Row count from the COUNT_RECORDS metric, only if computed by this build."""
    raw = ds.get_last_metric_values().get_raw()
    for metric in raw.get("metrics", []):
        if metric.get("metric", {}).get("id") != "records:COUNT_RECORDS":
            continue
        for point in metric.get("lastValues", []):
            computed = point.get("computed")
            if computed is None or computed < job_start_ms - _FRESHNESS_SLACK_MS:
                continue
            try:
                return int(point.get("value"))
            except (TypeError, ValueError):
                continue
    return None


def _sql_count(client, ds_def: dict, project_key: str) -> int | None:
    """Exact count via SELECT COUNT(*) for SQL-table-backed datasets."""
    # Late import: commands.dataset imports this module for `build --wait`.
    from dku_cli.commands.dataset import _resolve_sql_table

    resolved = _resolve_sql_table(ds_def, project_key)
    if resolved is None:
        return None
    connection, table = resolved
    result = client.sql_query(
        f"SELECT COUNT(*) AS n FROM {table}", connection=connection
    )
    rows = list(result.iter_rows())
    return int(rows[0][0]) if rows else 0


# Cap on the streaming-count fallback: exact counts below the cap (the
# typical agent-built dataset), "≥cap rows" above it — transfer stays bounded.
_PROBE_CAP = 10_000


def _probe_count(ds) -> tuple[int, bool]:
    """Stream up to _PROBE_CAP rows. Returns (count, is_exact)."""
    n = 0
    for _ in ds.iter_rows():
        n += 1
        if n >= _PROBE_CAP:
            return n, False
    return n, True


def _summarize_dataset(
    client,
    proj,
    project_key: str,
    name: str,
    job_start_ms: int,
    prev_cols: dict[str, str] | None = None,
) -> None:
    ds = proj.get_dataset(name)
    ds_def = ds.get_definition()
    columns = ds_def.get("schema", {}).get("columns", [])
    n_cols = len(columns)

    count: int | None = None
    exact = True
    with contextlib.suppress(Exception):
        count = _fresh_metric_count(ds, job_start_ms)
    if count is None:
        with contextlib.suppress(Exception):
            count = _sql_count(client, ds_def, project_key)
    if count is None:
        count, exact = _probe_count(ds)

    if count == 0:
        warn(
            f"Built {name}: 0 rows, {n_cols} cols — empty output. Check the "
            f"recipe's filter/join logic before building anything downstream: "
            f"dku dataset head {name} -P {project_key}"
        )
        return

    rows_part = f"{count} rows" if exact else f"≥{count} rows"
    success(f"Built {name}: {rows_part}, {n_cols} cols")

    if prev_cols is not None:
        _emit_schema_delta(name, prev_cols, columns)

    # The all-string schema is the recurring silent killer: upload/prepare
    # outputs typed entirely string break the next sum/avg/comparison. The
    # schema is already in hand, so the check is free.
    if n_cols >= 2 and all(c.get("type") == "string" for c in columns):
        info(
            f"All {n_cols} columns are typed string — numeric aggregations "
            f"will fail. Fix: dku dataset infer-types {name} --apply -P {project_key}"
        )


def emit_build_summary(
    client: Any,
    proj: Any,
    project_key: str,
    targets: list[tuple[str, str]],
    job_start_ms: int | None = None,
    prev_schemas: dict[str, dict[str, str]] | None = None,
) -> None:
    """Print a one-line rows/cols summary per built dataset target.

    Args:
        client: authenticated DSSClient (for the SQL count path).
        proj: DSSProject handle.
        project_key: resolved project key.
        targets: (ref, object_type) pairs as resolved at job-submit time;
            non-DATASET targets (folders, saved models) are skipped.
        job_start_ms: epoch ms the job was started, for metric freshness.
        prev_schemas: pre-build ``{dataset: {column: type}}`` from
            ``snapshot_schemas``; when given, a per-dataset schema-change line
            is printed so an auto-applied schema update is never silent.
    """
    start_ms = job_start_ms if job_start_ms is not None else int(time.time() * 1000)
    prev = prev_schemas or {}
    for ref, object_type in targets:
        if object_type != "DATASET":
            continue
        try:
            _summarize_dataset(
                client, proj, project_key, ref, start_ms, prev_cols=prev.get(ref)
            )
        except Exception as e:  # verification must never fail a successful build
            info(f"(could not verify {ref}: {e})")
