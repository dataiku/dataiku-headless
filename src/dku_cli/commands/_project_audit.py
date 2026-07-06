"""Read-only project reviewability audit — the finish gate for agent-built flows.

Answers one question: can an SME open this DSS project cold, follow the flow,
see what changed, and trust the result? Every check is read-only and, when it
fails, names the offending objects and the exact `dku ...` command that fixes
them. Nothing here mutates DSS or auto-writes descriptions.

The verdict spans four buckets (structure, documentation, evidence,
maintainability) and two severities:

* ``fail``  — a reviewer cannot trust or operate the project.
* ``warn``  — suspicious; usually worth fixing before delivery.

The command body in ``project.py`` builds the ``dataikuapi`` project handle and
hands it to :func:`run_audit`; everything below works off that one handle in a
single in-process pass (no subprocess fan-out).
"""

from __future__ import annotations

import contextlib
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

FAIL = "fail"
WARN = "warn"

MAX_SAMPLE_ROWS = 100

CODE_RECIPE_TYPES = {"python", "r", "shell", "pyspark", "sparkr", "spark_scala"}

# Editor/default object names DSS hands out when nobody renamed the object.
LAZY_NAME = re.compile(r"(_copy(_\d+)?)$|^(compute_|new_dataset|untitled)", re.I)
# Scaffolding/reference names that must not survive as disconnected datasets.
REFERENCE_NAME = re.compile(
    r"(^expected_|^reference_|^ref_|^tmp_|_expected$|_actual$)", re.I
)
# Identifier columns whose blanks are almost always a parsing/join bug. Kept to
# id/key spellings — a blank generic `*name` is too often legitimate to fail on.
KEY_COLUMN_NAME = re.compile(r"(^id$|_id$|^key$|_key$)", re.I)

# Matched against wiki heading lines only (see HEADING_LINE), so a stray "this
# source was flaky" sentence in the prose doesn't count as a Sources section.
RUNBOOK_SECTIONS = {
    "purpose": ("purpose", "overview", "goal", "objective"),
    "sources": ("source", "input"),
}

# A markdown heading line (`#`..`######`) or a bold-label line (`**Sources:**`).
HEADING_LINE = re.compile(r"^\s*(#{1,6}\s|\*\*[^*]+\*\*\s*:?\s*$)")


@dataclass
class Check:
    id: str
    status: str
    bucket: str
    severity: str
    detail: str = ""
    fix: str = ""


def _ok(id: str, *, bucket: str, severity: str = FAIL) -> Check:
    return Check(id=id, status="pass", bucket=bucket, severity=severity)


def _bad(
    id: str, *, bucket: str, detail: str, severity: str = FAIL, fix: str = ""
) -> Check:
    return Check(
        id=id, status=severity, bucket=bucket, severity=severity, detail=detail, fix=fix
    )


def _verdict(
    id: str, *, bucket: str, problems: list[str], severity: str = FAIL, fix: str = ""
) -> Check:
    if problems:
        return _bad(
            id, bucket=bucket, detail="; ".join(problems), severity=severity, fix=fix
        )
    return _ok(id, bucket=bucket, severity=severity)


def _first(items: list[str]) -> str:
    return items[0] if items else ""


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


# --- text quality ------------------------------------------------------------
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


def _describe_problems(
    missing: list[str], described: dict[str, str], label: str
) -> list[str]:
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


# --- graph -------------------------------------------------------------------
def graph_sets(
    nodes: dict[str, Any], datasets: set[str]
) -> tuple[set[str], set[str], set[str]]:
    """(inputs, outputs, terminal) dataset sets derived from recipe nodes."""
    inputs: set[str] = set()
    outputs: set[str] = set()
    for node in nodes.values():
        if node.get("type") != "RUNNABLE_RECIPE":
            continue
        inputs.update(p for p in node.get("predecessors", []) if p in datasets)
        outputs.update(s for s in node.get("successors", []) if s in datasets)
    return inputs, outputs, outputs - inputs


# --- value helpers -----------------------------------------------------------
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


def load_json_arg(value: str | None) -> dict[str, Any]:
    """Load a JSON arg from a literal string, ``@file.json``, or ``-`` (stdin)."""
    if not value:
        return {}
    if value == "-":
        import sys

        return json.loads(sys.stdin.read())
    if value.startswith("@"):
        return json.loads(Path(value[1:]).read_text())
    return json.loads(value)


