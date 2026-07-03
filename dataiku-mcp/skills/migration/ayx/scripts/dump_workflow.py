#!/usr/bin/env python3
"""Dump an Alteryx `.yxmd` (or extracted `.yxwz`/`.yxzp` inner file) as a Phase-1
inventory.

Emits the tool list + the connection DAG (each tool's upstream inputs and downstream
outputs) as the migration-skill inventory table — the mechanical half of Phase 1. You
still fill the "What It Does" and "Migratable?" columns by reading each tool's config.

    uv run python scripts/dump_workflow.py workflow.yxmd          # markdown to stdout
    uv run python scripts/dump_workflow.py workflow.yxmd -o inv.md

Notes:
- Presentation-only tools (TextBox, BrowseV2, ToolContainer) are flagged "ignore" —
  they carry no flow logic (see ayx/overview.md § Non-migratable patterns). Their TEXT
  is still dumped in the ANNOTATIONS section: it often carries migration intelligence
  (source-table lists, prod-vs-test markers, delivery changelogs).
- Predictive Tool / R macros leave `GuiSettings/@Plugin` EMPTY; the real tool is in
  `EngineSettings/@Macro` — this script reports it as `Macro:<name>` so it never shows
  blank (ayx/tools-predictive-ml.md § Predictive Tools). Bundled `.yxmc` macros are
  separate XML files with the same schema — run this script on each to inventory their
  internals too.
- EMBEDDED LOGIC: any `<Query>`/`*SQL*` payload inside a tool's Configuration is
  workflow logic written in SQL, NOT a source — the tool's row is flagged and the
  query is dumped with a clause census (joins/unions/filters/aggregations) so it
  gets decomposed into pseudo-tools during Phase 2 (see migration SKILL.md § Rules,
  embedded SQL).
- INPUT CONTRACT: the flow's true leaves — file/DB endpoints read by input tools PLUS
  the deduplicated base tables read by all embedded SQL. Each must exist as a source
  dataset; synthetic data may only be generated for THESE, never for a query's result.
- OUTPUT CONTRACT: for each terminal tool (feeds only a BrowseV2/sink), the script reads
  that tool's cached `Properties/MetaInfo/RecordInfo` (the output anchor) and prints its
  ordered `name:type` field list. THAT column set — names, order AND types — is the
  migration's output contract; the migrated terminal dataset must match it exactly (no
  carried-over working columns, no measures landing as text). Absent when Alteryx didn't
  cache schema — then derive the contract from the terminal tool's Select/config (see
  ayx/overview.md § Source-specific verification).
- DISABLED containers: tools inside a `<Disabled value="True"/>` ToolContainer never
  execute — their rows are flagged dead and must NOT be migrated.
- INTERFACE: `.yxwz` apps and `.yxmc` macros carry Questions (the interactive surface).
  Each is listed — the interface is a required deliverable, rebuilt in App Designer,
  never silently dropped (ayx/tools-io-apps-ml.md § Analytic Apps).
"""

import argparse
import re
import xml.etree.ElementTree as ET
from collections import defaultdict

IGNORE = {"TextBox", "BrowseV2", "ToolContainer"}

# Clause keywords that end a FROM table list.
_CLAUSE_STOP = re.compile(
    r"\b(where|left|right|full|inner|cross|join|group|order|union|having|limit|on|select)\b",
    re.I,
)


def short_plugin(node):
    """Tool name: last segment of GuiSettings/@Plugin, else the EngineSettings macro."""
    gui = node.find("GuiSettings")
    plugin = gui.get("Plugin", "") if gui is not None else ""
    if plugin:
        return plugin.split(".")[-1]
    eng = node.find("EngineSettings")
    if eng is not None and eng.get("Macro"):
        macro = eng.get("Macro").replace("\\", "/").split("/")[-1]
        return f"Macro:{macro}"
    return "(unknown)"


