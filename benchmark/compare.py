#!/usr/bin/env python3
"""Compare benchmark runs across profiles.

Usage:
    uv run python -m benchmark.compare                              # latest per profile
    uv run python -m benchmark.compare bench_A bench_B             # specific run IDs or dirs
    uv run python -m benchmark.compare --baseline A --candidate B  # explicit A/B comparison
    uv run python -m benchmark.compare --all                       # every recorded run
    uv run python -m benchmark.compare --profile claude_dku_skills,codex_dku_skills
    uv run python -m benchmark.compare --domain data_prep
    uv run python -m benchmark.compare --export json               # also export to file
    uv run python -m benchmark.compare --profiles-only             # skip scenario matrix
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from datetime import datetime
from io import StringIO
from pathlib import Path

from rich import box
from rich.console import Console
from rich.table import Table
from rich.text import Text

REPORTS_DIR = Path(__file__).parent / "reports"


def _load_records(paths: list[Path]) -> list[dict]:
    records = []
    for p in paths:
        summary_path = p / "summary.json"
        if not summary_path.exists():
            continue
        try:
            s = json.loads(summary_path.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        for t in s.get("tests", []):
            records.append(
                {
                    "run_id": s["run_id"],
                    "timestamp": s.get("timestamp", ""),
                    "git_sha": s.get("git_sha", ""),
                    "profile": t["agent"],
                    "test_id": t["test_id"],
                    "domain": t.get("domain", ""),
                    "difficulty": t.get("difficulty", "?"),
                    "passed": t["passed"],
                    "score": t.get("score", 0.0),
                    "duration_ms": t.get("duration_ms", 0),
                    "input_tokens": t.get("input_tokens", 0),
                    "output_tokens": t.get("output_tokens", 0),
                    "cost_usd": t.get("cost_usd", 0.0),
                    "n_commands": t.get(
                        "n_commands", len(t.get("commands_executed", []))
                    ),
                }
            )
    return records


def _resolve_paths(run_refs: list[str]) -> list[Path]:
    if not run_refs:
        if not REPORTS_DIR.exists():
            return []
        return sorted(REPORTS_DIR.iterdir())
    paths = []
    for ref in run_refs:
        p = Path(ref)
        if p.is_dir():
            paths.append(p)
            continue
        if not REPORTS_DIR.exists():
            print(f"ERROR: reports dir not found, cannot resolve '{ref}'")
            sys.exit(1)
        matches = [d for d in REPORTS_DIR.iterdir() if d.is_dir() and ref in d.name]
        if not matches:
            print(f"ERROR: no run matching '{ref}'")
            sys.exit(1)
        if len(matches) > 1:
            print(f"ERROR: ambiguous ref '{ref}': {[d.name for d in matches]}")
            sys.exit(1)
        paths.append(matches[0])
    return paths


def _select_latest_per_profile(records: list[dict]) -> list[dict]:
    """Keep only records from the newest report dir for each distinct profile."""
    by_run: dict[str, list[dict]] = defaultdict(list)
    for r in records:
        by_run[r["run_id"]].append(r)

    run_profiles: dict[str, set[str]] = {}
    run_timestamp: dict[str, str] = {}
    for run_id, recs in by_run.items():
        run_profiles[run_id] = {r["profile"] for r in recs}
        run_timestamp[run_id] = recs[0].get("timestamp", "")

    selected: set[str] = set()
    all_profiles = {r["profile"] for r in records}
    for profile in all_profiles:
        candidates = [
            (rid, ts)
            for rid, ts in run_timestamp.items()
            if profile in run_profiles[rid]
        ]
        if candidates:
            candidates.sort(key=lambda x: x[1], reverse=True)
            selected.add(candidates[0][0])

    return [r for r in records if r["run_id"] in selected]


def _avg(values: list[float | int]) -> float:
    return sum(values) / len(values) if values else 0.0


def _fmt_tokens(n: float) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.0f}k"
    return str(int(n))


def _pass_cell(recs: list[dict]) -> Text:
    if not recs:
        return Text("—", style="dim")
    n = len(recs)
    n_passed = sum(1 for r in recs if r["passed"])
    if n == 1:
        return (
            Text("PASS", style="bold green")
            if recs[0]["passed"]
            else Text("FAIL", style="bold red")
        )
    pct = n_passed / n
    label = f"{n_passed}/{n}"
    style = "bold green" if pct == 1.0 else ("bold red" if pct == 0.0 else "yellow")
    return Text(label, style=style)


def _rate_text(n_passed: int, n_total: int) -> Text:
    if n_total == 0:
        return Text("—", style="dim")
    pct = n_passed / n_total
    label = f"{n_passed}/{n_total} ({pct:.0%})"
    style = "bold green" if pct >= 0.7 else ("bold red" if pct < 0.4 else "yellow")
    return Text(label, style=style)


def _matrix_table(
    active: list[dict],
    by_ps: dict[tuple[str, str], list[dict]],
    profiles: list[str],
    scenarios: list[str],
) -> Table:
    table = Table(
        title="Pass / Fail Matrix",
        box=box.SIMPLE_HEAVY,
        show_lines=True,
        title_style="bold",
    )
    table.add_column("Scenario", style="bold", no_wrap=True)
    table.add_column("Domain", style="dim", no_wrap=True)
    table.add_column("Diff", style="dim", justify="center", no_wrap=True)
    for p in profiles:
        table.add_column(p, justify="center", no_wrap=True)
    table.add_column("Overall", justify="center", no_wrap=True)

    for scenario in scenarios:
        sample = next((r for r in active if r["test_id"] == scenario), {})
        row: list = [scenario, sample.get("domain", ""), sample.get("difficulty", "?")]
        total_p, total_n = 0, 0
        for profile in profiles:
            recs = by_ps.get((profile, scenario), [])
            row.append(_pass_cell(recs))
            total_p += sum(1 for r in recs if r["passed"])
            total_n += len(recs)
        row.append(_rate_text(total_p, total_n))
        table.add_row(*row)

    totals: list = [Text("TOTAL", style="bold"), "", ""]
    for profile in profiles:
        recs = [r for r in active if r["profile"] == profile]
        totals.append(_rate_text(sum(1 for r in recs if r["passed"]), len(recs)))
    all_p = sum(1 for r in active if r["passed"])
    totals.append(_rate_text(all_p, len(active)))
    table.add_section()
    table.add_row(*totals)
    return table


def _stats_table(active: list[dict], profiles: list[str]) -> Table:
    table = Table(title="Profile Stats", box=box.SIMPLE_HEAVY, title_style="bold")
    table.add_column("Profile", style="bold")
    table.add_column("Runs", justify="right")
    table.add_column("Pass Rate", justify="right")
    table.add_column("Avg Time", justify="right")
    table.add_column("Avg Commands", justify="right")
    table.add_column("Avg In Tokens", justify="right")
    table.add_column("Avg Out Tokens", justify="right")
    table.add_column("Total Cost", justify="right")

    for profile in profiles:
        recs = [r for r in active if r["profile"] == profile]
        n = len(recs)
        n_passed = sum(1 for r in recs if r["passed"])
        pct = n_passed / n if n else 0
        style = "bold green" if pct >= 0.7 else ("bold red" if pct < 0.4 else "yellow")
        table.add_row(
            profile,
            str(n),
            Text(f"{pct:.0%}  ({n_passed}/{n})", style=style),
            f"{_avg([r['duration_ms'] for r in recs]) / 1000:.0f}s",
            f"{_avg([r['n_commands'] for r in recs]):.1f}",
            _fmt_tokens(_avg([r["input_tokens"] for r in recs])),
            _fmt_tokens(_avg([r["output_tokens"] for r in recs])),
            f"${sum(r['cost_usd'] for r in recs):.3f}",
        )
    return table


def _regression_section(records: list[dict], console: Console) -> None:
    """Compare two runs side-by-side and show what changed."""
    run_ids = sorted({r["run_id"] for r in records})
    if len(run_ids) != 2:
        return
    id_a, id_b = run_ids
    by_a = {(r["profile"], r["test_id"]): r for r in records if r["run_id"] == id_a}
    by_b = {(r["profile"], r["test_id"]): r for r in records if r["run_id"] == id_b}

    improvements, regressions, still_failing = [], [], []
    for key in set(by_a) | set(by_b):
        ra, rb = by_a.get(key), by_b.get(key)
        pa, pb = (ra["passed"] if ra else None), (rb["passed"] if rb else None)
        label = f"{key[0]} / {key[1]}"
        if pa is False and pb is True:
            improvements.append(label)
        elif pa is True and pb is False:
            regressions.append(label)
        elif pa is False and pb is False:
            still_failing.append(label)

    console.print(f"\n  A: [dim]{id_a}[/dim]   B: [dim]{id_b}[/dim]\n")
    if improvements:
        console.print(
            f"  [bold green]▲ Newly passing ({len(improvements)}):[/bold green]"
        )
        for s in improvements:
            console.print(f"      + {s}")
    if regressions:
        console.print(f"  [bold red]▼ Regressions ({len(regressions)}):[/bold red]")
        for s in regressions:
            console.print(f"      - {s}")
    if still_failing:
        console.print(f"  · Still failing: {', '.join(still_failing)}")
    if not improvements and not regressions and not still_failing:
        console.print("  · No pass/fail changes between runs")
    console.print()


def _export_path(suffix: str) -> Path:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return REPORTS_DIR / f"_compare_{ts}.{suffix}"


def _export_json(
    records: list[dict],
    active: list[dict],
    by_ps: dict,
    profiles: list[str],
    scenarios: list[str],
) -> str:
    """Build a JSON payload of the full comparison data."""
    run_ids = sorted({r["run_id"] for r in records})
    payload = {
        "run_ids": run_ids,
        "profiles": profiles,
        "scenarios": scenarios,
        "total_records": len(records),
        "active_records": len(active),
        "total_passed": sum(1 for r in active if r["passed"]),
        "total_failed": sum(1 for r in active if not r["passed"]),
        "runs": {},
        "matrix": {},
    }

    for rid in run_ids:
        run_recs = [r for r in records if r["run_id"] == rid]
        payload["runs"][rid] = {
            "timestamp": run_recs[0]["timestamp"] if run_recs else "",
            "git_sha": run_recs[0]["git_sha"] if run_recs else "",
            "total": len(run_recs),
            "passed": sum(1 for r in run_recs if r["passed"]),
        }

    for (profile, scenario), recs in sorted(by_ps.items()):
        payload["matrix"].setdefault(profile, {})[scenario] = [
            {
                "run_id": r["run_id"],
                "passed": r["passed"],
                "score": r["score"],
                "duration_ms": r["duration_ms"],
                "cost_usd": r.get("cost_usd", 0),
            }
            for r in recs
        ]

    return json.dumps(payload, indent=2)


def _export_csv(records: list[dict]) -> str:
    """Build a CSV string of per-test records."""
    out = StringIO()
    fieldnames = [
        "run_id",
        "timestamp",
        "git_sha",
        "profile",
        "test_id",
        "domain",
        "difficulty",
        "passed",
        "score",
        "duration_ms",
        "input_tokens",
        "output_tokens",
        "cost_usd",
        "n_commands",
    ]
    writer = csv.DictWriter(out, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    for r in records:
        writer.writerow(r)
    return out.getvalue()


def _export_md(
    active: list[dict],
    by_ps: dict[tuple[str, str], list[dict]],
    profiles: list[str],
    scenarios: list[str],
) -> str:
    """Build a Markdown table of the comparison."""
    lines: list[str] = []

    run_ids = sorted({r["run_id"] for r in active})
    lines.append("# Benchmark Comparison\n")
    lines.append(f"**Runs:** {', '.join(run_ids)}\n")
    lines.append("")

    def _md_rate(recs: list[dict]) -> str:
        if not recs:
            return "—"
        n_passed = sum(1 for r in recs if r["passed"])
        return f"{n_passed}/{len(recs)}"

    headers = ["Scenario", "Domain", "Diff"] + profiles + ["Overall"]
    lines.append("| " + " | ".join(headers) + " |")
    lines.append("| " + " | ".join(["---"] * len(headers)) + " |")

    for scenario in scenarios:
        sample = next((r for r in active if r["test_id"] == scenario), {})
        row = [scenario, sample.get("domain", ""), sample.get("difficulty", "?")]
        total_p, total_n = 0, 0
        for profile in profiles:
            recs = by_ps.get((profile, scenario), [])
            row.append(_md_rate(recs))
            total_p += sum(1 for r in recs if r["passed"])
            total_n += len(recs)
        row.append(f"{total_p}/{total_n}" if total_n else "—")
        lines.append("| " + " | ".join(row) + " |")

    total_row = ["**TOTAL**", "", ""]
    for profile in profiles:
        recs = [r for r in active if r["profile"] == profile]
        total_row.append(_md_rate(recs))
    all_p = sum(1 for r in active if r["passed"])
    total_row.append(f"{all_p}/{len(active)}")
    lines.append("| " + " | ".join(total_row) + " |")

    lines.append("")
    lines.append("## Profile Stats\n")
    stat_headers = [
        "Profile",
        "Runs",
        "Pass Rate",
        "Avg Time",
        "Avg Commands",
        "Avg In Tokens",
        "Avg Out Tokens",
        "Total Cost",
    ]
    lines.append("| " + " | ".join(stat_headers) + " |")
    lines.append("| " + " | ".join(["---"] * len(stat_headers)) + " |")

    for profile in profiles:
        recs = [r for r in active if r["profile"] == profile]
        n = len(recs)
        n_passed = sum(1 for r in recs if r["passed"])
        pct = f"{n_passed}/{n} ({n_passed / n:.0%})" if n else "—"
        lines.append(
            f"| {profile} | {n} | {pct} | "
            f"{_avg([r['duration_ms'] for r in recs]) / 1000:.0f}s | "
            f"{_avg([r['n_commands'] for r in recs]):.1f} | "
            f"{_fmt_tokens(_avg([r['input_tokens'] for r in recs]))} | "
            f"{_fmt_tokens(_avg([r['output_tokens'] for r in recs]))} | "
            f"${sum(r['cost_usd'] for r in recs):.3f} |"
        )

    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compare benchmark runs across profiles"
    )
    parser.add_argument(
        "runs",
        nargs="*",
        help="Run IDs or report dirs (default: latest run per profile)",
    )
    parser.add_argument(
        "--baseline",
        help="First run for explicit A/B comparison (use with --candidate)",
    )
    parser.add_argument(
        "--candidate",
        help="Second run for explicit A/B comparison (use with --baseline)",
    )
    parser.add_argument("--domain", help="Filter by domain (comma-separated)")
    parser.add_argument("--profile", help="Filter by profile (comma-separated)")
    parser.add_argument(
        "--all",
        action="store_true",
        help="Load every report dir (default: latest run per profile only)",
    )
    parser.add_argument(
        "--profiles-only",
        action="store_true",
        help="Skip the per-scenario pass/fail matrix; show only profile stats",
    )
    parser.add_argument(
        "--export",
        choices=["json", "csv", "md"],
        help="Export comparison data to benchmark/reports/ (json, csv, or markdown)",
    )
    args = parser.parse_args()

    if args.baseline and args.candidate:
        paths = _resolve_paths([args.baseline, args.candidate])
    elif args.baseline or args.candidate:
        print("ERROR: both --baseline and --candidate must be used together")
        sys.exit(1)
    else:
        paths = _resolve_paths(args.runs)

    if not paths:
        print("No reports found.")
        sys.exit(0)

    records = _load_records(paths)

    if args.domain:
        domains = {d.strip() for d in args.domain.split(",")}
        records = [r for r in records if r["domain"] in domains]
    if args.profile:
        pf = {p.strip() for p in args.profile.split(",")}
        records = [r for r in records if r["profile"] in pf]

    if not records:
        print("No records found after filtering.")
        sys.exit(0)

    if not args.baseline and not args.candidate and not args.runs and not args.all:
        records = _select_latest_per_profile(records)

    by_ps: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in records:
        by_ps[(r["profile"], r["test_id"])].append(r)
    for key in by_ps:
        by_ps[key].sort(key=lambda x: x["timestamp"], reverse=True)

    active = [r for recs in by_ps.values() for r in recs]
    profiles = sorted({r["profile"] for r in active})
    scenarios = sorted({r["test_id"] for r in active})

    console = Console()
    console.print()

    if not args.profiles_only and scenarios:
        console.print(_matrix_table(active, by_ps, profiles, scenarios))
    if profiles:
        console.print(_stats_table(active, profiles))

    n_unique_runs = len({r["run_id"] for r in records})
    if n_unique_runs == 2:
        _regression_section(records, console)

    if args.export:
        path = _export_path(args.export)
        if args.export == "json":
            content = _export_json(records, active, by_ps, profiles, scenarios)
        elif args.export == "csv":
            content = _export_csv(records)
        elif args.export == "md":
            content = _export_md(active, by_ps, profiles, scenarios)
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        console.print(f"  Exported to [bold]{path}[/bold]")
        console.print()


if __name__ == "__main__":
    main()
