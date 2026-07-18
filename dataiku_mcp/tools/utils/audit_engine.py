"""Read-only project reviewability audit — the finish gate after a Cobuild build.

This is a harness-independent port of the ``dku`` CLI ``project-audit`` engine.
It answers one question: can an SME open this DSS project cold, follow the flow,
see what changed, and trust the result?

Everything here is read-only. Metrics are read from their *cached* values
(never recomputed); row samples are bounded to :data:`MAX_SAMPLE_ROWS`; the only
heavy operation (the flow-consistency check) is time-bounded. Because that check
is FAIL-severity, a failure or timeout degrades it to an ``error`` (unreadable
evidence blocks the gate and marks the audit incomplete), never a silent pass.
Nothing mutates DSS.

The verdict spans four buckets (structure, documentation, evidence,
maintainability) plus an optional contract, and four statuses a :class:`Check`
can carry:

* ``fail`` — a reviewer cannot trust or operate the project (blocks the gate).
* ``warn`` — suspicious; usually worth fixing before delivery (advisory).
* ``error`` — a FAIL-severity check whose evidence could not be read/evaluated
  (raised or timed out); blocks the gate and marks the audit ``incomplete`` —
  unreadable evidence is never treated as success.
* ``skip`` — a WARN-severity check that could not run (its dependency raised /
  timed out); never blocks, surfaced so the supervisor knows it was not run.

Every failing check names the offending objects and a ``fix`` re-pointed at this
server's action model: a copy-paste Cobuild delegation prompt, or a named MCP
tool (e.g. ``build_datasets``) for the rare direct action. There are no ``dku``
shell commands here — those are meaningless to the supervisor.

Callers pass a ``dataikuapi`` project handle. Use :func:`run_audit` for the
all-in-one payload, or compose :func:`load_context` + :func:`run_bucket` +
:func:`run_contract_checks` + :func:`build_payload` to interleave progress
reporting (as the MCP tool wrapper does, one ``run_blocking`` call per bucket).
"""

from __future__ import annotations

import contextlib
import re
import threading
import time
from dataclasses import asdict, dataclass, field
from itertools import islice
from typing import Any, Callable

from .serialization import columnar

FAIL = "fail"
WARN = "warn"
SKIP = "skip"
PASS = "pass"
# A FAIL-severity check whose evidence could not be read/evaluated. Unlike a
# ``skip`` (a WARN check that could not run), an ``error`` blocks the gate and
# marks the whole audit ``incomplete`` — unreadable evidence is never success.
ERROR = "error"

MAX_SAMPLE_ROWS = 100

# The flow-consistency check is the one heavy DSS round-trip. Bound the internal
# future polling with this soft deadline, and bound the whole check body (which
# runs in a dedicated thread) with the hard deadline below, so a slow or wedged
# instance turns one check into an ``error`` instead of hanging the audit.
FLOW_CHECK_TIMEOUT_SECONDS = 60.0
FLOW_CHECK_HARD_TIMEOUT_SECONDS = 70.0
_FLOW_POLL_INTERVAL_SECONDS = 1.0

AUDIT_BUCKETS_ORDER = ("structure", "documentation", "evidence", "maintainability")
AUDIT_BUCKETS = frozenset(AUDIT_BUCKETS_ORDER)

CODE_RECIPE_TYPES = {"python", "r", "shell", "pyspark", "sparkr", "spark_scala"}

# Editor/default object names DSS hands out when nobody renamed the object.
LAZY_NAME = re.compile(r"(_copy(_\d+)?)$|^(compute_|new_dataset|untitled)", re.I)
# Scaffolding/reference names that must not survive as disconnected datasets.
REFERENCE_NAME = re.compile(r"(^expected_|^reference_|^ref_|^tmp_|_expected$|_actual$)", re.I)
# Identifier columns whose blanks are almost always a parsing/join bug. Kept to
# id/key spellings — a blank generic ``*name`` is too often legitimate to fail on.
KEY_COLUMN_NAME = re.compile(r"(^id$|_id$|^key$|_key$)", re.I)

# Matched against wiki heading lines only (see HEADING_LINE), so a stray "this
# source was flaky" sentence in the prose doesn't count as a Sources section.
RUNBOOK_SECTIONS = {
    "purpose": ("purpose", "overview", "goal", "objective"),
    "sources": ("source", "input"),
}

# A markdown heading line (`#`..`######`) or a bold-label line (`**Sources:**`).
HEADING_LINE = re.compile(r"^\s*(#{1,6}\s|\*\*[^*]+\*\*\s*:?\s*$)")


# --------------------------------------------------------------------------- #
# Check model
# --------------------------------------------------------------------------- #
@dataclass
class Check:
    id: str
    status: str
    bucket: str
    severity: str
    detail: str = ""
    fix: str = ""


def _ok(id: str, *, bucket: str, severity: str = FAIL) -> Check:
    return Check(id=id, status=PASS, bucket=bucket, severity=severity)


def _bad(id: str, *, bucket: str, detail: str, severity: str = FAIL, fix: str = "") -> Check:
    return Check(id=id, status=severity, bucket=bucket, severity=severity, detail=detail, fix=fix)


def _skip(id: str, *, bucket: str, severity: str, detail: str) -> Check:
    return Check(id=id, status=SKIP, bucket=bucket, severity=severity, detail=detail)


def _error(id: str, *, bucket: str, severity: str, detail: str) -> Check:
    return Check(id=id, status=ERROR, bucket=bucket, severity=severity, detail=detail)


def _verdict(
    id: str, *, bucket: str, problems: list[str], severity: str = FAIL, fix: str = ""
) -> Check:
    if problems:
        return _bad(id, bucket=bucket, detail="; ".join(problems), severity=severity, fix=fix)
    return _ok(id, bucket=bucket, severity=severity)


def _listing(
    id: str,
    *,
    bucket: str,
    items: list[str],
    problem: str,
    fix: str = "",
    severity: str = FAIL,
) -> Check:
    """Check built from a list of offending object names.

    ``problem`` and ``fix`` are format strings; ``{names}`` expands to the
    comma-joined items. A clean check (no items) returns pass and drops the fix.
    """
    if not items:
        return _ok(id, bucket=bucket, severity=severity)
    names = ", ".join(items)
    return _bad(
        id,
        bucket=bucket,
        detail=problem.format(names=names),
        fix=fix.format(names=names),
        severity=severity,
    )


# A check unit: (id, bucket, severity, thunk). ``thunk`` produces the Check(s);
# if it raises, the unit degrades so one broken read never aborts the audit. A
# FAIL-severity unit degrades to an ``error`` (unreadable evidence blocks the
# gate); a WARN-severity unit degrades to a ``skip`` (advisory, never blocks).
# ``severity`` is the severity the degraded check inherits.
CheckUnit = tuple[str, str, str, Callable[[], "Check | list[Check] | None"]]


def _collect(units: list[CheckUnit]) -> list[Check]:
    out: list[Check] = []
    for check_id, bucket, severity, thunk in units:
        try:
            result = thunk()
        except Exception as exc:  # per-check isolation
            if severity == FAIL:
                out.append(
                    _error(
                        check_id,
                        bucket=bucket,
                        severity=severity,
                        detail=f"check could not be evaluated: {exc}",
                    )
                )
            else:
                out.append(
                    _skip(
                        check_id,
                        bucket=bucket,
                        severity=severity,
                        detail=f"check could not run: {exc}",
                    )
                )
            continue
        if result is None:
            continue
        out.extend(result if isinstance(result, list) else [result])
    return out