def record_infos(node):
    """ToolID's cached output schemas: {anchor -> [(field name, type), …] in order}.

    Alteryx caches schema per output anchor under Properties/MetaInfo[@connection];
    the Field order IS the column order. Empty when the workflow wasn't run/saved with
    metadata (common) — the caller then falls back to the tool config.
    """
    out = {}
    for meta in node.findall("Properties/MetaInfo"):
        ri = meta.find("RecordInfo")
        if ri is None:
            continue
        out[meta.get("connection") or "Output"] = [
            (f.get("name"), f.get("type", "")) for f in ri.findall("Field")
        ]
    return out


def file_endpoint(node):
    """The tool's file/DB endpoint (Configuration/File text), or None.

    For DbFileInput this is a source path/table (`x.yxdb`, `x.xlsx|||Sheet1$`,
    ODBC string); for DbFileOutput a destination. Both are contract material.
    """
    f = node.find("Properties/Configuration/File")
    if f is not None and (f.text or "").strip():
        return f.text.strip()
    return None


def indb_connection(node):
    """Connection name of an In-DB (LockIn*) tool, or None (may be nested)."""
    cfg = node.find("Properties/Configuration")
    if cfg is None:
        return None
    c = cfg.find(".//Connection")
    if c is not None and (c.text or "").strip():
        return c.text.strip()
    return None


def ui_questions(root):
    """Interface questions of an app/macro: [{Type, Name, Description, ToolId, extras}].

    Walks nested Questions (Tabs hold children); Tabs themselves are layout, skipped.
    """
    out, seen = [], set()
    for q in root.iter("Question"):
        typ = q.findtext("Type") or ""
        name = q.findtext("Name") or ""
        if typ == "Tab" or (typ, name) in seen:
            continue
        seen.add((typ, name))
        extras = {
            c.tag: re.sub(r"\s+", " ", c.text.strip())
            for c in q
            if c.tag not in ("Type", "Name", "Description", "ToolId", "Questions")
            and (c.text or "").strip()
        }
        out.append(
            {
                "Type": typ,
                "Name": name,
                "Description": q.findtext("Description") or "",
                "ToolId": q.findtext("ToolId") or "",
                "extras": extras,
            }
        )
    return out


def embedded_queries(node):
    """SQL payloads under Properties/Configuration: [(tag, sql_text)].

    Matches any element whose tag contains 'query' or 'sql' (Query, PreSQL,
    PostSQLStatement, …) with non-empty text — the In-DB (`LockIn*`) and
    Input-with-SQL-override cases.
    """
    cfg = node.find("Properties/Configuration")
    if cfg is None:
        return []
    out = []
    for el in cfg.iter():
        tag = el.tag.lower()
        if ("query" in tag or "sql" in tag) and el.text and el.text.strip():
            out.append((el.tag, el.text.strip()))
    return out


def sql_tables(sql):
    """Base tables read by a SQL string, in order of appearance.

    Handles JOINed tables, comma-separated FROM lists ("from a x, b y") and
    tables inside subqueries. Skips derived tables ("from (select …)").
    """
    s = re.sub(r"--[^\n]*", " ", sql)
    s = re.sub(r"\s+", " ", s)
    tables = []
    for m in re.finditer(r"\bfrom\s+", s, re.I):
        rest = s[m.end() :]
        stop = _CLAUSE_STOP.search(rest)
        seg = rest[: stop.start()] if stop else rest
        for part in seg.split(","):
            tok = part.strip().split(" ")[0].strip("()")
            if tok and tok.lower() != "select" and tok not in tables:
                tables.append(tok)
    for m in re.finditer(r"\bjoin\s+([\w.$]+)", s, re.I):
        if m.group(1) not in tables:
            tables.append(m.group(1))
    return tables