# --- DSS reads (kept tiny so per-object failures stay local) -----------------
def _dataset_metadata(proj, name: str) -> dict[str, Any]:
    return proj.get_dataset(name).get_metadata()


def _recipe_metadata(proj, name: str) -> dict[str, Any]:
    return proj.get_recipe(name).get_settings().get_recipe_raw_definition()


def _dataset_columns(proj, name: str) -> list[dict[str, Any]]:
    return proj.get_dataset(name).get_definition().get("schema", {}).get("columns", [])


def _has_documented_column(proj, name: str) -> bool:
    """True if any column carries a description (the schema `comment` field)."""
    try:
        columns = _dataset_columns(proj, name)
    except Exception:
        return True  # unreadable schema is the row-count check's problem, not this one
    return not columns or any(c.get("comment", "").strip() for c in columns)


def _dataset_sample(
    proj, name: str, columns: list[dict[str, Any]], max_rows: int
) -> list[dict[str, Any]]:
    names = [c.get("name", "") for c in columns]
    rows: list[dict[str, Any]] = []
    for i, row in enumerate(proj.get_dataset(name).iter_rows()):
        if i >= max_rows:
            break
        rows.append(dict(zip(names, row, strict=False)))
    return rows


def _terminal_row_count(proj, name: str) -> int:
    """Cached COUNT_RECORDS for a terminal output (keeps the audit read-only).

    Raises when no cached value exists; callers treat that as "unknown" and point
    the user at `dku dataset info --recompute` for a fresh number.
    """
    metrics = proj.get_dataset(name).get_last_metric_values()
    return int(metrics.get_global_value("records:COUNT_RECORDS"))


def flow_check_clean(proj) -> tuple[bool, str]:
    """Run DSS flow consistency check; return (clean, first error message)."""
    flow = proj.get_flow()
    tool = flow.start_tool("CHECK_CONSISTENCY")
    try:
        tool.update(
            {
                "recheckAll": True,
                "datasets": {"consistencyWithData": True},
                "recipes": {"schemaConsistency": True, "otherExpensiveChecks": False},
            }
        ).wait_for_result()
        state = tool.get_state()
        for node_id, node_state in state.get("stateByNode", {}).items():
            for key in ("recipeCheckResult", "datasetCheckResult"):
                for msg in node_state.get(key, {}).get("messages", []):
                    if msg.get("isFatal") or msg.get("severity") in ("ERROR", "FATAL"):
                        return (
                            False,
                            f"{node_id}: {msg.get('message', msg.get('code', ''))}",
                        )
        return True, ""
    finally:
        with contextlib.suppress(Exception):
            tool.stop()


