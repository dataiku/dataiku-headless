#!/usr/bin/env python3
"""Decode Alteryx report-image blobs (<encsection ... PNG ...>base64</encsection>) to PNG.

A "Visual Assets" .yxdb stores each picture in an image column (Image / Anchor Image /
Icon Images / Large Background) as `<encsection id=".." ftype="PNG" ..>iVBOR..b64..</encsection>`.
This decodes one column's blobs to PNG files, so a PortfolioComposer poster can be
rebuilt with Pillow instead of fetching dead asset URLs.

    uv run --with yxdb python decode_encsection.py assets.yxdb --column "Icon Images" -o ./tiles

Discriminator: a column holding long `<encsection ...PNG...>` strings => assets ARE shipped
(decode + finish). A column holding short filenames => assets live at the (often dead) URL.

Trap: the blob can carry a trailing `<img src="..PNG" />` AFTER `</encsection>`, so the
base64 is bounded by the opening tag's first `>` and the FIRST subsequent `<` (split, not
rsplit / not a greedy regex over the whole tail). We also drop `=` from the char class and
re-pad explicitly so a stray mid-payload `=` can't desync the length.
"""

import argparse
import base64
import io
import os
import re


def decode_blob(blob):
    """<encsection ...>b64</encsection>[<img.../>] -> raw PNG bytes (or None)."""
    if not blob or "<encsection" not in blob:
        return None
    payload = blob.split(">", 1)[1].split("<", 1)[
        0
    ]  # between first '>' and first subsequent '<'
    b64 = "".join(re.findall(r"[A-Za-z0-9+/]", payload))
    b64 += "=" * (-len(b64) % 4)
    return base64.b64decode(b64)


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("yxdb", help="path to the Visual Assets .yxdb")
    ap.add_argument("--column", required=True, help="image column to decode")
    ap.add_argument(
        "--name-column", help="column to name files by (default: row index)"
    )
    ap.add_argument(
        "-o", "--out", default="./tiles", help="output directory (default: ./tiles)"
    )
    ap.add_argument(
        "--verify",
        action="store_true",
        help="open each PNG with Pillow to confirm it decodes (needs pillow)",
    )
    args = ap.parse_args()

    from yxdb.yxdb_reader import YxdbReader

    os.makedirs(args.out, exist_ok=True)
    r = YxdbReader(path=args.yxdb)
    n_ok = n_skip = 0
    idx = 0
    while r.next():
        idx += 1
        png = decode_blob(r.read_name(args.column))
        if png is None:
            n_skip += 1
            continue
        stem = (
            str(r.read_name(args.name_column))
            if args.name_column
            else f"tile_{idx:04d}"
        )
        stem = re.sub(r"[^\w.-]", "_", stem) or f"tile_{idx:04d}"
        path = os.path.join(
            args.out, stem if stem.lower().endswith(".png") else stem + ".png"
        )
        with open(path, "wb") as fh:
            fh.write(png)
        if args.verify:
            from PIL import Image

            Image.open(io.BytesIO(png)).verify()
        n_ok += 1
    print(f"decoded {n_ok} PNG(s) -> {args.out}  ({n_skip} rows had no <encsection>)")


if __name__ == "__main__":
    main()