def sql_census(sql):
    """Count of logic-bearing clauses in a SQL string: {clause -> n}, zeros omitted."""
    s = re.sub(r"--[^\n]*", " ", sql)
    ops = {
        "join": len(re.findall(r"\bjoin\b", s, re.I)),
        "union": len(re.findall(r"\bunion\b", s, re.I)),
        "where": len(re.findall(r"\bwhere\b", s, re.I)),
        "group by": len(re.findall(r"\bgroup\s+by\b", s, re.I)),
        "case": len(re.findall(r"\bcase\b", s, re.I)),
        "subquery": len(re.findall(r"\(\s*select\b", s, re.I)),
        "distinct": len(re.findall(r"\bdistinct\b", s, re.I)),
    }
    return {k: v for k, v in ops.items() if v}


def annotations(node):
    """Human-written text on a tool: TextBox body, container Caption, AnnotationText."""
    out = []
    for path in (
        "Properties/Configuration/Text",
        "Properties/Configuration/Caption",
        "Properties/Annotation/AnnotationText",
    ):
        el = node.find(path)
        if el is not None and (el.text or "").strip():
            out.append(el.text.strip())
    return out


def _hidden_macro(node):
    """Bundled-macro path when a plugin name hides it (predictive tools), else None."""
    eng = node.find("EngineSettings")
    gui = node.find("GuiSettings")
    if eng is not None and eng.get("Macro") and gui is not None and gui.get("Plugin"):
        return eng.get("Macro").replace("\\", "/")
    return None


def _disabled_children(node, tid):
    """ToolIDs living inside a disabled ToolContainer — dead logic."""
    dis = node.find("Properties/Configuration/Disabled")
    if dis is None or (dis.get("value") or "").lower() != "true":
        return []
    return [
        c.get("ToolID")
        for c in node.iter("Node")
        if c.get("ToolID") and c.get("ToolID") != tid
    ]


def _node_facts(node, plugin):
    """Per-tool optional facts, keyed by their inventory bucket."""
    return {
        "schemas": record_infos(node),
        "queries": embedded_queries(node),
        "notes": annotations(node),
        "files": file_endpoint(node),
        "connections": indb_connection(node) if plugin.startswith("LockIn") else None,
        "macro_refs": _hidden_macro(node),
    }


def _dag(root, nodes):
    """Connection DAG + the anchor feeding each terminal's presentation sink."""
    inputs = defaultdict(set)
    outputs = defaultdict(set)
    sink_anchor = {}
    edges = 0
    for conn in root.iter("Connection"):
        o, d = conn.find("Origin"), conn.find("Destination")
        if o is None or d is None:
            continue
        oi, di = o.get("ToolID"), d.get("ToolID")
        if oi is None or di is None:
            continue
        outputs[oi].add(di)
        inputs[di].add(oi)
        edges += 1
        if nodes.get(di) in IGNORE and oi in nodes:
            sink_anchor.setdefault(oi, o.get("Connection") or "Output")
    return inputs, outputs, sink_anchor, edges


def parse(yxmd_path):
    root = ET.parse(yxmd_path).getroot()

    nodes = {}  # ToolID -> plugin short name
    buckets = {
        "schemas": {},  # ToolID -> {anchor -> [(field name, type)]}
        "queries": {},  # ToolID -> [(tag, sql)]
        "notes": {},  # ToolID -> [annotation strings]
        "files": {},  # ToolID -> Configuration/File endpoint
        "connections": {},  # In-DB ToolID -> connection name
        "macro_refs": {},  # ToolID -> bundled macro path hidden by a plugin name
    }
    dead = {}  # ToolID inside a disabled container -> container ToolID
    for node in root.iter("Node"):
        tid = node.get("ToolID")
        if tid is None or tid in nodes:
            continue
        plugin = short_plugin(node)
        nodes[tid] = plugin
        for key, val in _node_facts(node, plugin).items():
            if val:
                buckets[key][tid] = val
        if plugin == "ToolContainer":
            for ctid in _disabled_children(node, tid):
                dead.setdefault(ctid, tid)

    inputs, outputs, sink_anchor, edges = _dag(root, nodes)
    return {
        "nodes": nodes,
        "inputs": inputs,
        "outputs": outputs,
        "edges": edges,
        "sink_anchor": sink_anchor,
        "dead": dead,
        "ui": ui_questions(root),
        **buckets,
    }