# --- checks: structure -------------------------------------------------------
def _structure_checks(
    project: str,
    datasets: set[str],
    recipe_names: set[str],
    inputs: set[str],
    outputs: set[str],
    terminal: set[str],
    zones: list[dict[str, Any]],
) -> list[Check]:
    orphans = sorted(datasets - inputs - outputs)
    bad_refs = sorted(n for n in datasets if REFERENCE_NAME.search(n) and n in orphans)
    nondefault_zones = [z for z in zones if not _is_default(z)]
    default_zone = next((z for z in zones if _is_default(z)), None)
    repurposed = default_zone is not None and _default_repurposed(default_zone)
    organizing = bool(nondefault_zones) or repurposed
    default_members = _default_members(zones, datasets | recipe_names)
    checks = [
        _listing(
            "no_orphan_datasets",
            bucket="structure",
            items=orphans,
            problem="Datasets not connected to any recipe: {names}",
            fix="delete, connect, or document reference datasets: {names}",
        ),
        _listing(
            "reference_dataset_policy",
            bucket="structure",
            severity=WARN,
            items=bad_refs,
            problem="Reference/tmp-looking datasets are disconnected: {names}",
            fix="connect them to the flow, document them, or remove them",
        ),
    ]
    if len(recipe_names) > 3 or len(datasets) > 5:
        checks.append(
            _verdict(
                "flow_zones_present",
                bucket="structure",
                severity=WARN,
                problems=["Non-trivial flow has no flow zones"]
                if not organizing
                else [],
                fix=f"dku flow create-zone '<stage>' -P {project}",
            )
        )
    # Empty NAMED zones are leftover scaffolding (e.g. after moving their items
    # elsewhere) — delete them.
    empty_zones = sorted(
        z.get("name", "") for z in nondefault_zones if not z.get("itemCount")
    )
    checks.append(
        _listing(
            "empty_zones",
            bucket="structure",
            severity=WARN,
            items=empty_zones,
            problem="Named zones with no items (leftover scaffolding): {names}",
            fix=f"dku flow delete-zone '{_first(empty_zones)}' -P {project}",
        )
    )
    # The default zone can't be deleted, so an empty one is a stranded husk left
    # behind after its objects were moved into named zones. The author should have
    # adopted it as a real stage (rename + keep objects in it), not orphaned it.
    # Only a concern once named zones exist — otherwise the default zone
    # legitimately holds the whole flow.
    if nondefault_zones and not default_members:
        checks.append(
            _verdict(
                "default_zone_empty",
                bucket="structure",
                severity=WARN,
                problems=[
                    "The default flow zone is empty — its objects were moved into "
                    "named zones, stranding it. The default zone can't be deleted; "
                    "rename it to a real stage and move that stage's objects into it."
                ],
                fix=f"dku flow set-zone default --name '<stage>' -P {project}",
            )
        )
    # Zone coverage: objects still sitting in the anonymous default bucket aren't
    # organized. A repurposed (renamed) default zone is itself a real stage, so its
    # members count as covered. Tiny unzoned flows are not nagged.
    if organizing:
        loose = [] if repurposed else sorted(default_members)
        moves = " ".join(loose[:5])
        zone_fix = f"dku flow move {moves} --zone '<stage>' --type AUTO -P {project}"
        checks.append(
            _listing(
                "zone_coverage",
                bucket="structure",
                severity=WARN,
                items=loose,
                problem="Datasets left outside the named zones: {names}",
                fix=zone_fix,
            )
        )
    return checks


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


# --- checks: documentation ---------------------------------------------------
def _documentation_checks(
    project: str,
    proj,
    targets: set[str],
    recipes: list[dict[str, Any]],
    zones: list[dict[str, Any]],
    wiki_bodies: list[str] | None,
    terminal: set[str],
) -> list[Check]:
    out_problems, out_first = _description_scan(
        _dataset_metadata, proj, sorted(terminal), "Output datasets"
    )
    src_problems, src_first = _description_scan(
        _dataset_metadata, proj, sorted(targets - terminal), "Source datasets"
    )
    ds_fix = (
        f"dku dataset set-metadata {out_first or src_first} "
        f"--description '...' -P {project}"
    )
    undoc_cols = sorted(t for t in terminal if not _has_documented_column(proj, t))
    col = undoc_cols[0] if undoc_cols else "COL"
    col_fix = f"dku dataset set-column-description {col} <col> '...' -P {project}"
    rec_names = sorted(r["name"] for r in recipes if r.get("name"))
    rec_problems, rec_first = _description_scan(
        _recipe_metadata, proj, rec_names, "Recipes"
    )
    rec_fix = f"dku recipe set-metadata {rec_first} --short-desc '...' -P {project}"
    undescribed = _undescribed_zones(zones, targets | set(rec_names))
    zone = _first(undescribed)
    zone_fix = f"dku flow set-zone '{zone}' --short-desc '...' -P {project}"
    checks = [
        _verdict(
            "datasets_have_descriptions",
            bucket="documentation",
            problems=out_problems,
            fix=ds_fix,
        ),
        _verdict(
            "source_datasets_have_descriptions",
            bucket="documentation",
            severity=WARN,
            problems=src_problems,
            fix=ds_fix,
        ),
        _verdict(
            "recipes_have_descriptions",
            bucket="documentation",
            severity=WARN,
            problems=rec_problems,
            fix=rec_fix,
        ),
        _listing(
            "zones_have_short_desc",
            bucket="documentation",
            severity=WARN,
            items=undescribed,
            problem="Named zones without short descriptions: {names}",
            fix=zone_fix,
        ),
        _listing(
            "terminal_columns_documented",
            bucket="documentation",
            severity=WARN,
            items=undoc_cols,
            problem="Terminal outputs with no documented columns: {names}",
            fix=col_fix,
        ),
        _flow_visible_description_check(
            project,
            proj,
            targets - terminal,
            terminal,
            recipes,
            zones,
        ),
    ]
    if wiki_bodies is None:
        checks.append(
            _bad(
                "has_wiki",
                bucket="documentation",
                severity=WARN,
                detail="No wiki articles found",
                fix=f"dku wiki create 'Runbook' --body @runbook.md -P {project}",
            )
        )
    else:
        checks.append(_ok("has_wiki", bucket="documentation"))
        headings = "\n".join(
            line
            for body in wiki_bodies
            for line in body.splitlines()
            if HEADING_LINE.match(line)
        ).lower()
        missing = [
            name
            for name, kws in RUNBOOK_SECTIONS.items()
            if not any(k in headings for k in kws)
        ]
        runbook_fix = f"add a purpose and sources heading to the wiki -P {project}"
        checks.append(
            _listing(
                "wiki_runbook",
                bucket="documentation",
                severity=WARN,
                items=missing,
                problem="Wiki is missing runbook headings: {names}",
                fix=runbook_fix,
            )
        )
    return checks


