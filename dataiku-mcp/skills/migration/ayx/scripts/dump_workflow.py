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


def parse(yxmd_path):
    root = ET.parse(yxmd_path).getroot()

    nodes = {}  # ToolID -> plugin short name
    for node in root.iter("Node"):
        tid = node.get("ToolID")
        if tid is None or tid in nodes:
            continue
        nodes[tid] = short_plugin(node)

    inputs = defaultdict(set)
    outputs = defaultdict(set)
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

    return nodes, inputs, outputs, edges


def fmt(ids):
    return (
        ", ".join(
            f"#{i}" for i in sorted(ids, key=lambda x: int(x) if x.isdigit() else x)
        )
        or "—"
    )


def render(nodes, inputs, outputs, edges):
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
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("yxmd", help="path to the .yxmd workflow")
    ap.add_argument("-o", "--out", help="write to this file instead of stdout")
    args = ap.parse_args()

    nodes, inputs, outputs, edges = parse(args.yxmd)
    table = render(nodes, inputs, outputs, edges)
    if args.out:
        with open(args.out, "w") as f:
            f.write(table)
        print(f"{len(nodes)} tools, {edges} connections -> {args.out}")
    else:
        print(table, end="")


if __name__ == "__main__":
    main()