def terminals(nodes, inputs, outputs):
    """Tools whose every downstream consumer is presentation-only, plus pure sinks.

    Excludes isolated nodes (no inputs and no outputs) — disconnected TextInput decoys,
    not output sinks.
    """
    out = []
    for tid in sorted(nodes, key=lambda x: int(x) if x.isdigit() else x):
        if nodes[tid] in IGNORE:
            continue
        if not inputs.get(tid) and not outputs.get(tid):
            continue
        real = [c for c in outputs.get(tid, ()) if nodes.get(c) not in IGNORE]
        if not real:
            out.append(tid)
    return out


def fmt(ids):
    return (
        ", ".join(
            f"#{i}" for i in sorted(ids, key=lambda x: int(x) if x.isdigit() else x)
        )
        or "—"
    )


def _ordered(nodes):
    return sorted(nodes, key=lambda x: int(x) if x.isdigit() else x)


def render_embedded(nodes, queries):
    """EMBEDDED LOGIC section: per query — census, tables, verbatim SQL."""
    lines = [
        "## EMBEDDED LOGIC — SQL inside tool configs (decompose in Phase 2)",
        "",
        "Each query below is workflow logic written in SQL, NOT a source. Explode",
        "it into pseudo-tools (FROM/JOIN → Join, WHERE → filter, GROUP BY → Group,",
        "UNION → Stack, CASE/computed cols → Prepare), migrate like canvas logic.",
        "Never synthesize",
        "a query's result set — synthesize its base tables (see INPUT CONTRACT).",
        "",
    ]
    for tid in _ordered(queries):
        for tag, sql in queries[tid]:
            census = sql_census(sql)
            census_s = (
                ", ".join(f"{v} {k}" for k, v in census.items()) or "plain SELECT"
            )
            tables = sql_tables(sql)
            lines.append(f"### #{tid} ({nodes[tid]}) `<{tag}>` — {census_s}")
            lines.append(f"Tables read: {', '.join(tables) or '(none detected)'}")
            lines.append("```sql")
            lines.append(sql)
            lines.append("```")
            lines.append("")
    return "\n".join(lines) + "\n"


def render_input_contract(nodes, queries, files, connections):
    """INPUT CONTRACT: file/DB endpoints read by input tools + SQL base tables."""
    tables = []
    for tid in _ordered(queries):
        for _, sql in queries[tid]:
            for t in sql_tables(sql):
                if t not in tables:
                    tables.append(t)
    sources = {tid: f for tid, f in files.items() if "Output" not in nodes[tid]}
    if not (sources or connections or tables):
        return ""
    lines = [
        "## INPUT CONTRACT — sources (the flow's true leaves)",
        "",
        "Every source below must exist as a dataset in the migrated flow.",
        "Synthetic data may only be generated for these — never for an embedded",
        "query's result set (that would silently delete the query's logic).",
        "",
    ]
    for tid in _ordered(sources):
        lines.append(f"- **#{tid}** ({nodes[tid]}): `` {sources[tid]} ``")
    for tid in _ordered(connections):
        lines.append(
            f"- **#{tid}** ({nodes[tid]}): In-DB connection `{connections[tid]}`"
        )
    lines += [f"- `{t}` (SQL base table)" for t in sorted(tables)]
    return "\n".join(lines) + "\n"


def render_interface(ui):
    """INTERFACE section: app/macro questions — a required deliverable."""
    lines = [
        "## INTERFACE — app/macro questions (rebuild, don't drop)",
        "",
        "This workflow carries an interactive surface. Each question maps to an",
        "App Designer param/tile, each Action to a `${var}` binding (see",
        "ayx/tools-io-apps-ml.md § Analytic Apps). Migrating only the flow is a",
        "silent deliverable drop.",
        "",
    ]
    for q in ui:
        d = re.sub(r"\s+", " ", q["Description"])
        desc = f" — {d}" if d else ""
        tool = f" (tool #{q['ToolId']})" if q["ToolId"] else ""
        extras = "".join(f"; {k}={v[:60]}" for k, v in q["extras"].items())
        lines.append(f"- **{q['Type']}** `{q['Name']}`{tool}{desc}{extras}")
    return "\n".join(lines) + "\n"