def _description_scan(
    reader, proj, names: list[str], label: str
) -> tuple[list[str], str]:
    """Read each object's description via ``reader``; return (problems, first name)."""
    missing: list[str] = []
    described: dict[str, str] = {}
    for name in names:
        try:
            meta = reader(proj, name)
        except Exception:
            continue
        text = (meta.get("description") or meta.get("shortDesc") or "").strip()
        if text:
            described[name] = text
        else:
            missing.append(name)
    return _describe_problems(missing, described, label), _first(names)


def _short_desc_scan(
    reader, proj, names: list[str], label: str
) -> tuple[list[str], str]:
    missing: list[str] = []
    described: dict[str, str] = {}
    for name in names:
        try:
            meta = reader(proj, name)
        except Exception:
            continue
        text = (meta.get("shortDesc") or "").strip()
        if text:
            described[name] = text
        else:
            missing.append(name)
    return _describe_problems(missing, described, label), _first(names)


def _flow_visible_description_check(
    project: str,
    proj,
    sources: set[str],
    terminal: set[str],
    recipes: list[dict[str, Any]],
    zones: list[dict[str, Any]],
) -> Check:
    # Datasets have no `shortDesc` in DSS — only `description`, which is what the
    # flow tile renders. Recipes and zones do carry a real `shortDesc`.
    terminal_problems, first_terminal = _description_scan(
        _dataset_metadata, proj, sorted(terminal), "Terminal datasets"
    )
    source_problems, first_source = _description_scan(
        _dataset_metadata, proj, sorted(sources), "Source datasets"
    )
    recipe_names = sorted(r["name"] for r in recipes if r.get("name"))
    recipe_problems, first_recipe = _short_desc_scan(
        _recipe_metadata, proj, recipe_names, "Recipes"
    )
    zone_missing = _undescribed_zones(zones, sources | terminal | set(recipe_names))
    zone_problems = (
        [f"Named zones without a short description: {', '.join(sorted(zone_missing))}"]
        if zone_missing
        else []
    )
    problems = terminal_problems + source_problems + recipe_problems + zone_problems
    if not problems:
        return _ok("flow_visible_descriptions", bucket="documentation", severity=WARN)

    first = first_terminal or first_source
    if terminal_problems:
        fix = f"dku dataset set-metadata {first} --description '...' -P {project}"
        severity = FAIL
    elif source_problems:
        fix = f"dku dataset set-metadata {first} --description '...' -P {project}"
        severity = WARN
    elif recipe_problems:
        fix = f"dku recipe set-metadata {first_recipe} --short-desc '...' -P {project}"
        severity = WARN
    else:
        fix = (
            f"dku flow set-zone '{_first(zone_missing)}' "
            f"--short-desc '...' -P {project}"
        )
        severity = WARN
    return _bad(
        "flow_visible_descriptions",
        bucket="documentation",
        detail="; ".join(problems),
        severity=severity,
        fix=fix,
    )


# --- checks: evidence --------------------------------------------------------
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