# --------------------------------------------------------------------------- #
# Text quality heuristics
# --------------------------------------------------------------------------- #
def _normalize(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


def low_quality_descriptions(described: dict[str, str]) -> dict[str, str]:
    """Map object name -> why its description reads as auto-fill, not authorship."""
    issues: dict[str, str] = {}
    for name, desc in described.items():
        if _normalize(desc) and _normalize(desc) == _normalize(name):
            issues[name] = "just repeats the name"
        if len(desc.split()) < 2:
            issues.setdefault(name, "too short")
        if re.search(r"\b(todo|test|temp|temporary|tbd|placeholder)\b", desc, re.I):
            issues.setdefault(name, "placeholder language")
    grouped: dict[str, list[str]] = {}
    for name, desc in described.items():
        grouped.setdefault(_normalize(desc), []).append(name)
    for norm, names in grouped.items():
        if norm and len(names) >= 3:
            for name in names:
                issues.setdefault(name, f"templated, shared by {len(names)} objects")
    return issues


def _describe_problems(missing: list[str], described: dict[str, str], label: str) -> list[str]:
    problems: list[str] = []
    if missing:
        problems.append(f"{label} without a description: {', '.join(sorted(missing))}")
    low = low_quality_descriptions(described)
    if low:
        problems.append(
            f"{label} with low-quality descriptions: "
            + ", ".join(f"{n} ({why})" for n, why in sorted(low.items()))
        )
    return problems


# --------------------------------------------------------------------------- #
# Graph
# --------------------------------------------------------------------------- #
def graph_sets(nodes: dict[str, Any], datasets: set[str]) -> tuple[set[str], set[str], set[str]]:
    """(inputs, outputs, terminal) dataset sets derived from recipe nodes."""
    inputs: set[str] = set()
    outputs: set[str] = set()
    for node in nodes.values():
        if node.get("type") != "RUNNABLE_RECIPE":
            continue
        inputs.update(p for p in node.get("predecessors", []) if p in datasets)
        outputs.update(s for s in node.get("successors", []) if s in datasets)
    return inputs, outputs, outputs - inputs


# --------------------------------------------------------------------------- #
# Value helpers
# --------------------------------------------------------------------------- #
def _is_blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _looks_numeric(values: list[Any]) -> bool:
    seen = numeric = 0
    for value in values:
        if _is_blank(value):
            continue
        seen += 1
        try:
            float(str(value).replace(",", ""))
            numeric += 1
        except ValueError:
            pass
    return seen >= 5 and numeric / seen >= 0.9


def _all_same(values: list[Any]) -> bool:
    present = [v for v in values if not _is_blank(v)]
    return len(present) >= 5 and len({str(v) for v in present}) == 1


# --------------------------------------------------------------------------- #
# DSS reads (kept tiny so per-object failures stay local)
# --------------------------------------------------------------------------- #
def _dataset_metadata(proj, name: str) -> dict[str, Any]:
    return proj.get_dataset(name).get_metadata()


def _recipe_metadata(proj, name: str) -> dict[str, Any]:
    return proj.get_recipe(name).get_settings().get_recipe_raw_definition()


def _dataset_columns(proj, name: str) -> list[dict[str, Any]]:
    return proj.get_dataset(name).get_definition().get("schema", {}).get("columns", [])


def _terminal_columns_scan(proj, terminal: set[str]) -> tuple[list[str], list[str]]:
    """Split terminal outputs into (undocumented columns, unreadable schema).

    A dataset whose schema read *raises* is unreadable evidence — it is reported
    as an explicit gap, never silently treated as "documented" (the old
    ``_has_documented_column`` returned True on failure, which hid a denied read).
    A dataset with no schema at all is neither undocumented nor unreadable.
    """
    undocumented: list[str] = []
    unreadable: list[str] = []
    for name in sorted(terminal):
        try:
            columns = _dataset_columns(proj, name)
        except Exception:
            unreadable.append(name)
            continue
        if columns and not any(c.get("comment", "").strip() for c in columns):
            undocumented.append(name)
    return undocumented, unreadable


def _dataset_sample(proj, name: str, columns: list[dict[str, Any]], max_rows: int) -> list[dict[str, Any]]:
    names = [c.get("name", "") for c in columns]
    # ``islice`` pulls *exactly* ``max_rows`` items from the row iterator and no
    # more — so a 100-row sample consumes 100 rows, never the 101st. (An
    # ``enumerate``/``break`` loop would fetch row max_rows+1 before deciding to
    # stop, an unnecessary read against the live dataset.)
    return [
        dict(zip(names, row, strict=False))
        for row in islice(proj.get_dataset(name).iter_rows(), max(max_rows, 0))
    ]


def _terminal_row_count(proj, name: str) -> int:
    """Cached COUNT_RECORDS for a terminal output (keeps the audit read-only).

    Raises when no cached value exists; callers treat that as "unknown".
    """
    metrics = proj.get_dataset(name).get_last_metric_values()
    return int(metrics.get_global_value("records:COUNT_RECORDS"))


def _await_future_bounded(future, timeout_seconds: float) -> None:
    """Poll a DSSFuture to completion, or raise ``TimeoutError`` at the deadline.

    ``DSSFuture.wait_for_result`` has no timeout of its own, so the audit does the
    bounded polling itself rather than block indefinitely on a stuck instance.
    """
    deadline = time.monotonic() + timeout_seconds
    state = getattr(future, "state", None)
    while True:
        if state and state.get("hasResult", False):
            return
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError(
                f"flow consistency check exceeded {timeout_seconds:.0f}s"
            )
        time.sleep(min(_FLOW_POLL_INTERVAL_SECONDS, remaining))
        state = future.get_state()


def _run_flow_consistency(proj, timeout_seconds: float) -> tuple[bool, str]:
    """Body of the flow consistency check; return (clean, first error message).

    Runs the DSS round-trip: start the tool, poll its future (bounded), read the
    per-node results, and always stop the tool. Any of these SDK calls can block,
    so this body is invoked from a bounded worker thread (see
    :func:`_flow_check_clean`).
    """
    flow = proj.get_flow()
    tool = flow.start_tool("CHECK_CONSISTENCY")
    try:
        future = tool.update(
            {
                "recheckAll": True,
                "datasets": {"consistencyWithData": True},
                "recipes": {"schemaConsistency": True, "otherExpensiveChecks": False},
            }
        )
        _await_future_bounded(future, timeout_seconds)
        state = tool.get_state()
        for node_id, node_state in state.get("stateByNode", {}).items():
            for key in ("recipeCheckResult", "datasetCheckResult"):
                for msg in node_state.get(key, {}).get("messages", []):
                    if msg.get("isFatal") or msg.get("severity") in ("ERROR", "FATAL"):
                        return False, f"{node_id}: {msg.get('message', msg.get('code', ''))}"
        return True, ""
    finally:
        with contextlib.suppress(Exception):
            tool.stop()


def _flow_check_clean(proj, timeout_seconds: float = FLOW_CHECK_TIMEOUT_SECONDS) -> tuple[bool, str]:
    """Run the flow consistency check in a bounded worker thread.

    The individual SDK calls (``tool.update``, future polling, ``tool.stop``) can
    each block indefinitely on a wedged instance, and the between-calls deadline
    in :func:`_await_future_bounded` cannot interrupt a call already in flight. So
    the whole body runs in a daemon thread bounded by
    :data:`FLOW_CHECK_HARD_TIMEOUT_SECONDS`. On timeout this raises ``TimeoutError``
    (the check is FAIL-severity, so :func:`_collect` records it as an ``error`` and
    the audit continues); the abandoned daemon thread cannot block process exit.
    """
    box: dict[str, Any] = {}

    def _body() -> None:
        try:
            box["result"] = _run_flow_consistency(proj, timeout_seconds)
        except BaseException as exc:  # propagated to the caller thread below
            box["error"] = exc

    worker = threading.Thread(target=_body, name="audit-flow-check", daemon=True)
    worker.start()
    worker.join(FLOW_CHECK_HARD_TIMEOUT_SECONDS)
    if worker.is_alive():
        raise TimeoutError(
            f"flow consistency check exceeded {FLOW_CHECK_HARD_TIMEOUT_SECONDS:.0f}s"
        )
    if "error" in box:
        raise box["error"]
    return box["result"]


# --------------------------------------------------------------------------- #
# Zone helpers
# --------------------------------------------------------------------------- #
def _zone_covered(zones: list[dict[str, Any]]) -> set[str]:
    covered: set[str] = set()
    for zone in zones:
        if zone.get("id") == "default":
            continue
        for item in zone.get("items", []):
            oid = item.get("objectId") or item.get("id")
            if oid:
                covered.add(oid)
    return covered


def _is_default(zone: dict[str, Any]) -> bool:
    return zone.get("id") == "default"


def _default_repurposed(zone: dict[str, Any]) -> bool:
    """The default zone becomes a first-class stage only once it is renamed off
    the stock name DSS ships ("Default"). Its id stays "default" forever, so the
    rename is the sole signal that the author adopted it instead of stranding it.
    """
    name = (zone.get("name") or "").strip()
    return _is_default(zone) and bool(name) and name.casefold() != "default"


def _is_real_zone(zone: dict[str, Any]) -> bool:
    """A deliberately-organized zone: any named zone, or a repurposed default."""
    return not _is_default(zone) or _default_repurposed(zone)


def _default_members(zones: list[dict[str, Any]], universe: set[str]) -> set[str]:
    """Objects that fall to the default zone — everything not explicitly placed in
    a named zone. DSS reports the default zone's items[] as empty even when it
    holds objects, so membership is derived rather than read."""
    return universe - _zone_covered(zones)


def _undescribed_zones(zones: list[dict[str, Any]], universe: set[str]) -> list[str]:
    """Populated, real zones missing a shortDesc — named zones plus a repurposed
    default (whose membership is derived, since items[] reads empty)."""
    missing = [
        z.get("name", "")
        for z in zones
        if not _is_default(z) and z.get("itemCount", 0) and not z.get("shortDesc")
    ]
    default = next((z for z in zones if _is_default(z)), None)
    if (
        default is not None
        and _default_repurposed(default)
        and _default_members(zones, universe)
        and not default.get("shortDesc")
    ):
        missing.append(default.get("name", ""))
    return sorted(missing)


# --------------------------------------------------------------------------- #
# Description scans
# --------------------------------------------------------------------------- #
# A description scan returns (problems, unreadable): the quality problems found
# among readable objects, and the names of objects whose metadata read *raised*
# (unreadable evidence — never silently dropped, per fail-closed auditing).
DescriptionScan = tuple[list[str], list[str]]


def _description_scan(reader, proj, names: list[str], label: str) -> DescriptionScan:
    """Read each object's description via ``reader``; return (problems, unreadable)."""
    missing: list[str] = []
    described: dict[str, str] = {}
    unreadable: list[str] = []
    for name in names:
        try:
            meta = reader(proj, name)
        except Exception:
            unreadable.append(name)
            continue
        text = (meta.get("description") or meta.get("shortDesc") or "").strip()
        if text:
            described[name] = text
        else:
            missing.append(name)
    return _describe_problems(missing, described, label), unreadable


def _short_desc_scan(reader, proj, names: list[str], label: str) -> DescriptionScan:
    missing: list[str] = []
    described: dict[str, str] = {}
    unreadable: list[str] = []
    for name in names:
        try:
            meta = reader(proj, name)
        except Exception:
            unreadable.append(name)
            continue
        text = (meta.get("shortDesc") or "").strip()
        if text:
            described[name] = text
        else:
            missing.append(name)
    return _describe_problems(missing, described, label), unreadable


def _scan_verdict(
    id: str,
    *,
    bucket: str,
    scan: DescriptionScan,
    severity: str,
    fix: str = "",
) -> Check:
    """Turn a description-scan result into a Check with fail-closed evidence rules.

    A read that *raised* is unreadable evidence, not a clean object:

    * FAIL-severity — a pass can only be certified when every object was
      readable. A found problem is a proven fail (report it, note any unreadable
      objects). No problem but unreadable reads means the assertion cannot be
      proven, so the check is an ``error`` (blocks the gate, marks the audit
      incomplete) rather than a false pass.
    * WARN-severity — advisory, never blocks; it reports its problems and merely
      notes the unread objects as an evidence gap in the detail.
    """
    problems, unreadable = scan
    gap = f"could not read (evidence gap): {', '.join(sorted(unreadable))}" if unreadable else ""
    if severity == FAIL:
        if problems:
            detail = "; ".join(problems + ([gap] if gap else []))
            return _bad(id, bucket=bucket, detail=detail, severity=FAIL, fix=fix)
        if unreadable:
            return _error(
                id,
                bucket=bucket,
                severity=FAIL,
                detail=f"cannot certify — description evidence unreadable for: "
                f"{', '.join(sorted(unreadable))}",
            )
        return _ok(id, bucket=bucket, severity=FAIL)
    return _verdict(
        id,
        bucket=bucket,
        problems=problems + ([gap] if gap else []),
        severity=WARN,
        fix=fix,
    )


# --------------------------------------------------------------------------- #
# Fix strings (re-pointed at THIS server's action model — never `dku`)
# --------------------------------------------------------------------------- #
_FIX_ORPHANS = (
    'Delegate to Cobuild: "Connect, delete, or document these disconnected datasets: {names}"'
)
_FIX_REFERENCE = (
    'Delegate to Cobuild: "These reference/tmp datasets ({names}) are disconnected from the '
    'flow — connect, document, or remove them."'
)
_FIX_ZONES_PRESENT = (
    'Delegate to Cobuild: "Organize this flow into labeled flow zones by stage '
    '(e.g. ingestion, preparation, output)."'
)
_FIX_EMPTY_ZONES = 'Delegate to Cobuild: "Delete these empty flow zones: {names}"'
_FIX_DEFAULT_ZONE_EMPTY = (
    'Delegate to Cobuild: "The default flow zone is empty; rename it to a real stage and move '
    'that stage\'s objects back into it."'
)
_FIX_ZONE_COVERAGE = (
    'Delegate to Cobuild: "Move these datasets into the appropriate named flow zone: {names}"'
)

_FIX_OUTPUT_DESC = (
    'Delegate to Cobuild: "Write a description for each output dataset explaining what it '
    'contains and how it was produced."'
)
_FIX_SOURCE_DESC = (
    'Delegate to Cobuild: "Add a description to each source dataset explaining its origin and '
    'meaning."'
)
_FIX_RECIPE_DESC = (
    'Delegate to Cobuild: "Add a short description to each recipe explaining the transformation '
    'it performs."'
)
_FIX_ZONE_DESC = 'Delegate to Cobuild: "Add a short description to each named flow zone: {names}"'
_FIX_COLUMN_DESC = (
    'Delegate to Cobuild: "Document the columns of these terminal outputs (add column '
    'descriptions): {names}"'
)
_FIX_FLOW_VISIBLE = (
    'Delegate to Cobuild: "Add flow-visible descriptions — dataset descriptions plus recipe and '
    'zone short descriptions — so every flow tile is labeled."'
)
_FIX_WIKI_MISSING = (
    'Delegate to Cobuild: "Create a project wiki \'Runbook\' article covering the project\'s '
    'purpose and its data sources."'
)
_FIX_WIKI_RUNBOOK = (
    'Delegate to Cobuild: "Add the missing runbook headings ({names}) to the project wiki."'
)

_FIX_FLOW_CHECK = (
    'Delegate to Cobuild: "Resolve the flow consistency errors and rebuild the affected datasets."'
)
_FIX_BUILT = (
    'Build these terminal outputs with the build_datasets tool (recursive build), or delegate '
    'to Cobuild to build them: {names}'
)
_FIX_ROW_COUNT = (
    'Delegate to Cobuild: "Build/compute these datasets so a record count metric is available: '
    '{names}"'
)
_FIX_ALL_NULL = (
    'Delegate to Cobuild: "These terminal columns are entirely blank in the sample ({names}); '
    'inspect the upstream formula/prepare steps that feed them and rebuild."'
)
_FIX_BLANK_KEYS = (
    'Delegate to Cobuild: "Likely key columns contain blanks ({names}); fix the upstream '
    'parsing/join logic and rebuild."'
)
_FIX_TYPE_SMELLS = (
    'Delegate to Cobuild: "Numeric-looking string columns ({names}); infer types or set the '
    'schema, then rebuild."'
)
_FIX_DIVERSITY = (
    'Delegate to Cobuild: "String columns collapse to a single sampled value ({names}); confirm '
    'this is expected or document it in the wiki."'
)

_FIX_VISUAL_FIRST = (
    'Delegate to Cobuild: "Replace these code recipes with visual recipes wherever the '
    'capability exists: {names}"'
)
_FIX_RECIPE_NAMING = (
    'Delegate to Cobuild: "Rename these auto-named recipes to an action verb or a clear '
    'transformation noun: {names}"'
)
_FIX_DATASET_NAMING = (
    'Delegate to Cobuild: "Rename these auto-named terminal datasets to business names: {names}"'
)


# --------------------------------------------------------------------------- #
# Audit context
# --------------------------------------------------------------------------- #
@dataclass
class AuditContext:
    proj: Any
    project_key: str
    datasets: set[str]
    recipes: list[dict[str, Any]]
    recipe_names: set[str]
    zones: list[dict[str, Any]]
    inputs: set[str]
    outputs: set[str]
    terminal: set[str]
    inventory: dict[str, Any] = field(default_factory=dict)


def _zone_dicts(proj) -> list[dict[str, Any]]:
    zones: list[dict[str, Any]] = []
    for z in proj.get_flow().list_zones():
        raw = getattr(z, "_raw", {}) or {}
        items = raw.get("items", []) or []
        zones.append(
            {
                "id": z.id,
                "name": z.name,
                "shortDesc": raw.get("shortDesc", ""),
                "itemCount": len(items),
                "items": items,
            }
        )
    return zones


def _wiki_bodies(proj) -> list[str] | None:
    articles = proj.get_wiki().list_articles()
    if not articles:
        return None
    bodies: list[str] = []
    for article in articles:
        data = article.get_data()
        bodies.append(f"{data.get_name() or ''}\n{data.get_body() or ''}")
    return bodies


def load_context(proj, project_key: str) -> AuditContext:
    """Load the cheap, foundational flow facts once, shared by every bucket."""
    datasets = {d.get("name", d.get("id", "")) for d in proj.list_datasets()}
    recipes = [
        {"name": r.get("name", ""), "type": r.get("type", "")} for r in proj.list_recipes()
    ]
    recipe_names = {r["name"] for r in recipes if r.get("name")}
    nodes = proj.get_flow().get_graph().nodes
    zones = _zone_dicts(proj)
    inputs, outputs, terminal = graph_sets(nodes, datasets)
    inventory = {
        "datasets": len(datasets),
        "recipes": len(recipes),
        "zones": len([z for z in zones if _is_real_zone(z)]),
        "terminal_datasets": sorted(terminal),
        "source_datasets": sorted(inputs - outputs),
        "orphan_datasets": sorted(datasets - inputs - outputs),
    }
    return AuditContext(
        proj=proj,
        project_key=project_key,
        datasets=datasets,
        recipes=recipes,
        recipe_names=recipe_names,
        zones=zones,
        inputs=inputs,
        outputs=outputs,
        terminal=terminal,
        inventory=inventory,
    )


# --------------------------------------------------------------------------- #
# Bucket: structure
# --------------------------------------------------------------------------- #
def _structure_units(actx: AuditContext) -> list[CheckUnit]:
    datasets, recipe_names = actx.datasets, actx.recipe_names
    inputs, outputs = actx.inputs, actx.outputs
    zones = actx.zones

    orphans = sorted(datasets - inputs - outputs)
    bad_refs = sorted(n for n in datasets if REFERENCE_NAME.search(n) and n in orphans)
    nondefault_zones = [z for z in zones if not _is_default(z)]
    default_zone = next((z for z in zones if _is_default(z)), None)
    repurposed = default_zone is not None and _default_repurposed(default_zone)
    organizing = bool(nondefault_zones) or repurposed
    default_members = _default_members(zones, datasets | recipe_names)
    empty_zones = sorted(z.get("name", "") for z in nondefault_zones if not z.get("itemCount"))

    units: list[CheckUnit] = [
        (
            "no_orphan_datasets",
            "structure",
            FAIL,
            lambda: _listing(
                "no_orphan_datasets",
                bucket="structure",
                items=orphans,
                problem="Datasets not connected to any recipe: {names}",
                fix=_FIX_ORPHANS,
            ),
        ),
        (
            "reference_dataset_policy",
            "structure",
            WARN,
            lambda: _listing(
                "reference_dataset_policy",
                bucket="structure",
                severity=WARN,
                items=bad_refs,
                problem="Reference/tmp-looking datasets are disconnected: {names}",
                fix=_FIX_REFERENCE,
            ),
        ),
    ]
    if len(recipe_names) > 3 or len(datasets) > 5:
        units.append(
            (
                "flow_zones_present",
                "structure",
                WARN,
                lambda: _verdict(
                    "flow_zones_present",
                    bucket="structure",
                    severity=WARN,
                    problems=["Non-trivial flow has no flow zones"] if not organizing else [],
                    fix=_FIX_ZONES_PRESENT,
                ),
            )
        )
    units.append(
        (
            "empty_zones",
            "structure",
            WARN,
            lambda: _listing(
                "empty_zones",
                bucket="structure",
                severity=WARN,
                items=empty_zones,
                problem="Named zones with no items (leftover scaffolding): {names}",
                fix=_FIX_EMPTY_ZONES,
            ),
        )
    )
    if nondefault_zones and not default_members:
        units.append(
            (
                "default_zone_empty",
                "structure",
                WARN,
                lambda: _verdict(
                    "default_zone_empty",
                    bucket="structure",
                    severity=WARN,
                    problems=[
                        "The default flow zone is empty — its objects were moved into named "
                        "zones, stranding it. The default zone can't be deleted; rename it to a "
                        "real stage and move that stage's objects into it."
                    ],
                    fix=_FIX_DEFAULT_ZONE_EMPTY,
                ),
            )
        )
    if organizing:
        loose = [] if repurposed else sorted(default_members)
        units.append(
            (
                "zone_coverage",
                "structure",
                WARN,
                lambda: _listing(
                    "zone_coverage",
                    bucket="structure",
                    severity=WARN,
                    items=loose,
                    problem="Datasets left outside the named zones: {names}",
                    fix=_FIX_ZONE_COVERAGE,
                ),
            )
        )
    return units


# --------------------------------------------------------------------------- #
# Bucket: documentation
# --------------------------------------------------------------------------- #
def _flow_visible_description_check(actx: AuditContext) -> Check:
    proj, zones = actx.proj, actx.zones
    sources, terminal = actx.datasets - actx.terminal, actx.terminal
    recipe_names = sorted(actx.recipe_names)

    # Datasets have no `shortDesc` in DSS — only `description`, which is what the
    # flow tile renders. Recipes and zones do carry a real `shortDesc`.
    terminal_problems, terminal_unreadable = _description_scan(
        _dataset_metadata, proj, sorted(terminal), "Terminal datasets"
    )
    source_problems, _ = _description_scan(_dataset_metadata, proj, sorted(sources), "Source datasets")
    recipe_problems, _ = _short_desc_scan(_recipe_metadata, proj, recipe_names, "Recipes")
    zone_missing = _undescribed_zones(zones, sources | terminal | set(recipe_names))
    zone_problems = (
        [f"Named zones without a short description: {', '.join(sorted(zone_missing))}"]
        if zone_missing
        else []
    )
    problems = terminal_problems + source_problems + recipe_problems + zone_problems
    gap = (
        f"terminal description evidence unreadable for: {', '.join(sorted(terminal_unreadable))}"
        if terminal_unreadable
        else ""
    )
    # A missing terminal-output description is flow-blind at the point that matters
    # most, so it fails; the rest are advisory.
    if terminal_problems:
        return _bad(
            "flow_visible_descriptions",
            bucket="documentation",
            detail="; ".join(problems + ([gap] if gap else [])),
            severity=FAIL,
            fix=_FIX_FLOW_VISIBLE,
        )
    # Terminal descriptions are the FAIL-worthy part; if they could not be read we
    # cannot certify them — that is an ``error`` (blocks the gate), even when
    # only advisory source/recipe/zone problems exist.
    if terminal_unreadable:
        detail = gap
        if problems:
            detail += "; also: " + "; ".join(problems)
        return _error(
            "flow_visible_descriptions",
            bucket="documentation",
            severity=FAIL,
            detail=detail,
        )
    if problems:
        return _bad(
            "flow_visible_descriptions",
            bucket="documentation",
            detail="; ".join(problems),
            severity=WARN,
            fix=_FIX_FLOW_VISIBLE,
        )
    return _ok("flow_visible_descriptions", bucket="documentation", severity=WARN)


def _wiki_units(actx: AuditContext) -> list[CheckUnit]:
    proj = actx.proj
    holder: dict[str, list[str] | None] = {}

    def bodies() -> list[str] | None:
        if "v" not in holder:
            holder["v"] = _wiki_bodies(proj)
        return holder["v"]

    def has_wiki_check() -> Check:
        if bodies() is None:
            return _bad(
                "has_wiki",
                bucket="documentation",
                severity=WARN,
                detail="No wiki articles found",
                fix=_FIX_WIKI_MISSING,
            )
        return _ok("has_wiki", bucket="documentation", severity=WARN)

    def wiki_runbook_check() -> Check | None:
        wiki = bodies()
        if wiki is None:
            return None
        headings = "\n".join(
            line for body in wiki for line in body.splitlines() if HEADING_LINE.match(line)
        ).lower()
        missing = [
            name
            for name, kws in RUNBOOK_SECTIONS.items()
            if not any(k in headings for k in kws)
        ]
        return _listing(
            "wiki_runbook",
            bucket="documentation",
            severity=WARN,
            items=missing,
            problem="Wiki is missing runbook headings: {names}",
            fix=_FIX_WIKI_RUNBOOK,
        )

    return [
        ("has_wiki", "documentation", WARN, has_wiki_check),
        ("wiki_runbook", "documentation", WARN, wiki_runbook_check),
    ]


def _terminal_columns_check(proj, terminal: set[str]) -> Check:
    """Advisory (WARN) check: terminal outputs should carry column descriptions.

    Unreadable schemas are surfaced as an explicit evidence gap rather than being
    counted as documented — a WARN never blocks, but it must not hide a denied
    schema read behind a clean pass.
    """
    undocumented, unreadable = _terminal_columns_scan(proj, terminal)
    problems: list[str] = []
    if undocumented:
        problems.append(
            "Terminal outputs with no documented columns: " + ", ".join(undocumented)
        )
    if unreadable:
        problems.append("schema unreadable (evidence gap): " + ", ".join(unreadable))
    if not problems:
        return _ok("terminal_columns_documented", bucket="documentation", severity=WARN)
    return _bad(
        "terminal_columns_documented",
        bucket="documentation",
        detail="; ".join(problems),
        severity=WARN,
        fix=_FIX_COLUMN_DESC.format(names=", ".join(undocumented)) if undocumented else "",
    )


def _documentation_units(actx: AuditContext) -> list[CheckUnit]:
    proj = actx.proj
    datasets, terminal = actx.datasets, actx.terminal
    zones, recipe_names = actx.zones, sorted(actx.recipe_names)

    units: list[CheckUnit] = [
        (
            "datasets_have_descriptions",
            "documentation",
            FAIL,
            lambda: _scan_verdict(
                "datasets_have_descriptions",
                bucket="documentation",
                scan=_description_scan(_dataset_metadata, proj, sorted(terminal), "Output datasets"),
                severity=FAIL,
                fix=_FIX_OUTPUT_DESC,
            ),
        ),
        (
            "source_datasets_have_descriptions",
            "documentation",
            WARN,
            lambda: _scan_verdict(
                "source_datasets_have_descriptions",
                bucket="documentation",
                severity=WARN,
                scan=_description_scan(
                    _dataset_metadata, proj, sorted(datasets - terminal), "Source datasets"
                ),
                fix=_FIX_SOURCE_DESC,
            ),
        ),
        (
            "recipes_have_descriptions",
            "documentation",
            WARN,
            lambda: _scan_verdict(
                "recipes_have_descriptions",
                bucket="documentation",
                severity=WARN,
                scan=_description_scan(_recipe_metadata, proj, recipe_names, "Recipes"),
                fix=_FIX_RECIPE_DESC,
            ),
        ),
        (
            "zones_have_short_desc",
            "documentation",
            WARN,
            lambda: _listing(
                "zones_have_short_desc",
                bucket="documentation",
                severity=WARN,
                items=_undescribed_zones(zones, datasets | set(recipe_names)),
                problem="Named zones without short descriptions: {names}",
                fix=_FIX_ZONE_DESC,
            ),
        ),
        (
            "terminal_columns_documented",
            "documentation",
            WARN,
            lambda: _terminal_columns_check(proj, terminal),
        ),
        (
            "flow_visible_descriptions",
            "documentation",
            FAIL,
            lambda: _flow_visible_description_check(actx),
        ),
    ]
    units.extend(_wiki_units(actx))
    return units


# --------------------------------------------------------------------------- #
# Bucket: evidence
# --------------------------------------------------------------------------- #
def _scan_column_smells(
    dataset: str,
    columns: list[dict[str, Any]],
    rows: list[dict[str, Any]],
    acc: dict[str, list[str]],
) -> None:
    """Accumulate per-column value smells for one terminal dataset into ``acc``."""
    for col in columns:
        name = col.get("name", "")
        is_string = col.get("type") == "string"
        values = [r.get(name) for r in rows]
        if all(_is_blank(v) for v in values):
            acc["all_null"].append(f"{dataset}.{name}")
        if KEY_COLUMN_NAME.search(name) and any(_is_blank(v) for v in values):
            acc["blank_keys"].append(f"{dataset}.{name}")
        if is_string and _looks_numeric(values):
            acc["numeric_strings"].append(f"{dataset}.{name}")
        if is_string and _all_same(values):
            acc["one_value"].append(f"{dataset}.{name}")


def _evidence_sweep(proj, terminal: set[str]) -> dict[str, Any]:
    """One read-only pass over terminal outputs: cached row counts + value smells.

    A single unreadable dataset must not abort the sweep. Both evidence gaps are
    recorded, never silently dropped: a missing/denied cached count lands in
    ``unknown_count`` and a denied schema/sample read lands in
    ``unreadable_sample`` — both surfaced by the (WARN-severity) row-count check.
    Only fully-read samples feed the value-smell heuristics.
    """
    empty: list[str] = []
    unknown_count: list[str] = []
    unreadable_sample: list[str] = []
    smells: dict[str, list[str]] = {
        "all_null": [],
        "blank_keys": [],
        "numeric_strings": [],
        "one_value": [],
    }
    for dataset in sorted(terminal):
        try:
            count = _terminal_row_count(proj, dataset)
        except Exception:
            count = None
        if count is None:
            unknown_count.append(dataset)
        elif count <= 0:
            empty.append(dataset)
        try:
            columns = _dataset_columns(proj, dataset)
            rows = _dataset_sample(proj, dataset, columns, MAX_SAMPLE_ROWS) if columns else []
        except Exception:
            rows = []
            unreadable_sample.append(dataset)
        if rows:
            _scan_column_smells(dataset, columns, rows, smells)
    return {
        "empty": empty,
        "unknown_count": unknown_count,
        "unreadable_sample": unreadable_sample,
        "smells": smells,
    }


def _flow_check_unit(proj) -> Check:
    clean, message = _flow_check_clean(proj)
    return _verdict(
        "flow_check_clean",
        bucket="evidence",
        problems=[message or "flow consistency check reported an error"] if not clean else [],
        fix=_FIX_FLOW_CHECK,
    )


def _terminal_outputs_built_check(sweep: dict[str, Any]) -> Check:
    """FAIL-severity evidence gate: every terminal output was built with real rows.

    The proof is each output's cached record count. Fail-closed, same discipline as
    the description scans (:func:`_scan_verdict`):

    * a proven-empty output (count <= 0) is a real fail — report it (and note any
      outputs whose count could not be read);
    * no proven-empty output but an *unreadable* count for some output means the
      assertion cannot be certified for those outputs, so the check is an ``error``
      (blocks the gate, marks the audit incomplete) rather than a false pass on
      absent evidence;
    * only when every output's count was readable and non-empty does it pass.

    The WARN :func:`_terminal_row_counts_check` still notes the same read gap.
    """
    empty = sweep["empty"]
    unknown = sweep["unknown_count"]
    gap = (
        "; could not read a record-count metric (evidence gap) for: " + ", ".join(unknown)
        if unknown
        else ""
    )
    if empty:
        return _bad(
            "terminal_outputs_built",
            bucket="evidence",
            detail="Terminal outputs with zero rows: " + ", ".join(empty) + gap,
            fix=_FIX_BUILT.format(names=", ".join(empty)),
        )
    if unknown:
        return _error(
            "terminal_outputs_built",
            bucket="evidence",
            severity=FAIL,
            detail=(
                "cannot certify terminal outputs were built — record-count evidence "
                "unreadable for: " + ", ".join(unknown)
            ),
        )
    return _ok("terminal_outputs_built", bucket="evidence", severity=FAIL)


def _terminal_row_counts_check(sweep: dict[str, Any]) -> Check:
    """Advisory (WARN) evidence-read check: unread cached counts and samples.

    Surfaces both gaps recorded by :func:`_evidence_sweep`. A sample-only gap
    (schema/sample denied but the count was readable) is reported separately so a
    denied read is never silent; a fully-denied dataset shows only in the
    count clause, not twice.
    """
    unknown = sweep["unknown_count"]
    sample_only = [d for d in sweep["unreadable_sample"] if d not in set(unknown)]
    problems: list[str] = []
    if unknown:
        problems.append("Could not read a cached row count for: " + ", ".join(unknown))
    if sample_only:
        problems.append("Could not read a data sample for: " + ", ".join(sample_only))
    if not problems:
        return _ok("terminal_row_counts", bucket="evidence", severity=WARN)
    return _bad(
        "terminal_row_counts",
        bucket="evidence",
        detail="; ".join(problems),
        severity=WARN,
        fix=_FIX_ROW_COUNT,
    )


def _evidence_units(actx: AuditContext) -> list[CheckUnit]:
    proj, terminal = actx.proj, actx.terminal
    holder: dict[str, dict[str, Any]] = {}

    def sweep() -> dict[str, Any]:
        if "v" not in holder:
            holder["v"] = _evidence_sweep(proj, terminal)
        return holder["v"]

    return [
        (
            "flow_check_clean",
            "evidence",
            FAIL,
            lambda: _flow_check_unit(proj),
        ),
        (
            "terminal_outputs_built",
            "evidence",
            FAIL,
            lambda: _terminal_outputs_built_check(sweep()),
        ),
        (
            "terminal_row_counts",
            "evidence",
            WARN,
            lambda: _terminal_row_counts_check(sweep()),
        ),
        (
            "all_null_columns",
            "evidence",
            WARN,
            lambda: _listing(
                "all_null_columns",
                bucket="evidence",
                severity=WARN,
                items=sweep()["smells"]["all_null"],
                problem="Terminal columns entirely blank in sample: {names}",
                fix=_FIX_ALL_NULL,
            ),
        ),
        (
            "blank_key_columns",
            "evidence",
            WARN,
            lambda: _listing(
                "blank_key_columns",
                bucket="evidence",
                severity=WARN,
                items=sweep()["smells"]["blank_keys"],
                problem="Likely key columns contain blanks in sample: {names}",
                fix=_FIX_BLANK_KEYS,
            ),
        ),
        (
            "type_smells",
            "evidence",
            WARN,
            lambda: _listing(
                "type_smells",
                bucket="evidence",
                severity=WARN,
                items=sweep()["smells"]["numeric_strings"],
                problem="Numeric-looking string columns: {names}",
                fix=_FIX_TYPE_SMELLS,
            ),
        ),
        (
            "sample_diversity",
            "evidence",
            WARN,
            lambda: _listing(
                "sample_diversity",
                bucket="evidence",
                severity=WARN,
                items=sweep()["smells"]["one_value"],
                problem="String columns collapse to a single sampled value: {names}",
                fix=_FIX_DIVERSITY,
            ),
        ),
    ]


# --------------------------------------------------------------------------- #
# Bucket: maintainability
# --------------------------------------------------------------------------- #
def _maintainability_units(actx: AuditContext) -> list[CheckUnit]:
    recipes, terminal = actx.recipes, actx.terminal
    code_recipes = sorted(
        r["name"] for r in recipes if str(r.get("type", "")).lower() in CODE_RECIPE_TYPES
    )
    lazy_recipes = sorted(
        r["name"] for r in recipes if r.get("name") and LAZY_NAME.search(r["name"])
    )
    lazy_terminals = sorted(n for n in terminal if LAZY_NAME.search(n))
    return [
        (
            "visual_first",
            "maintainability",
            WARN,
            lambda: _listing(
                "visual_first",
                bucket="maintainability",
                severity=WARN,
                items=code_recipes,
                problem="Code recipes present: {names}",
                fix=_FIX_VISUAL_FIRST,
            ),
        ),
        (
            "recipe_naming",
            "maintainability",
            WARN,
            lambda: _listing(
                "recipe_naming",
                bucket="maintainability",
                severity=WARN,
                items=lazy_recipes,
                problem="Recipes with default/auto names: {names}",
                fix=_FIX_RECIPE_NAMING,
            ),
        ),
        (
            "dataset_naming",
            "maintainability",
            WARN,
            lambda: _listing(
                "dataset_naming",
                bucket="maintainability",
                severity=WARN,
                items=lazy_terminals,
                problem="Terminal datasets with default/auto names: {names}",
                fix=_FIX_DATASET_NAMING,
            ),
        ),
    ]


_BUCKET_UNITS: dict[str, Callable[[AuditContext], list[CheckUnit]]] = {
    "structure": _structure_units,
    "documentation": _documentation_units,
    "evidence": _evidence_units,
    "maintainability": _maintainability_units,
}


def run_bucket(actx: AuditContext, bucket: str) -> list[Check]:
    """Run one bucket's checks against ``actx``; raising checks become ``skip``."""
    if bucket not in _BUCKET_UNITS:
        raise ValueError(f"Unknown audit bucket: {bucket}")
    return _collect(_BUCKET_UNITS[bucket](actx))


# --------------------------------------------------------------------------- #
# Contract
# --------------------------------------------------------------------------- #
def _validate_string_list(dataset: str, field_name: str, value: Any) -> None:
    """Reject a non-list, or any empty/non-string entry, for columns/not_blank."""
    if not isinstance(value, list):
        raise ValueError(f'contract output "{dataset}": "{field_name}" must be a list')
    for i, entry in enumerate(value):
        if not isinstance(entry, str) or not entry.strip():
            raise ValueError(
                f'contract output "{dataset}": "{field_name}"[{i}] must be a '
                "non-empty string"
            )


# The only assertion keys a per-output spec may carry. An unknown key is a typo
# (``min_row`` for ``min_rows``) that would otherwise silently drop the assertion,
# so it is rejected rather than ignored.
_KNOWN_OUTPUT_SPEC_KEYS = frozenset({"columns", "not_blank", "min_rows", "types"})

# The only top-level keys a contract may carry. ``outputs`` is the sole key the
# engine consumes (see :func:`_contract_units`), so an unknown top-level key
# (e.g. a top-level ``min_rows`` that belongs inside an output spec) is a typo
# that would otherwise be silently dropped — reject it rather than ignore it.
_KNOWN_CONTRACT_KEYS = frozenset({"outputs"})


def _validate_types(dataset: str, value: Any) -> None:
    """Reject a ``types`` spec that isn't a non-empty {column: type} string map."""
    if not isinstance(value, dict) or not value:
        raise ValueError(
            f'contract output "{dataset}": "types" must be a non-empty object mapping '
            "column name to expected type"
        )
    for column, expected in value.items():
        if not isinstance(column, str) or not column.strip():
            raise ValueError(
                f'contract output "{dataset}": "types" keys must be non-empty strings'
            )
        if not isinstance(expected, str) or not expected.strip():
            raise ValueError(
                f'contract output "{dataset}": "types"[{column!r}] must be a '
                "non-empty string"
            )


def _validate_output_spec(dataset: str, spec: dict[str, Any]) -> dict[str, Any]:
    """Reject degenerate spec values with a precise message (no DSS work here)."""
    unknown = sorted(k for k in spec if k not in _KNOWN_OUTPUT_SPEC_KEYS)
    if unknown:
        raise ValueError(
            f'contract output "{dataset}": unknown key(s) {unknown}. Allowed keys: '
            f"{sorted(_KNOWN_OUTPUT_SPEC_KEYS)}"
        )
    if "columns" in spec:
        _validate_string_list(dataset, "columns", spec["columns"])
    if "not_blank" in spec:
        _validate_string_list(dataset, "not_blank", spec["not_blank"])
    if "types" in spec:
        _validate_types(dataset, spec["types"])
    if spec.get("min_rows") is not None:
        min_rows = spec["min_rows"]
        # A numeric string (or float/bool) is rejected outright, never coerced.
        if isinstance(min_rows, bool) or not isinstance(min_rows, int) or min_rows < 0:
            raise ValueError(
                f'contract output "{dataset}": "min_rows" must be a non-negative '
                f"integer, got {min_rows!r}"
            )
    return spec


def normalize_contract(contract: Any) -> dict[str, Any]:
    """Validate + normalize a delegated-output contract into ``{"outputs": {name: spec}}``.

    Accepts the documented list form ``{"outputs": [{"dataset": ..., "columns": ...,
    "min_rows": ...}]}`` and the equivalent mapping form. Every degenerate value is
    rejected here, before any DSS work: an unknown *top-level* key (only ``outputs``
    is consumed — a misplaced top-level ``min_rows`` would otherwise be silently
    dropped); an empty ``outputs``; an empty or duplicate
    dataset name; an *unknown* spec key (a ``min_row`` typo would otherwise silently
    drop the assertion — only ``columns``/``not_blank``/``min_rows``/``types`` are
    allowed); a non-integer or negative ``min_rows`` (a numeric string is rejected,
    not coerced); a non-list or empty-string-bearing ``columns`` / ``not_blank``;
    and a ``types`` that isn't a non-empty {column: type} map of non-empty strings.
    Raises ``ValueError`` with a clear message on anything malformed.
    """
    if not isinstance(contract, dict):
        raise ValueError("contract must be a JSON object")
    unknown_top = sorted(k for k in contract if k not in _KNOWN_CONTRACT_KEYS)
    if unknown_top:
        raise ValueError(
            f"contract has unknown top-level key(s) {unknown_top}. Allowed keys: "
            f"{sorted(_KNOWN_CONTRACT_KEYS)} (per-output assertions like "
            f'"min_rows"/"columns" belong inside each "outputs" entry)'
        )
    if "outputs" not in contract:
        raise ValueError('contract must contain an "outputs" key')
    outputs = contract["outputs"]
    normalized: dict[str, Any] = {}
    if isinstance(outputs, list):
        if not outputs:
            raise ValueError('contract "outputs" list must not be empty')
        for i, entry in enumerate(outputs):
            if not isinstance(entry, dict):
                raise ValueError(f"contract outputs[{i}] must be an object")
            dataset = entry.get("dataset")
            if not isinstance(dataset, str) or not dataset.strip():
                raise ValueError(f'contract outputs[{i}] must have a non-empty "dataset" field')
            dataset = dataset.strip()
            if dataset in normalized:
                raise ValueError(f'contract has a duplicate output dataset "{dataset}"')
            normalized[dataset] = _validate_output_spec(
                dataset, {k: v for k, v in entry.items() if k != "dataset"}
            )
    elif isinstance(outputs, dict):
        if not outputs:
            raise ValueError('contract "outputs" object must not be empty')
        for name, spec in outputs.items():
            if not isinstance(name, str) or not name.strip():
                raise ValueError("contract output names must be non-empty strings")
            clean_name = name.strip()
            if not isinstance(spec, dict):
                raise ValueError(f'contract output "{clean_name}" must map to an object')
            if clean_name in normalized:
                raise ValueError(f'contract has a duplicate output dataset "{clean_name}"')
            normalized[clean_name] = _validate_output_spec(clean_name, spec)
    else:
        raise ValueError('contract "outputs" must be a list or an object')
    return {"outputs": normalized}


def _contract_types_check(dataset: str, spec: dict[str, Any], columns: list[dict[str, Any]]) -> Check:
    by_name = {c.get("name"): c.get("type") for c in columns}
    mismatches = [
        f"{name}: expected {typ}, got {by_name.get(name)}"
        for name, typ in spec.get("types", {}).items()
        if by_name.get(name) != typ
    ]
    return _verdict(
        f"contract_types:{dataset}",
        bucket="evidence",
        problems=[f"Type mismatches: {'; '.join(mismatches)}"] if mismatches else [],
        fix=(
            f'Delegate to Cobuild: "Fix the column type mismatches on output {dataset} to match '
            'the contract, then rebuild."'
        ),
    )


def _contract_min_rows_check(proj, dataset: str, spec: dict[str, Any]) -> Check:
    min_rows = spec["min_rows"]
    # A raising metric read is unreadable evidence, never a measured zero: fabricating
    # count=0 would report a *fail* asserting the dataset is empty — a claim the audit
    # cannot back. Propagate it as an ``error`` (blocks the gate, marks the audit
    # incomplete) so the shortfall verdict only ever rests on a real count.
    try:
        count = _terminal_row_count(proj, dataset)
    except Exception as exc:
        return _error(
            f"contract_min_rows:{dataset}",
            bucket="evidence",
            severity=FAIL,
            detail=(
                f"cannot verify the min_rows contract for {dataset} — record-count "
                f"evidence unreadable: {exc}"
            ),
        )
    short = count < min_rows
    return _verdict(
        f"contract_min_rows:{dataset}",
        bucket="evidence",
        problems=[f"Expected at least {min_rows} rows, got {count}"] if short else [],
        fix=(
            f"Build/inspect {dataset} — it has fewer rows than the contract requires. Use the "
            "build_datasets tool, or delegate to Cobuild to investigate the shortfall."
        ),
    )


def _contract_not_blank_check(proj, dataset: str, spec: dict[str, Any], columns: list[dict[str, Any]]) -> Check:
    rows = _dataset_sample(proj, dataset, columns, MAX_SAMPLE_ROWS)
    blank_cols = [c for c in spec["not_blank"] if any(_is_blank(r.get(c)) for r in rows)]
    return _listing(
        f"contract_not_blank:{dataset}",
        bucket="evidence",
        items=blank_cols,
        problem="Columns contain blanks in sample: {names}",
        fix=(
            'Delegate to Cobuild: "These columns are expected non-blank but contain blanks '
            '({names}); fix the upstream logic and rebuild."'
        ),
    )


def _contract_units(actx: AuditContext, contract: dict[str, Any]) -> list[CheckUnit]:
    proj, datasets = actx.proj, actx.datasets
    units: list[CheckUnit] = []
    for dataset, spec in contract["outputs"].items():
        if dataset not in datasets:
            units.append(
                (
                    f"contract_output_exists:{dataset}",
                    "evidence",
                    FAIL,
                    (
                        lambda ds=dataset: _bad(
                            f"contract_output_exists:{ds}",
                            bucket="evidence",
                            detail=f"Contract output dataset does not exist: {ds}",
                            fix=(
                                f'Delegate to Cobuild: "Create and build the expected contract '
                                f"output dataset '{ds}', or correct the contract output name.\""
                            ),
                        )
                    ),
                )
            )
            continue

        cols_holder: dict[str, list[dict[str, Any]]] = {}

        def columns(ds=dataset, h=cols_holder) -> list[dict[str, Any]]:
            if "v" not in h:
                h["v"] = _dataset_columns(proj, ds)
            return h["v"]

        units.append(
            (
                f"contract_columns:{dataset}",
                "evidence",
                FAIL,
                (
                    lambda ds=dataset, sp=spec, cf=columns: _listing(
                        f"contract_columns:{ds}",
                        bucket="evidence",
                        items=[c for c in sp.get("columns", []) if c not in {col.get("name") for col in cf()}],
                        problem="Missing expected columns: {names}",
                        fix=(
                            'Delegate to Cobuild: "Output is missing expected columns ({names}); '
                            'add them via the upstream recipe and rebuild."'
                        ),
                    )
                ),
            )
        )
        units.append(
            (
                f"contract_types:{dataset}",
                "evidence",
                FAIL,
                lambda ds=dataset, sp=spec, cf=columns: _contract_types_check(ds, sp, cf()),
            )
        )
        if spec.get("min_rows") is not None:
            units.append(
                (
                    f"contract_min_rows:{dataset}",
                    "evidence",
                    FAIL,
                    lambda ds=dataset, sp=spec: _contract_min_rows_check(proj, ds, sp),
                )
            )
        if spec.get("not_blank"):
            units.append(
                (
                    f"contract_not_blank:{dataset}",
                    "evidence",
                    FAIL,
                    lambda ds=dataset, sp=spec, cf=columns: _contract_not_blank_check(proj, ds, sp, cf()),
                )
            )
    return units


def run_contract_checks(actx: AuditContext, normalized_contract: dict[str, Any]) -> list[Check]:
    """Run the contract assertions (already normalized via :func:`normalize_contract`)."""
    return _collect(_contract_units(actx, normalized_contract))


# --------------------------------------------------------------------------- #
# Orchestration + payload
# --------------------------------------------------------------------------- #
def validate_buckets(buckets: list[str] | None) -> list[str]:
    """Validate + canonicalize the requested bucket names; default is all four."""
    if buckets is None:
        return list(AUDIT_BUCKETS_ORDER)
    selected: set[str] = set()
    for b in buckets:
        name = str(b).strip().lower()
        if name not in AUDIT_BUCKETS:
            raise ValueError(
                f"Invalid bucket '{b}'. Allowed buckets: {sorted(AUDIT_BUCKETS)}"
            )
        selected.add(name)
    if not selected:
        raise ValueError(f"'buckets' must include at least one of {sorted(AUDIT_BUCKETS)}")
    return [b for b in AUDIT_BUCKETS_ORDER if b in selected]


# The audit only inspects flow-level objects; the scope claim is stated on every
# payload (and in the tool docstring) so the verdict is never read as broader.
AUDIT_SCOPE = "flow-level audit (datasets, recipes, zones, wiki)"


def build_payload(project_key: str, checks: list[Check], inventory: dict[str, Any]) -> dict[str, Any]:
    """Assemble the lean verdict payload.

    Only non-``pass`` checks are itemized (dense mode); the full pass list is
    emitted only when every check passed. A ``skip`` (a WARN check that could not
    run) never affects the score or blocks the gate. An ``error`` (a FAIL check
    whose evidence could not be read) blocks the gate, lowers the score, and marks
    the payload ``incomplete``.
    """
    failed = [c for c in checks if c.status == FAIL]
    errored = [c for c in checks if c.status == ERROR]
    warnings = sum(1 for c in checks if c.status == WARN)
    skipped = sum(1 for c in checks if c.status == SKIP)
    scored = [c for c in checks if c.status in {PASS, FAIL, WARN, ERROR}]
    passed_count = sum(1 for c in scored if c.status == PASS)
    score = round(passed_count / len(scored), 3) if scored else 1.0

    if failed or errored:
        parts = []
        if failed:
            parts.append(f"{len(failed)} check(s) failed")
        if errored:
            parts.append(f"{len(errored)} check(s) errored (evidence unreadable)")
        summary = "; ".join(parts)
    elif warnings:
        summary = f"passed with {warnings} warning(s)"
    else:
        summary = "passed"
    if skipped:
        summary += f"; {skipped} check(s) skipped"

    counts: dict[str, int] = {}
    for c in checks:
        counts[c.status] = counts.get(c.status, 0) + 1

    issues = [c for c in checks if c.status != PASS]
    checks_block: dict[str, Any] = {"counts": counts}
    if issues:
        checks_block["issues"] = columnar(
            [asdict(c) for c in issues],
            ["id", "bucket", "severity", "status", "detail", "fix"],
        )
    else:
        checks_block["passed_checks"] = [c.id for c in checks]

    payload: dict[str, Any] = {
        "project_key": project_key,
        "scope": AUDIT_SCOPE,
        "passed": not failed and not errored,
        "score": score,
        "summary": summary,
        "checks": checks_block,
        "inventory": inventory,
    }
    if errored:
        payload["incomplete"] = True
        payload["errors"] = len(errored)
    return payload


def run_audit(
    proj,
    project_key: str,
    *,
    contract: dict[str, Any] | None = None,
    buckets: list[str] | None = None,
) -> dict[str, Any]:
    """Run the selected buckets (plus contract, if given) and return the payload.

    The gate fails only on ``fail``-severity checks; warnings are advisory. Fewer
    ``buckets`` means less work — an agent can re-check one area without paying for
    the flow-consistency check and metric reads. A ``contract`` runs only when
    passed. Convenience wrapper over :func:`load_context` / :func:`run_bucket` /
    :func:`run_contract_checks` / :func:`build_payload`.
    """
    selected = validate_buckets(buckets)
    normalized_contract = normalize_contract(contract) if contract is not None else None
    actx = load_context(proj, project_key)
    checks: list[Check] = []
    for bucket in selected:
        checks += run_bucket(actx, bucket)
    if normalized_contract is not None:
        checks += run_contract_checks(actx, normalized_contract)
    return build_payload(project_key, checks, actx.inventory)