def render_annotations(nodes, notes):
    """ANNOTATIONS section: human-written text, verbatim."""
    lines = [
        "## ANNOTATIONS — human context (not recipes; read before Phase 2)",
        "",
        "TextBox bodies and tool annotations, verbatim. These often carry",
        "environment-specific instructions (prod-vs-test filters, delivery notes,",
        "source-table lists) — anything of that kind belongs at the Phase-2 gate.",
        "",
    ]
    for tid in _ordered(notes):
        for text in notes[tid]:
            one = " / ".join(line.strip() for line in text.splitlines() if line.strip())
            lines.append(f"- **#{tid}** ({nodes[tid]}): {one}")
    return "\n".join(lines) + "\n"


def _fields_s(fields):
    return ", ".join(f"{n}:{t}" if t else n for n, t in fields)


def render_contract(nodes, inputs, outputs, schemas, sink_anchor, files, dead):
    lines = [
        "## OUTPUT CONTRACT — terminal schema (Phase-4 column-parity target)",
        "",
        "The migrated terminal dataset must match this column SET, NAMES, ORDER and",
        "TYPES exactly (a measure landing as text = fail, extra working columns =",
        "fail). Feed the names to `dku project audit --contract`.",
        "",
    ]
    any_schema = False
    for tid in terminals(nodes, inputs, outputs):
        dead_s = (
            f" ⚠ DEAD (disabled container #{dead[tid]}) — not a contract"
            if tid in dead
            else ""
        )
        dest = (
            f" → writes `` {files[tid]} ``"
            if tid in files and "Output" in nodes[tid]
            else ""
        )
        head = f"- **#{tid}** ({nodes[tid]}){dest}{dead_s}"
        cached = schemas.get(tid) or {}
        anchor = sink_anchor.get(tid, "Output")
        fields = cached.get(anchor) or cached.get("Output")
        if not fields and len(cached) == 1:
            anchor, fields = next(iter(cached.items()))
        if fields:
            any_schema = True
            lines.append(f"{head} — {len(fields)} cols: {_fields_s(fields)}")
        elif cached:
            any_schema = True
            lines.append(
                f"{head}: schema cached per anchor — the anchor wired to the "
                f"real output is the contract:"
            )
            for a in cached:
                lines.append(
                    f"  - `{a}` ({len(cached[a])} cols): {_fields_s(cached[a])}"
                )
        else:
            hint = ""
            ups = inputs.get(tid) or ()
            if len(ups) == 1:
                up = next(iter(ups))
                up_cached = schemas.get(up) or {}
                if len(up_cached) == 1:
                    ua, uf = next(iter(up_cached.items()))
                    hint = (
                        f" Direct upstream #{up} caches ({len(uf)} cols): "
                        f"{_fields_s(uf)} — apply this tool's own config on top."
                    )
            lines.append(
                f"{head}: no cached schema — read this tool's Select/config "
                f"for the kept column set.{hint}"
            )
    if not any_schema:
        lines.append(
            "  > No terminal has a cached RecordInfo — derive each contract from "
            "the terminal tool's config (mid-flow tools may still cache schemas; "
            "check the .yxmd)."
        )
    return "\n".join(lines) + "\n"


def _size_line(inv, ignorable):
    queries, dead = inv["queries"], inv["dead"]
    n_queries = sum(len(v) for v in queries.values())
    n_ops = sum(
        sum(sum(sql_census(sql).values()) for _, sql in v) for v in queries.values()
    )
    size = (
        f"<!-- {len(inv['nodes'])} canvas tools ({ignorable} presentation-only), "
        f"{inv['edges']} connections"
    )
    if dead:
        size += f"; {len(dead)} tools in disabled containers — dead, not migration size"
    if n_queries:
        size += (
            f"; +{n_ops} embedded-SQL operations across {n_queries} queries "
            f"— the real migration size"
        )
    return size + " -->"


