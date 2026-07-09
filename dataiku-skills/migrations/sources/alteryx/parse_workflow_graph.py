"""Parse one Alteryx workflow XML into a tool-node + connection graph · in: <workflow.yxmd|.yxmc|.yxwz> --out PATH → out: JSON {source,root,node_count,connection_count,warnings,nodes[],connections[]} (+parse_error) · deps: stdlib (xml.etree.ElementTree, re, json, pathlib, sys, argparse)."""
from __future__ import annotations

import argparse
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

# ordered: first substring match wins
PLUGIN_SUFFIX_NAMES = (
    ("DbFileInput", "Input Data"), ("DbFileOutput", "Output Data"), ("Filter", "Filter"),
    ("MultiRowFormula", "Multi-Row Formula"), ("Formula", "Formula"),
    ("AlteryxSelect", "Select"), ("Select", "Select"), ("Join", "Join"),
    ("Summarize", "Summarize"), ("Sort", "Sort"), ("Union", "Union"), ("Unique", "Unique"),
    ("Sample", "Sample"), ("TextInput", "Text Input"), ("MacroInput", "Macro Input"),
    ("MacroOutput", "Macro Output"), ("TextToColumns", "Text To Columns"), ("DateTime", "DateTime"),
    ("Transpose", "Transpose"), ("DynamicRename", "Dynamic Rename"), ("RegEx", "RegEx"),
    ("CrossTab", "Cross Tab"), ("AppendFields", "Append Fields"), ("RecordID", "Record ID"),
    ("FindReplace", "Find Replace"), ("GenerateRows", "Generate Rows"), ("RunningTotal", "Running Total"),
    ("ToolContainer", "Tool Container"), ("Download", "Download"), ("BrowseV2", "Browse"),
    ("HtmlBox", "HTML Box"), ("TextBox", "Text Box"),
    ("BlockUntilDone", "Block Until Done"), ("Rank", "Rank"), ("Tile", "Tile"),
    ("Questions.Tab", "Interface Tab"), ("NumericUpDown", "Interface Numeric Up Down"),
    ("ControlParam", "Control Parameter"), ("Action", "Interface Action"),
    ("PlotlyCharting", "Plotly Chart"), ("ComposerImage", "Composer Image"),
)


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def iter_named(root, name):
    return [el for el in root.iter() if local_name(el.tag) == name]


def first_named(root, name):
    return next((el for el in root.iter() if local_name(el.tag) == name), None)


def first_child_named(root, name):
    return next((c for c in root if local_name(c.tag) == name), None)


def element_text(element) -> str:
    if element is None:
        return ""
    return " ".join(part.strip() for part in element.itertext() if part.strip())


def compact_xml(element) -> str:
    if element is None:
        return ""
    return ET.tostring(element, encoding="unicode", short_empty_elements=True).strip()


def regex_attr(raw_text: str, attr_name: str) -> str:
    match = re.search(rf'\b{re.escape(attr_name)}\s*=\s*["\']([^"\']+)["\']', raw_text, flags=re.IGNORECASE)
    return match.group(1).strip() if match else ""


def plugin_name(plugin: str) -> str:
    if not plugin:
        return "Unknown Tool"
    if plugin.lower().endswith(".yxmc"):
        return "Macro"
    normalized = plugin.lower()
    for suffix, name in PLUGIN_SUFFIX_NAMES:
        if suffix.lower() in normalized:
            return name
    return "Unknown Tool"


def build_node(tool_id, plugin, annotation, raw_config, warnings, prefix=""):
    tool_name = plugin_name(plugin)
    if tool_name == "Unknown Tool":
        warnings.append(f"{prefix}Tool ID {tool_id} uses unknown plugin '{plugin or '(missing)'}'.")
    return {
        "id": tool_id,
        "plugin": plugin,
        "tool_name": tool_name,
        "annotation": annotation,
        "raw_config": raw_config,
    }


def parse_node(node, warnings):
    gui = first_child_named(node, "GuiSettings")
    engine = first_child_named(node, "EngineSettings")
    plugin = gui.attrib.get("Plugin", "").strip() if gui is not None else ""
    if not plugin and engine is not None:
        plugin = (
            engine.attrib.get("EngineDllEntryPoint", "").strip()
            or engine.attrib.get("Macro", "").strip()
        )
    tool_id = node.attrib.get("ToolID", "").strip() or "unknown"
    return build_node(tool_id, plugin, element_text(first_named(node, "Annotation")),
                      compact_xml(first_named(node, "Configuration")), warnings)