def _evidence_checks(project: str, proj, terminal: set[str]) -> list[Check]:
    empty: list[str] = []
    unknown_count: list[str] = []
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

        # One bad object must not abort the sweep — record its smells if it
        # reads, skip it otherwise (it still shows up via the row-count check).
        try:
            columns = _dataset_columns(proj, dataset)
            rows = (
                _dataset_sample(proj, dataset, columns, MAX_SAMPLE_ROWS)
                if columns
                else []
            )
        except Exception:
            rows = []
        if rows:
            _scan_column_smells(dataset, columns, rows, smells)

    build_fix = (
        f"dku job run --type RECURSIVE_BUILD --auto-update-schema --wait -P {project}"
    )
    count_fix = f"dku dataset info {_first(unknown_count)} -P {project} --recompute"
    return [
        _listing(
            "terminal_outputs_built",
            bucket="evidence",
            items=empty,
            problem="Terminal outputs with zero rows: {names}",
            fix=build_fix,
        ),
        _listing(
            "terminal_row_counts",
            bucket="evidence",
            severity=WARN,
            items=unknown_count,
            problem="Could not read a recomputed row count for: {names}",
            fix=count_fix,
        ),
        _listing(
            "all_null_columns",
            bucket="evidence",
            severity=WARN,
            items=smells["all_null"],
            problem="Terminal columns entirely blank in sample: {names}",
            fix="inspect the formula/prepare steps that feed them, then rebuild",
        ),
        _listing(
            "blank_key_columns",
            bucket="evidence",
            severity=WARN,
            items=smells["blank_keys"],
            problem="Likely key columns contain blanks in sample: {names}",
            fix="fix upstream parsing/join logic before delivery",
        ),
        _listing(
            "type_smells",
            bucket="evidence",
            severity=WARN,
            items=smells["numeric_strings"],
            problem="Numeric-looking string columns: {names}",
            fix="run infer-types or set the schema, then rebuild and recheck",
        ),
        _listing(
            "sample_diversity",
            bucket="evidence",
            severity=WARN,
            items=smells["one_value"],
            problem="String columns collapse to a single sampled value: {names}",
            fix="confirm the collapse is expected or document it in the wiki",
        ),
    ]


# --- checks: maintainability -------------------------------------------------
def _maintainability_checks(
    project: str, recipes: list[dict[str, Any]], terminal: set[str]
) -> list[Check]:
    code_recipes = sorted(
        r["name"]
        for r in recipes
        if str(r.get("type", "")).lower() in CODE_RECIPE_TYPES
    )
    lazy_recipes = sorted(
        r["name"] for r in recipes if r.get("name") and LAZY_NAME.search(r["name"])
    )
    lazy_terminals = sorted(n for n in terminal if LAZY_NAME.search(n))
    return [
        _listing(
            "visual_first",
            bucket="maintainability",
            severity=WARN,
            items=code_recipes,
            problem="Code recipes present: {names}",
            fix="use visual recipes unless the capability is genuinely absent",
        ),
        _listing(
            "recipe_naming",
            bucket="maintainability",
            severity=WARN,
            items=lazy_recipes,
            problem="Recipes with default/auto names: {names}",
            fix="rename recipes to an action verb or clear transformation noun",
        ),
        _listing(
            "dataset_naming",
            bucket="maintainability",
            severity=WARN,
            items=lazy_terminals,
            problem="Terminal datasets with default/auto names: {names}",
            fix=f"rename outputs to business names in project {project}",
        ),
    ]