def _banners(inv):
    lines = []
    if any(p.startswith("LockIn") for p in inv["nodes"].values()):
        conns = sorted(set(inv["connections"].values()))
        named = (
            f" — connection(s): {', '.join(f'`{c}`' for c in conns)}" if conns else ""
        )
        lines += [
            "> ⚠ **In-Database workflow** (`LockIn*` tools): the whole flow runs",
            f"> as SQL push-down on ONE connection{named} — a hard engine mandate.",
            "> Every `<Query>` is workflow logic to decompose, not a source (see",
            "> EMBEDDED LOGIC below).",
            "",
        ]
    if inv["ui"]:
        lines += [
            f"> ⚠ **Analytic App / macro interface** ({len(inv['ui'])} questions): the",
            "> interactive surface is a required deliverable — see INTERFACE below.",
            "",
        ]
    return lines


def _row_note(tid, inv):
    plugin, queries, notes = inv["nodes"][tid], inv["queries"], inv["notes"]
    parts = []
    if tid in inv["dead"]:
        parts.append(
            f"⚠ DEAD — inside disabled container #{inv['dead'][tid]}, do not migrate"
        )
    if plugin in IGNORE:
        parts.append(
            "ignore as recipe (text in ANNOTATIONS)"
            if tid in notes
            else "ignore (presentation-only)"
        )
    elif tid in queries:
        n_tables = len({t for _, sql in queries[tid] for t in sql_tables(sql)})
        ops = sum(sum(sql_census(sql).values()) for _, sql in queries[tid])
        parts.append(
            f"⚠ embedded SQL ({n_tables} tables, {ops} ops) — decompose, "
            f"see EMBEDDED LOGIC"
        )
    if tid in inv["macro_refs"]:
        parts.append(
            f"logic in bundled macro `{inv['macro_refs'][tid]}` — inventory it too"
        )
    return "; ".join(parts)


def render(inv):
    nodes, inputs, outputs = inv["nodes"], inv["inputs"], inv["outputs"]
    queries, notes, files = inv["queries"], inv["notes"], inv["files"]
    ordered = _ordered(nodes)
    ignorable = sum(1 for t in ordered if nodes[t] in IGNORE)
    lines = [_size_line(inv, ignorable), ""]
    lines += _banners(inv)
    lines += [
        "| # | Tool ID | Plugin | Inputs | Outputs | What It Does | Migratable? |",
        "|---|---------|--------|--------|---------|--------------|-------------|",
    ]
    for n, tid in enumerate(ordered, 1):
        lines.append(
            f"| {n} | {tid} | {nodes[tid]} | {fmt(inputs[tid])} "
            f"| {fmt(outputs[tid])} |  | {_row_note(tid, inv)} |"
        )
    body = "\n".join(lines) + "\n\n"
    if queries:
        body += render_embedded(nodes, queries) + "\n"
    contract_in = render_input_contract(nodes, queries, files, inv["connections"])
    if contract_in:
        body += contract_in + "\n"
    if inv["ui"]:
        body += render_interface(inv["ui"]) + "\n"
    if notes:
        body += render_annotations(nodes, notes) + "\n"
    return body + render_contract(
        nodes, inputs, outputs, inv["schemas"], inv["sink_anchor"], files, inv["dead"]
    )


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("yxmd", help="path to the .yxmd workflow")
    ap.add_argument("-o", "--out", help="write to this file instead of stdout")
    args = ap.parse_args()

    inv = parse(args.yxmd)
    table = render(inv)
    if args.out:
        with open(args.out, "w") as f:
            f.write(table)
        print(f"{len(inv['nodes'])} tools, {inv['edges']} connections -> {args.out}")
    else:
        print(table, end="")


if __name__ == "__main__":
    main()