def parse_connections(root):
    connections = []
    for connection in iter_named(root, "Connection"):
        origin = first_child_named(connection, "Origin")
        destination = first_child_named(connection, "Destination")
        connections.append({
            "origin_tool_id": origin.attrib.get("ToolID", "") if origin is not None else "",
            "origin_anchor": origin.attrib.get("Connection", "") if origin is not None else "",
            "destination_tool_id": destination.attrib.get("ToolID", "") if destination is not None else "",
            "destination_anchor": destination.attrib.get("Connection", "") if destination is not None else "",
        })
    return connections


def salvage_config(raw_text: str) -> str:
    match = re.search(r"<Configuration\b[^>]*>.*?</Configuration>", raw_text, flags=re.IGNORECASE | re.DOTALL)
    return re.sub(r"\s+", " ", match.group(0)).strip() if match else ""


def salvage_nodes(xml_payload, warnings):
    nodes = []
    pattern = re.compile(r"<Node\b(?P<attrs>[^>]*)>(?P<body>.*?)</Node>", flags=re.IGNORECASE | re.DOTALL)
    for match in pattern.finditer(xml_payload):
        attrs, body = match.group("attrs"), match.group("body")
        tool_id = regex_attr(attrs, "ToolID") or "unknown"
        plugin = regex_attr(body, "Plugin") or regex_attr(body, "EngineDllEntryPoint")
        nodes.append(build_node(tool_id, plugin, "", salvage_config(body), warnings, prefix="Salvaged "))
    return nodes


def salvage_connections(xml_payload):
    connections = []
    pattern = re.compile(
        r"<Connection\b[^>]*>\s*<Origin\b(?P<origin>[^>]*)/?>.*?"
        r"<Destination\b(?P<destination>[^>]*)/?>.*?</Connection>",
        flags=re.IGNORECASE | re.DOTALL,
    )
    for match in pattern.finditer(xml_payload):
        connections.append({
            "origin_tool_id": regex_attr(match.group("origin"), "ToolID") or "unknown",
            "origin_anchor": regex_attr(match.group("origin"), "Connection") or "Output",
            "destination_tool_id": regex_attr(match.group("destination"), "ToolID") or "unknown",
            "destination_anchor": regex_attr(match.group("destination"), "Connection") or "Input",
        })
    return connections


def summary(source, root, nodes, connections, warnings, parse_error=""):
    if not nodes:
        warnings.append("No Alteryx tool nodes were parsed from the payload.")
    if not connections:
        warnings.append("No Alteryx connections were parsed from the payload.")
    result = {
        "source": str(source),
        "root": root,
        "node_count": len(nodes),
        "connection_count": len(connections),
        "warnings": warnings,
        "nodes": nodes,
        "connections": connections,
    }
    if parse_error:
        result["parse_error"] = parse_error
    return result


def inspect_workflow(path):
    xml_payload = path.read_text()
    warnings = []
    try:
        root = ET.fromstring(xml_payload)
    except ET.ParseError as exc:
        parse_error = str(exc)
        warnings.append(f"XML parse failed: {parse_error}. Returned degraded summary.")
        nodes = salvage_nodes(xml_payload, warnings)
        connections = salvage_connections(xml_payload)
        return summary(path, "unknown", nodes, connections, warnings, parse_error)

    root_name = local_name(root.tag)
    if root_name != "AlteryxDocument":
        warnings.append(f"Root tag is '{root_name}', not 'AlteryxDocument'.")
    nodes = [parse_node(node, warnings) for node in iter_named(root, "Node")]
    connections = parse_connections(root)
    return summary(path, root_name, nodes, connections, warnings)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("workflow", help="path to .yxmd/.yxmc/.yxwz workflow XML")
    parser.add_argument("--out", default=None, help="JSON output path (default extract/<stem>.json under cwd)")
    args = parser.parse_args()

    src = Path(args.workflow)
    out = Path(args.out) if args.out else Path("extract") / f"{src.stem}.json"
    out.parent.mkdir(parents=True, exist_ok=True)

    try:
        result = inspect_workflow(src)
    except OSError as exc:
        sys.exit(f"error: cannot read workflow {src}: {exc}")

    out.write_text(json.dumps(result, indent=1), encoding="utf-8")

    unknown = sorted({n["plugin"] or "(missing)" for n in result["nodes"] if n["tool_name"] == "Unknown Tool"})
    print(
        f"root={result['root']} nodes={result['node_count']} conns={result['connection_count']} "
        f"warnings={len(result['warnings'])}" + (f"; unknown plugins: {', '.join(unknown)}" if unknown else "")
    )
    print(f"out: {out}")


if __name__ == "__main__":
    main()
