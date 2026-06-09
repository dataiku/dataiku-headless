#!/usr/bin/env python3
"""Extract every Alteryx TextInput tool's inline data from a .yxmd into one CSV per tool.

TextInput tools embed their data in the workflow XML (no external file). This writes
`tool_<ToolID>.csv` (header + rows) for each, ready for `dku dataset upload`.

    uv run python extract_textinput.py workflow.yxmd -o ./out

Then per file:  dku dataset create tool_13 --type UploadedFiles -P PROJ
                dku dataset upload tool_13 out/tool_13.csv -P PROJ
                dku dataset set-schema tool_13 -P PROJ -d '[{"name":..,"type":"bigint"},..]'

Types are NOT in the XML — set them from the first downstream AlteryxSelect (else STRING).
If a single column holds delimited / quoted text, the upload autodetect mis-parses it:
see ayx/overview.md "Single-column TextInput upload traps" before uploading.
"""

import argparse
import csv
import os
import xml.etree.ElementTree as ET


def extract(yxmd_path, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    root = ET.parse(yxmd_path).getroot()
    written = []
    for node in root.findall("./Nodes/Node"):
        gui = node.find("./GuiSettings")
        if gui is None or "TextInput" not in gui.get("Plugin", ""):
            continue
        tid = node.get("ToolID")
        cfg = node.find("./Properties/Configuration")
        if cfg is None:
            continue
        fields = [f.get("name") for f in cfg.findall("./Fields/Field")]
        rows = [
            [c.text or "" for c in r.findall("./c")] for r in cfg.findall("./Data/r")
        ]
        path = os.path.join(out_dir, f"tool_{tid}.csv")
        with open(path, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(fields)
            w.writerows(rows)
        written.append((tid, len(rows), len(fields), path))
    return written


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("yxmd", help="path to the .yxmd workflow")
    ap.add_argument("-o", "--out", default=".", help="output directory (default: cwd)")
    args = ap.parse_args()
    written = extract(args.yxmd, args.out)
    if not written:
        print("No TextInput tools found.")
        return
    for tid, nrows, ncols, path in written:
        print(f"tool_{tid}: {nrows} rows x {ncols} cols -> {path}")


if __name__ == "__main__":
    main()