# --- checks: contract --------------------------------------------------------
def _contract_checks(proj, contract: dict[str, Any], datasets: set[str]) -> list[Check]:
    checks: list[Check] = []
    for dataset, spec in contract.get("outputs", {}).items():
        if dataset not in datasets:
            checks.append(
                _bad(
                    f"contract_output_exists:{dataset}",
                    bucket="evidence",
                    detail=f"Contract output dataset does not exist: {dataset}",
                    fix=(
                        "create/build the expected output dataset or correct "
                        f"--contract output name: {dataset}"
                    ),
                )
            )
            continue

        columns = _dataset_columns(proj, dataset)
        by_name = {c.get("name"): c.get("type") for c in columns}

        missing_cols = [c for c in spec.get("columns", []) if c not in by_name]
        checks.append(
            _listing(
                f"contract_columns:{dataset}",
                bucket="evidence",
                items=missing_cols,
                problem="Missing expected columns: {names}",
            )
        )

        mismatches = [
            f"{name}: expected {typ}, got {by_name.get(name)}"
            for name, typ in spec.get("types", {}).items()
            if by_name.get(name) != typ
        ]
        checks.append(
            _verdict(
                f"contract_types:{dataset}",
                bucket="evidence",
                problems=[f"Type mismatches: {'; '.join(mismatches)}"]
                if mismatches
                else [],
            )
        )

        if spec.get("min_rows") is not None:
            try:
                count = _terminal_row_count(proj, dataset) or 0
            except Exception:
                count = 0
            short = [f"Expected at least {spec['min_rows']} rows, got {count}"]
            checks.append(
                _verdict(
                    f"contract_min_rows:{dataset}",
                    bucket="evidence",
                    problems=short if count < spec["min_rows"] else [],
                )
            )

        if spec.get("not_blank"):
            rows = _dataset_sample(proj, dataset, columns, MAX_SAMPLE_ROWS)
            blank_cols = [
                c for c in spec["not_blank"] if any(_is_blank(r.get(c)) for r in rows)
            ]
            checks.append(
                _listing(
                    f"contract_not_blank:{dataset}",
                    bucket="evidence",
                    items=blank_cols,
                    problem="Columns contain blanks in sample: {names}",
                )
            )
    return checks


# --- orchestration -----------------------------------------------------------
def run_audit(
    proj,
    project: str,
    *,
    contract: dict[str, Any] | None = None,
    buckets: set[str] | None = None,
) -> dict[str, Any]:
    """Run the checks against ``proj`` and return the verdict payload.

    The gate fails only on ``fail``-severity checks; warnings are advisory and
    always shown but never block. ``buckets`` (lower-case names) restricts which
    check groups run — selecting fewer skips their work, so an agent can re-check
    one area without paying for the flow consistency check and metric reads.
    """
    run = (lambda b: True) if buckets is None else (lambda b: b in buckets)
    datasets = {d.get("name", d.get("id", "")) for d in proj.list_datasets()}
    recipes = [
        {"name": r.get("name", ""), "type": r.get("type", "")}
        for r in proj.list_recipes()
    ]
    recipe_names = {r["name"] for r in recipes if r.get("name")}
    nodes = proj.get_flow().get_graph().nodes
    zones = _zone_dicts(proj)

    inputs, outputs, terminal = graph_sets(nodes, datasets)

    checks: list[Check] = []
    if run("structure"):
        checks += _structure_checks(
            project, datasets, recipe_names, inputs, outputs, terminal, zones
        )
    if run("documentation"):
        wiki_bodies = _wiki_bodies(proj)
        checks += _documentation_checks(
            project, proj, datasets, recipes, zones, wiki_bodies, terminal
        )
    if run("evidence"):
        clean, message = flow_check_clean(proj)
        checks.append(
            _verdict(
                "flow_check_clean",
                bucket="evidence",
                problems=[message] if not clean else [],
                fix=f"dku flow check -P {project}" if not clean else "",
            )
        )
        checks += _evidence_checks(project, proj, terminal)
        if contract:
            checks += _contract_checks(proj, contract, datasets)
    if run("maintainability"):
        checks += _maintainability_checks(project, recipes, terminal)

    inventory = {
        "datasets": len(datasets),
        "recipes": len(recipes),
        "zones": len([z for z in zones if _is_real_zone(z)]),
        "terminal_datasets": sorted(terminal),
        "source_datasets": sorted(inputs - outputs),
        "orphan_datasets": sorted(datasets - inputs - outputs),
    }
    return _payload(checks, inventory=inventory)


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


def _payload(checks: list[Check], *, inventory: dict[str, Any]) -> dict[str, Any]:
    failed = [c for c in checks if c.status == FAIL]
    warnings = sum(1 for c in checks if c.status == WARN)
    scored = [c for c in checks if c.status in {"pass", FAIL, WARN}]
    passed_count = sum(1 for c in scored if c.status == "pass")
    score = round(passed_count / len(scored), 3) if scored else 1.0
    if failed:
        summary = f"{len(failed)} check(s) failed"
    elif warnings:
        summary = f"passed with {warnings} warning(s)"
    else:
        summary = "passed"
    return {
        "passed": not failed,
        "summary": summary,
        "score": score,
        "checks": [asdict(c) for c in checks],
        "inventory": inventory,
    }
