#!/usr/bin/env python3
"""Dump an Alteryx `.yxmd` (or extracted `.yxwz`/`.yxzp` inner `.yxmd`) as a Phase-1 inventory.

Emits the tool list + the connection DAG (each tool's upstream inputs and downstream
outputs) as the migration-skill inventory table — the mechanical half of Phase 1. You
still fill the "What It Does" and "Migratable?" columns by reading each tool's config.

    uv run python scripts/dump_workflow.py workflow.yxmd          # markdown to stdout
    uv run python scripts/dump_workflow.py workflow.yxmd -o inv.md

Notes:
- Presentation-only tools (TextBox, BrowseV2, ToolContainer) are flagged "ignore" — they
  carry no flow logic (see ayx/overview.md § Non-migratable patterns).
- Predictive Tool / R macros leave `GuiSettings/@Plugin` EMPTY; the real tool is in
  `EngineSettings/@Macro` — this script reports it as `Macro:<name>` so it never shows blank
  (ayx/tools-predictive-ml.md § Predictive Tools).
- OUTPUT CONTRACT: for each terminal tool (feeds only a BrowseV2/sink), the script reads
  that tool's cached `Properties/MetaInfo/RecordInfo` (the output anchor) and prints its
  ordered field list. THAT column set — names + order — is the migration's output contract;
  the migrated terminal dataset must match it exactly (no carried-over working columns).
  Absent when Alteryx didn't cache schema — then derive the contract from the terminal
  tool's Select/config (see ayx/overview.md § Source-specific verification).
"""

import argparse
import xml.etree.ElementTree as ET
from collections import defaultdict

IGNORE = {"TextBox", "BrowseV2", "ToolContainer"}


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
    """ToolID's cached output schemas: {anchor -> [field names in order]}.

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
            f.get("name") for f in ri.findall("Field")
        ]
    return out


def parse(yxmd_path):
    root = ET.parse(yxmd_path).getroot()

    nodes = {}  # ToolID -> plugin short name
    schemas = {}  # ToolID -> {anchor -> [field names]}
    for node in root.iter("Node"):
        tid = node.get("ToolID")
        if tid is None or tid in nodes:
            continue
        nodes[tid] = short_plugin(node)
        ri = record_infos(node)
        if ri:
            schemas[tid] = ri

    inputs = defaultdict(set)
    outputs = defaultdict(set)
    sink_anchor = {}  # terminal ToolID -> anchor name feeding a presentation sink
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

    # Terminal = no real (non-presentation) downstream consumer; remember the anchor
    # that feeds its BrowseV2 so we report the right RecordInfo.
    for conn in root.iter("Connection"):
        o, d = conn.find("Origin"), conn.find("Destination")
        if o is None or d is None:
            continue
        oi, di = o.get("ToolID"), d.get("ToolID")
        if di in nodes and nodes[di] in IGNORE and oi in nodes:
            sink_anchor.setdefault(oi, o.get("Connection") or "Output")

    return nodes, inputs, outputs, edges, schemas, sink_anchor


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


def render_contract(nodes, inputs, outputs, schemas, sink_anchor):
    lines = [
        "## OUTPUT CONTRACT — terminal schema (Phase-4 column-parity target)",
        "",
        "The migrated terminal dataset must match this column SET, NAMES and ORDER exactly.",
        "Extra working columns = fail. Feed the list to `dku project audit --contract`.",
        "",
    ]
    any_schema = False
    for tid in terminals(nodes, inputs, outputs):
        anchor = sink_anchor.get(tid, "Output")
        fields = (schemas.get(tid) or {}).get(anchor) or (schemas.get(tid) or {}).get(
            "Output"
        )
        if fields:
            any_schema = True
            cols = ", ".join(fields)
            lines.append(f"- **#{tid}** ({nodes[tid]}, {len(fields)} cols): {cols}")
        else:
            lines.append(
                f"- **#{tid}** ({nodes[tid]}): no cached schema — read this tool's "
                f"Select/config for the kept column set."
            )
    if not any_schema:
        lines.append(
            "  > No cached RecordInfo anywhere — derive each contract from the terminal "
            "tool's config."
        )
    return "\n".join(lines) + "\n"


def render(nodes, inputs, outputs, edges, schemas, sink_anchor):
    ordered = sorted(nodes, key=lambda x: int(x) if x.isdigit() else x)
    ignorable = sum(1 for t in ordered if nodes[t] in IGNORE)
    lines = [
        f"<!-- {len(nodes)} tools ({ignorable} presentation-only), {edges} connections -->",
        "",
        "| # | Tool ID | Plugin | Inputs | Outputs | What It Does | Migratable? |",
        "|---|---------|--------|--------|---------|--------------|-------------|",
    ]
    for n, tid in enumerate(ordered, 1):
        plugin = nodes[tid]
        note = "ignore (presentation-only)" if plugin in IGNORE else ""
        lines.append(
            f"| {n} | {tid} | {plugin} | {fmt(inputs[tid])} | {fmt(outputs[tid])} |  | {note} |"
        )
    body = "\n".join(lines) + "\n"
    return body + "\n" + render_contract(nodes, inputs, outputs, schemas, sink_anchor)


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("yxmd", help="path to the .yxmd workflow")
    ap.add_argument("-o", "--out", help="write to this file instead of stdout")
    args = ap.parse_args()

    nodes, inputs, outputs, edges, schemas, sink_anchor = parse(args.yxmd)
    table = render(nodes, inputs, outputs, edges, schemas, sink_anchor)
    if args.out:
        with open(args.out, "w") as f:
            f.write(table)
        print(f"{len(nodes)} tools, {edges} connections -> {args.out}")
    else:
        print(table, end="")


if __name__ == "__main__":
    main()
