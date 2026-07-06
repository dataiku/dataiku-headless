#!/usr/bin/env python3
"""Read an Alteryx .yxdb offline: list fields, dump to CSV, decode SpatialObj BLOBs to WKT.

Needs the pure-Python `yxdb` lib (PyPI, Apache-2.0). Run without polluting any env:

    uv run --with yxdb python yxdb_read.py file.yxdb --fields
    uv run --with yxdb python yxdb_read.py file.yxdb --csv out.csv
    uv run --with yxdb python yxdb_read.py file.yxdb --csv out.csv --spatial GeomCol

A SpatialObj column arrives as a raw bytes BLOB = ESRI shapefile geometry-record encoding.
--spatial COL decodes that column in-place to WKT (POINT/LINESTRING/POLYGON, lon/lat).
Upload the CSV, then set the geom column's type to `geometry` (polygon/line) or `geopoint`
(point) with `dku dataset set-schema` so GeoJoin/geoDistance see it. .yxdb date/datetime
fields have no tz and read as STRING — parse downstream in a Prepare DateParser.
"""

import argparse
import csv
import struct


def spatial_to_wkt(blob):
    """ESRI geometry-record BLOB -> WKT. shapeType @0: 1=Point, 3=Polyline, 5=Polygon."""
    if blob is None:
        return None
    blob = bytes(blob)
    if len(blob) < 4:
        return None
    shape_type = struct.unpack_from("<i", blob, 0)[0]
    if shape_type == 1:  # Point: x,y as <2d at offset 4
        x, y = struct.unpack_from("<2d", blob, 4)
        return f"POINT({x} {y})"
    if shape_type not in (3, 5):  # only Polyline / Polygon below
        return None
    n_parts, n_pts = struct.unpack_from("<2i", blob, 36)
    parts = [*list(struct.unpack_from(f"<{n_parts}i", blob, 44)), n_pts]
    pts = struct.unpack_from(f"<{2 * n_pts}d", blob, 44 + n_parts * 4)
    # decode check: byte length is exactly 44 + n_parts*4 + n_pts*16
    rings = [pts[2 * parts[k] : 2 * parts[k + 1]] for k in range(n_parts)]

    def ring(r):
        return "(" + ", ".join(f"{r[i]} {r[i + 1]}" for i in range(0, len(r), 2)) + ")"

    if shape_type == 5:  # Polygon: first ring outer, rest holes
        return f"POLYGON({', '.join(ring(r) for r in rings)})"
    # Polyline -> LINESTRING (1 part) or MULTILINESTRING (N parts)
    if n_parts == 1:
        return "LINESTRING" + ring(rings[0])
    return "MULTILINESTRING(" + ", ".join(ring(r) for r in rings) + ")"


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("yxdb", help="path to the .yxdb file")
    ap.add_argument(
        "--fields",
        action="store_true",
        help="print field names + types and record count",
    )
    ap.add_argument("--csv", metavar="OUT", help="dump all records to this CSV")
    ap.add_argument(
        "--spatial",
        metavar="COL",
        action="append",
        default=[],
        help="decode this SpatialObj column to WKT (repeatable)",
    )
    args = ap.parse_args()

    from yxdb.yxdb_reader import YxdbReader

    r = YxdbReader(path=args.yxdb)
    names = [f.name for f in r.list_fields()]

    if args.fields or not args.csv:
        print(f"{r.num_records} records, {len(names)} fields:")
        for f in r.list_fields():
            print(f"  {f.name}\t{f.data_type}")
        if not args.csv:
            return

    with open(args.csv, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(names)
        while r.next():
            row = []
            for n in names:
                v = r.read_name(n)
                if n in args.spatial:
                    v = spatial_to_wkt(v)
                row.append("" if v is None else v)
            w.writerow(row)
    print(f"wrote {r.num_records} records -> {args.csv}")


if __name__ == "__main__":
    main()
