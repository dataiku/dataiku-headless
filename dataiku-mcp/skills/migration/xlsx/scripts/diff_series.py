#!/usr/bin/env python3
"""diff_series.py — parity diff: workbook engine row vs DSS flow series.

The verification workhorse for model/formula-engine migrations: locates a workbook
engine row via its date row in a dump_workbook.py dump, pulls the matching flow
series via `dku dataset download`, and diffs month by month with a divergence-
signature hint (see model-workbooks.md § Verification).

Usage:
  python3 diff_series.py WORKINGS_DUMP.tsv --row 33 \
      --dataset series_final --series UKPOS_Int --value-col metric_value \
      [--date-row 12] [--project PROJ] [--from 2025-08] [--sample-months 08,12]

The dump is dump_workbook.py output (COORD<TAB>K<TAB>formula[<TAB>=><TAB>cached]).
Reads the flow series via `dku dataset download` (logical name, any engine).

Reads the diff like a doctor, then prints a signature hint:
  constant % offset from first forecast month  -> wrong window/anchor (provenance)
  magnitudes equal, sign mirrored              -> per-block sign convention
  exact at seam, drift grows with horizon      -> path dependence / bad telescoping
  off by a stable days-ratio                   -> day-count basis (cal/trading/accrual)
"""

import argparse
import calendar as cal
import csv
import os
import re
import subprocess
import sys


def load_dump_row(path, row_n, date_row):
    cells, dates = {}, {}
    for line in open(path, encoding="utf-8"):
        p = line.rstrip("\n").split("\t")
        if len(p) < 3:
            continue
        m = re.match(r"^([A-Z]+)(\d+)$", p[0])
        if not m:
            continue
        col, row = m.group(1), int(m.group(2))
        val = p[4] if len(p) >= 5 and p[3] == "=>" else p[2]
        if row == date_row and "datetime" in val:
            dm = re.search(r"datetime\.datetime\((\d+), (\d+)", val)
            if dm:
                y, mo = int(dm.group(1)), int(dm.group(2))
                dates[col] = f"{y:04d}-{mo:02d}-{cal.monthrange(y, mo)[1]:02d}"
        elif row == row_n:
            cells[col] = val
    out = {}
    for col, me in dates.items():
        if col in cells:
            try:
                out[me] = float(cells[col])
            except ValueError:
                pass
    return out


def load_flow_series(dataset, series_col, series_id, value_col, month_col, project):
    env = dict(os.environ)
    if project:
        env["DKU_PROJECT"] = project
    raw = subprocess.run(
        ["dku", "dataset", "download", dataset, "-"],
        capture_output=True,
        text=True,
        env=env,
        check=True,
    ).stdout
    out = {}
    for r in csv.DictReader(raw.splitlines()):
        if r.get(series_col) == series_id and r.get(value_col) not in (None, ""):
            out[r[month_col][:10]] = float(r[value_col])
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dump")
    ap.add_argument(
        "--row", type=int, required=True, help="workbook engine row to compare"
    )
    ap.add_argument("--date-row", type=int, default=12, help="row holding month dates")
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--series", required=True)
    ap.add_argument("--series-col", default="series_id")
    ap.add_argument("--value-col", default="metric_value")
    ap.add_argument("--month-col", default="month_end")
    ap.add_argument("--project", default=os.environ.get("DKU_PROJECT"))
    ap.add_argument(
        "--from", dest="from_month", default=None, help="only months >= YYYY-MM"
    )
    ap.add_argument(
        "--sample-months", default=None, help="e.g. '08,12' to sample Aug+Dec per year"
    )
    args = ap.parse_args()

    wb = load_dump_row(args.dump, args.row, args.date_row)
    flow = load_flow_series(
        args.dataset,
        args.series_col,
        args.series,
        args.value_col,
        args.month_col,
        args.project,
    )
    sample = set(args.sample_months.split(",")) if args.sample_months else None

    deltas = []
    print(f"{'month':<12}{'flow':>18}{'workbook':>18}{'delta%':>9}")
    for me in sorted(wb):
        if args.from_month and me[:7] < args.from_month:
            continue
        if sample and me[5:7] not in sample:
            continue
        if me not in flow:
            continue
        f, w = flow[me], wb[me]
        d = (f - w) / abs(w) * 100 if w else 0.0
        deltas.append((me, f, w, d))
        print(f"{me:<12}{f:>18.6f}{w:>18.6f}{d:>8.2f}%")

    if not deltas:
        print(
            "no overlapping months — check --series / --row / --from", file=sys.stderr
        )
        return 1
    ds = [d for _, _, _, d in deltas]
    mirrored = sum(
        1
        for _, f, w, _ in deltas
        if w and abs(abs(f) - abs(w)) / abs(w) < 1e-6 and f * w < 0
    )
    print("\n-- signature hints --")
    if mirrored > len(deltas) * 0.8:
        print(
            "sign-mirrored: per-block sign convention "
            "(check =-INDEX pulls; carry sign in the catalog)"
        )
    elif max(abs(x) for x in ds) < 0.01:
        print("exact: series reproduces the workbook")
    elif max(ds) - min(ds) < 0.5 and abs(ds[0]) > 1:
        print(
            "constant offset from first month: wrong window/anchor — "
            "trace the bound to its assumptions cell"
        )
    elif abs(ds[0]) < 0.5 and abs(ds[-1]) > abs(ds[0]) + 1:
        print(
            "drift grows with horizon: path dependence — "
            "re-derive the telescoped recursion/window roll"
        )
    else:
        print("mixed: diff a component series (value/rate/residual) to localize")
    return 0


if __name__ == "__main__":
    sys.exit(main())
