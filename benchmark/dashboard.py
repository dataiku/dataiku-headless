#!/usr/bin/env python3
"""Profile-comparison dashboard: build a self-contained HTML page from benchmark reports.

Usage:
    uv run python -m benchmark.dashboard                          # open in browser
    uv run python -m benchmark.dashboard --output report.html     # write to file
    uv run python -m benchmark.dashboard --no-open                # write without opening
"""

from __future__ import annotations

import argparse
import json
import re
import webbrowser
from collections import defaultdict
from datetime import datetime
from pathlib import Path

REPORTS_DIR = Path(__file__).parent / "reports"

PROFILE_COLORS = {
    "vanilla": "#929088",
    "dku": "#3EDAB2",
    "dku_skills": "#06312E",
    "mcp": "#7092F2",
    "mcp_skills": "#EDAB4F",
}


def _rate_class(rate: float) -> str:
    if rate >= 0.7:
        return "green"
    if rate >= 0.4:
        return "yellow"
    return "red"


def _fmt_duration(ms: int) -> str:
    s = ms / 1000
    if s < 60:
        return f"{s:.0f}s"
    return f"{s / 60:.1f}m"


def _fmt_tokens(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.0f}K"
    return str(n)


def _fmt_date(ts: str) -> str:
    try:
        dt = datetime.fromisoformat(ts)
        return dt.strftime("%b %d, %H:%M")
    except (ValueError, TypeError):
        return ts or "?"


def _surface(profile: str) -> str:
    for s in ("mcp_skills", "dku_skills", "mcp", "dku", "vanilla"):
        if s in profile:
            return s
    return "?"


def _vendor(profile: str) -> str:
    if profile.startswith("claude"):
        return "claude"
    if profile.startswith("codex"):
        return "codex"
    return profile.split("_")[0] if "_" in profile else profile


def _profile_sort_key(p: str) -> tuple:
    surfaces = ["vanilla", "dku", "dku_skills", "mcp", "mcp_skills"]
    s = _surface(p)
    return (surfaces.index(s) if s in surfaces else 99, _vendor(p))


def _hex_to_rgba(hex_color: str, alpha: float) -> str:
    hex_color = hex_color.lstrip("#")
    r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"


def _render_template(template: str, **kwargs) -> str:
    """Render template replacing {key} placeholders with format support.
    Converts f-string artifacts ({{ -> {, }} -> }) first.
    Single braces in CSS/JS are left alone (they have spaces after {)."""
    t = template.replace("{{", "{").replace("}}", "}")

    def _replacer(m):
        body = m.group(1)
        if ":" in body:
            key, fmt = body.split(":", 1)
        else:
            key, fmt = body, ""
        val = kwargs.get(key)
        if val is None and key not in kwargs:
            return m.group(0)
        if fmt:
            return format(val, fmt)
        return str(val)

    return re.sub(r"\{(\w[^}]*)\}", _replacer, t)


def load_reports(reports_dir: Path, run: str | None = None) -> list[dict]:
    dirs = sorted(reports_dir.iterdir()) if reports_dir.is_dir() else []
    reports = []
    for d in dirs:
        if not d.is_dir() or d.name.startswith("_"):
            continue
        summary_path = d / "summary.json"
        if not summary_path.exists():
            continue
        try:
            data = json.loads(summary_path.read_text())
            data["_dir"] = d.name
            reports.append(data)
        except (json.JSONDecodeError, OSError):
            continue
    reports.sort(key=lambda r: r.get("timestamp", ""))

    if run == "latest":
        return reports[-1:]
    if run:
        scoped = [r for r in reports if run in (r.get("run_id", ""), r.get("_dir", ""))]
        if not scoped:
            raise SystemExit(f"No report matches run '{run}'")
        return scoped
    return reports


def _aggregate_profile_across_reports(reports: list[dict]) -> dict[str, dict]:
    aggregated: dict[str, dict] = {}
    for r in reports:
        for pname, info in r.get("by_agent", {}).items():
            if pname not in aggregated:
                aggregated[pname] = {
                    "appearances": 0,
                    "total_tests": 0,
                    "total_passed": 0,
                    "total_cost": 0.0,
                    "latest_pass_rate": info["pass_rate"],
                    "latest_cost": info.get("total_cost_usd", 0),
                    "latest_passed": info.get("passed", 0),
                    "latest_total": info.get("total", 0),
                    "latest_timed_out": info.get("timed_out", 0),
                    "model": info.get("model", ""),
                }
            a = aggregated[pname]
            a["appearances"] += 1
            a["total_tests"] += info.get("total", 0)
            a["total_passed"] += info.get("passed", 0)
            a["total_cost"] += info.get("total_cost_usd", 0)
            a["latest_pass_rate"] = info["pass_rate"]
            a["latest_cost"] = info.get("total_cost_usd", 0)
            a["latest_passed"] = info.get("passed", 0)
            a["latest_total"] = info.get("total", 0)
            a["latest_timed_out"] = info.get("timed_out", 0)
    for pname, a in aggregated.items():
        a["overall_pass_rate"] = (
            a["total_passed"] / a["total_tests"] if a["total_tests"] else 0
        )
    return aggregated


def _latest_per_profile(reports: list[dict]) -> dict[str, dict]:
    latest: dict[str, dict] = {}
    for r in reversed(reports):
        agents_in_run = set(r.get("by_agent", {}).keys())
        for pname in agents_in_run:
            if pname not in latest:
                latest[pname] = r
    return latest


def build_profile_cards(aggregated: dict[str, dict]) -> str:
    profiles = sorted(aggregated.keys(), key=_profile_sort_key)
    cards = '<div class="profile-grid">'
    for p in profiles:
        a = aggregated[p]
        rate = a["overall_pass_rate"]
        color = PROFILE_COLORS.get(_surface(p), "#929088")
        timeouts = a.get("latest_timed_out", 0)
        timeout_badge = (
            f'<span class="profile-timeout">{timeouts} timeout{"s" if timeouts != 1 else ""}</span>'
            if timeouts
            else ""
        )
        cards += f"""
  <div class="profile-card" style="border-left: 3px solid {color};">
    <div class="profile-name">{p}</div>
    <div class="profile-model">{a["model"]}</div>
    <div class="profile-stat">
      <span class="profile-rate {_rate_class(rate)}">{rate:.0%}</span>
      <span class="profile-meta">{a["appearances"]} runs &middot; {a["total_tests"]} tests &middot; ${a["total_cost"]:.2f}</span>
    </div>
    {timeout_badge}
  </div>"""
    cards += "\n</div>"
    return cards


def build_runs_table(reports: list[dict]) -> str:
    rows = []
    for r in reversed(reports):
        run_id = r.get("run_id", r.get("_dir", "?"))
        ts = _fmt_date(r.get("timestamp", ""))
        sha = r.get("git_sha", "")[:7]
        rate = r.get("pass_rate", 0)
        passed = r.get("passed", 0)
        total = r.get("total_tests", 0)
        dur = _fmt_duration(r.get("total_duration_ms", 0))
        cost = r.get("total_cost_usd", 0)
        agents = ", ".join(r.get("by_agent", {}).keys())
        rate_class = _rate_class(rate)
        rows.append(
            f"<tr>"
            f'<td class="muted">{run_id}</td>'
            f"<td>{ts}</td>"
            f'<td class="muted">{sha}</td>'
            f'<td><span class="stat-value {rate_class}">{rate:.0%}</span> <span class="muted">({passed}/{total})</span></td>'
            f"<td>{total}</td>"
            f'<td class="muted">{dur}</td>'
            f"<td>${cost:.2f}</td>"
            f'<td class="muted">{agents}</td>'
            f"</tr>"
        )
    return "\n".join(rows)


def build_scenario_table(reports: list[dict]) -> tuple[str, str]:
    aggregated = _aggregate_profile_across_reports(reports)
    profiles = sorted(aggregated.keys(), key=_profile_sort_key)
    latest_run = _latest_per_profile(reports)

    by_scenario: dict[str, dict[str, str]] = {}
    domains: dict[str, str] = {}
    difficulties: dict[str, str] = {}

    for pname, r in latest_run.items():
        for t in r.get("tests", []):
            if t.get("agent") != pname:
                continue
            sid = t["test_id"]
            if sid not in by_scenario:
                by_scenario[sid] = {}
                domains[sid] = t.get("domain", "")
                difficulties[sid] = t.get("difficulty", "")
            if t.get("passed"):
                status = "pass"
            elif t.get("timed_out"):
                status = "timeout"
            else:
                status = "fail"
            by_scenario[sid][pname] = status

    scenarios = sorted(by_scenario.keys())
    headers = "".join(f"<th>{p}</th>" for p in profiles)
    body = ""
    for sid in scenarios:
        cells = ""
        n_pass = n_run = 0
        for p in profiles:
            status = by_scenario[sid].get(p)
            if status == "pass":
                cells += '<td><span class="badge pass">PASS</span></td>'
                n_pass += 1
                n_run += 1
            elif status == "timeout":
                cells += '<td><span class="badge timeout">TIMEOUT</span></td>'
                n_run += 1
            elif status == "fail":
                cells += '<td><span class="badge fail">FAIL</span></td>'
                n_run += 1
            else:
                cells += '<td class="muted">\u2014</td>'
        any_fail = "1" if n_pass < n_run else "0"
        summary_class = (
            "pass" if n_pass == n_run else ("fail" if n_pass == 0 else "warn")
        )
        body += (
            f"<tr data-fail='{any_fail}' "
            f"data-text='{sid} {domains.get(sid, '')} {difficulties.get(sid, '')}'>"
            f"<td>{sid}</td>"
            f"<td class='muted'>{domains.get(sid, '')}</td>"
            f"<td class='muted'>{difficulties.get(sid, '')}</td>"
            f"{cells}"
            f"<td><span class='stat-value {summary_class}'>{n_pass}/{n_run}</span></td>"
            f"</tr>"
        )
    return headers, body


def _profile_breakdown(report: dict, profile: str, key: str) -> dict[str, float]:
    """Pass rate per `key` (domain/difficulty) for one profile, from per-test rows."""
    agg: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for t in report.get("tests", []):
        if t.get("agent") != profile:
            continue
        bucket = agg[t.get(key) or "unknown"]
        bucket[1] += 1
        if t.get("passed"):
            bucket[0] += 1
    return {k: (p / n if n else 0) for k, (p, n) in agg.items()}


def _profile_duration_mean(report: dict, profile: str) -> float:
    """Mean scenario duration (seconds) for the profile in this report."""
    durations = [
        t.get("duration_ms", 0)
        for t in report.get("tests", [])
        if t.get("agent") == profile
    ]
    if not durations:
        return 0
    return sum(durations) / len(durations) / 1000


def _profile_metric_median(report: dict, profile: str, key: str) -> float:
    """Median of a per-test numeric field for the profile in this report."""
    counts = sorted(
        t.get(key, 0) for t in report.get("tests", []) if t.get("agent") == profile
    )
    if not counts:
        return 0
    mid = len(counts) // 2
    if len(counts) % 2:
        return counts[mid]
    return (counts[mid - 1] + counts[mid]) / 2


def _profile_command_median(report: dict, profile: str) -> float:
    return _profile_metric_median(report, profile, "n_commands")


def build_profile_domain_dataset(reports: list[dict]) -> str:
    """Build JSON dataset for the profile x domain grouped bar chart."""
    aggregated = _aggregate_profile_across_reports(reports)
    profiles = sorted(aggregated.keys(), key=_profile_sort_key)
    latest_reports = _latest_per_profile(reports)

    breakdowns = {
        p: _profile_breakdown(latest_reports.get(p, {}), p, "domain") for p in profiles
    }
    all_domains = sorted({d for b in breakdowns.values() for d in b})

    datasets = []
    for pname in profiles:
        b = breakdowns[pname]
        datasets.append(
            {
                "label": pname,
                "data": [b.get(d, 0) * 100 for d in all_domains],
                "backgroundColor": PROFILE_COLORS.get(_surface(pname), "#64748b"),
            }
        )

    return json.dumps({"labels": all_domains, "datasets": datasets})


def build_chart_data(reports: list[dict]) -> str:
    """Build all chart data as a single JSON blob so JS avoids f-string issues."""
    aggregated = _aggregate_profile_across_reports(reports)
    profiles = sorted(aggregated.keys(), key=_profile_sort_key)
    profile_colors = [PROFILE_COLORS.get(_surface(p), "#929088") for p in profiles]
    latest_reports = _latest_per_profile(reports)

    latest_rates = [aggregated[p]["latest_pass_rate"] * 100 for p in profiles]
    latest_costs = [aggregated[p]["latest_cost"] for p in profiles]
    latest_durations = [
        round(_profile_duration_mean(latest_reports.get(p, {}), p), 1) for p in profiles
    ]
    latest_cost_per_pass = [
        round(aggregated[p]["latest_cost"] / aggregated[p]["latest_passed"], 2)
        if aggregated[p]["latest_passed"]
        else 0
        for p in profiles
    ]

    efficiency_points = [
        {
            "x": round(aggregated[p]["latest_cost"], 4),
            "y": round(aggregated[p]["latest_pass_rate"] * 100, 1),
            "label": p,
        }
        for p in profiles
    ]

    diff_order = {"easy": 0, "medium": 1, "hard": 2}
    diff_breakdowns = {
        p: _profile_breakdown(latest_reports.get(p, {}), p, "difficulty")
        for p in profiles
    }
    difficulty_labels = sorted(
        {d for b in diff_breakdowns.values() for d in b},
        key=lambda d: diff_order.get(d, 99),
    )
    difficulty_datasets = [
        {
            "label": p,
            "data": [diff_breakdowns[p].get(d, 0) * 100 for d in difficulty_labels],
            "backgroundColor": profile_colors[i],
        }
        for i, p in enumerate(profiles)
    ]

    latest_commands = [
        _profile_command_median(latest_reports.get(p, {}), p) for p in profiles
    ]
    latest_skill_reads = [
        _profile_metric_median(latest_reports.get(p, {}), p, "skill_reads")
        for p in profiles
    ]
    latest_skills_consulted = [
        _profile_metric_median(latest_reports.get(p, {}), p, "skills_consulted")
        for p in profiles
    ]
    has_skill_data = any(
        "skill_reads" in t
        for p in profiles
        for t in latest_reports.get(p, {}).get("tests", [])
        if t.get("agent") == p
    )

    return json.dumps(
        {
            "profiles": profiles,
            "colors": profile_colors,
            "fillColors": [_hex_to_rgba(c, 0.6) for c in profile_colors],
            "latestRates": latest_rates,
            "latestCosts": latest_costs,
            "latestDurations": latest_durations,
            "latestCostPerPass": latest_cost_per_pass,
            "latestCommands": latest_commands,
            "latestSkillReads": latest_skill_reads,
            "latestSkillsConsulted": latest_skills_consulted,
            "hasSkillData": has_skill_data,
            "efficiencyPoints": efficiency_points,
            "difficultyLabels": difficulty_labels,
            "difficultyDatasets": difficulty_datasets,
        }
    )


TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Benchmark Dashboard</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Spectral:wght@400;600;700&family=Roboto:wght@400;500;700&family=DM+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
  :root {
    --dk-black: #1A1A1A;
    --dk-white: #FFFEF9;
    --dk-dark-green: #06312E;
    --dk-beige: #F8F4E4;
    --dk-green: #3EDAB2;
    --dk-light-green: #C7FFF1;
    --dk-blue: #7092F2;
    --dk-orange: #EDAB4F;
    --dk-grey: #929088;
    --dk-dark-grey: #2F2E2B;
  }
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    font-family: "Roboto", system-ui, -apple-system, sans-serif;
    background: var(--dk-white);
    color: var(--dk-black);
    padding: 0;
  }
  .header {
    background: var(--dk-dark-green);
    padding: 20px 24px 16px;
  }
  .header h1 {
    font-family: "Spectral", Georgia, serif;
    font-size: 28px;
    font-weight: 700;
    color: var(--dk-white);
  }
  .header .subtitle {
    font-size: 13px;
    color: rgba(255,254,249,0.6);
    margin-top: 2px;
  }
  .content { padding: 16px 24px 32px; }
  .section { margin-bottom: 20px; }
  .section-title {
    font-size: 11px;
    font-weight: 500;
    color: var(--dk-grey);
    text-transform: uppercase;
    letter-spacing: 0.05em;
    margin-bottom: 10px;
  }
  .summary {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(100px, 1fr));
    gap: 8px;
    margin-bottom: 16px;
  }
  .summary-item {
    background: var(--dk-beige);
    border-radius: 8px;
    padding: 10px 12px;
    text-align: center;
  }
  .summary-item .label {
    font-size: 10px;
    color: var(--dk-grey);
    text-transform: uppercase;
    letter-spacing: 0.03em;
    font-weight: 500;
  }
  .summary-item .val {
    font-family: "DM Mono", "Courier New", monospace;
    font-size: 18px;
    font-weight: 500;
    color: var(--dk-black);
    margin-top: 2px;
  }
  .profile-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: 8px;
    margin-bottom: 20px;
  }
  .profile-card {
    background: var(--dk-beige);
    border-radius: 8px;
    padding: 10px 12px;
  }
  .profile-name {
    font-family: "DM Mono", monospace;
    font-size: 11px;
    font-weight: 500;
    color: var(--dk-dark-grey);
  }
  .profile-model {
    font-size: 10px;
    color: var(--dk-grey);
    margin: 1px 0 3px;
  }
  .profile-stat {
    display: flex;
    align-items: baseline;
    gap: 6px;
  }
  .profile-rate {
    font-family: "DM Mono", monospace;
    font-size: 20px;
    font-weight: 500;
  }
  .profile-rate.green { color: var(--dk-dark-green); }
  .profile-rate.yellow { color: var(--dk-orange); }
  .profile-rate.red { color: var(--dk-black); opacity: 0.4; }
  .profile-meta {
    font-size: 10px;
    color: var(--dk-grey);
  }
  .card {
    background: var(--dk-beige);
    border-radius: 10px;
    padding: 14px;
  }
  .card.full { grid-column: 1 / -1; }
  .card canvas { width: 100% !important; height: 240px !important; }
  .card.full canvas { height: 300px !important; }
  .card-title {
    font-size: 10px;
    font-weight: 500;
    color: var(--dk-grey);
    text-transform: uppercase;
    letter-spacing: 0.04em;
    margin-bottom: 10px;
  }
  .grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
  table { width: 100%; border-collapse: collapse; }
  th {
    font-family: "DM Mono", monospace;
    font-size: 10px;
    font-weight: 500;
    text-align: left;
    padding: 5px 8px;
    color: var(--dk-grey);
    text-transform: uppercase;
    letter-spacing: 0.03em;
    border-bottom: 1px solid rgba(26,26,26,0.08);
    white-space: nowrap;
  }
  td {
    padding: 5px 8px;
    font-size: 12px;
    border-bottom: 1px solid rgba(26,26,26,0.05);
  }
  tbody tr:hover { background: rgba(62,218,178,0.06); }
  .muted { color: var(--dk-grey); }
  .stat-value { font-family: "DM Mono", monospace; font-weight: 500; }
  .stat-value.green { color: var(--dk-dark-green); }
  .stat-value.yellow { color: var(--dk-orange); }
  .stat-value.red { color: var(--dk-black); opacity: 0.4; }
  .stat-value.pass { color: var(--dk-dark-green); }
  .stat-value.fail { color: var(--dk-black); opacity: 0.3; }
  .stat-value.warn { color: var(--dk-orange); }
  .badge {
    display: inline-block;
    font-family: "DM Mono", monospace;
    font-size: 10px;
    font-weight: 500;
    padding: 1px 5px;
    border-radius: 3px;
  }
  .badge.pass { background: rgba(62,218,178,0.15); color: var(--dk-dark-green); }
  .badge.fail { background: rgba(26,26,26,0.05); color: var(--dk-grey); }
  .badge.timeout { background: rgba(237,171,79,0.18); color: #8a5a12; }
  .profile-timeout {
    display: inline-block;
    margin-top: 4px;
    font-family: "DM Mono", monospace;
    font-size: 10px;
    font-weight: 500;
    color: #8a5a12;
    background: rgba(237,171,79,0.18);
    border-radius: 3px;
    padding: 1px 5px;
  }
  .table-controls {
    display: flex;
    align-items: center;
    gap: 10px;
    margin-bottom: 8px;
    flex-wrap: wrap;
  }
  .table-controls input[type=text] {
    background: var(--dk-white);
    border: 1px solid rgba(26,26,26,0.12);
    color: var(--dk-black);
    border-radius: 6px;
    padding: 5px 10px;
    font-size: 12px;
    flex: 1;
    min-width: 160px;
  }
  .table-controls input[type=text]:focus {
    outline: none;
    border-color: var(--dk-green);
    box-shadow: 0 0 0 2px rgba(62,218,178,0.15);
  }
  .table-controls .toggle {
    font-size: 11px;
    color: var(--dk-grey);
    display: flex;
    align-items: center;
    gap: 4px;
    cursor: pointer;
    user-select: none;
  }
</style>
</head>
<body>

<div class="header">
  <h1>&#9670; Benchmark Dashboard</h1>
  <div class="subtitle">{run_count} runs &middot; {scenario_count} scenarios &middot; {profile_count} profiles &middot; {date_range} &middot; generated {generated_at}</div>
</div>

<div class="content">

<div class="summary">
  <div class="summary-item">
    <div class="label">Runs</div>
    <div class="val">{run_count}</div>
  </div>
  <div class="summary-item">
    <div class="label">Pass rate</div>
    <div class="val" style="color:#06312E;">{overall_rate:.0%}</div>
  </div>
  <div class="summary-item">
    <div class="label">Total cost</div>
    <div class="val">${total_cost:.2f}</div>
  </div>
  <div class="summary-item">
    <div class="label">Timeouts</div>
    <div class="val" style="color:#8a5a12;">{total_timed_out}</div>
  </div>
  <div class="summary-item">
    <div class="label">Scenarios</div>
    <div class="val">{scenario_count}</div>
  </div>
  <div class="summary-item">
    <div class="label">Profiles</div>
    <div class="val">{profile_count}</div>
  </div>
  <div class="summary-item">
    <div class="label">Token in/out</div>
    <div class="val" style="font-size:14px;">{total_in_tokens} / {total_out_tokens}</div>
  </div>
</div>

{profile_cards_html}

<div class="section">
  <div class="section-title">Profile comparison &mdash; latest results</div>
  <div class="grid-2">
    <div class="card">
      <div class="card-title">Pass rate</div>
      <canvas id="profileCompareChart"></canvas>
    </div>
    <div class="card">
      <div class="card-title">Cost per profile</div>
      <canvas id="profileCostChart"></canvas>
    </div>
    <div class="card">
      <div class="card-title">Cost per passing test (lower is better)</div>
      <canvas id="costPerPassChart"></canvas>
    </div>
    <div class="card">
      <div class="card-title">Median commands per scenario (effort)</div>
      <canvas id="commandsChart"></canvas>
    </div>
    <div class="card">
      <div class="card-title">Mean duration per scenario (s)</div>
      <canvas id="profileDurationChart"></canvas>
    </div>
    <div class="card">
      <div class="card-title">Cost-efficiency (best: high rate, low cost)</div>
      <canvas id="efficiencyChart"></canvas>
    </div>
  </div>
</div>

<div class="section">
  <div class="section-title">Breakdown by difficulty &amp; domain</div>
  <div class="grid-2">
    <div class="card">
      <div class="card-title">Pass rate by difficulty</div>
      <canvas id="difficultyChart"></canvas>
    </div>
    <div class="card full">
      <div class="card-title">Pass rate by domain</div>
      <canvas id="profileDomainChart"></canvas>
    </div>
  </div>
</div>

<div class="section" id="skillSection">
  <div class="section-title">Skill usage &mdash; how much agents lean on skill docs</div>
  <div class="grid-2">
    <div class="card">
      <div class="card-title">Median skill-doc reads per scenario</div>
      <canvas id="skillReadsChart"></canvas>
    </div>
    <div class="card">
      <div class="card-title">Median distinct skills consulted per scenario</div>
      <canvas id="skillsConsultedChart"></canvas>
    </div>
  </div>
</div>

<div class="section">
  <div class="section-title">Run history</div>
  <div class="card full">
    <table>
      <thead>
        <tr>
          <th>Run</th>
          <th>Date</th>
          <th>SHA</th>
          <th>Pass rate</th>
          <th>Tests</th>
          <th>Duration</th>
          <th>Cost</th>
          <th>Profiles</th>
        </tr>
      </thead>
      <tbody>
{runs_table}
      </tbody>
    </table>
  </div>
</div>

<div class="section">
  <div class="section-title">Per-scenario results &mdash; latest run per profile</div>
  <div class="card full">
    <div class="table-controls">
      <input type="text" id="scenarioSearch" placeholder="Filter by name, domain, or difficulty" oninput="filterScenarios()">
      <label class="toggle"><input type="checkbox" id="failsOnly" onchange="filterScenarios()"> Failures only</label>
      <span class="muted" id="scenarioCount"></span>
    </div>
    <table id="scenarioTable">
      <thead>
        <tr>
          <th>Scenario</th>
          <th>Domain</th>
          <th>Diff</th>
{scenario_table_headers}
          <th>Pass</th>
        </tr>
      </thead>
      <tbody>
{scenario_table_body}
      </tbody>
    </table>
  </div>
</div>

</div>

<script>
const DATA = {chart_data};

function makeBarChart(id, labels, data, colors, opts) {{
  new Chart(document.getElementById(id), {{
    type: 'bar',
    data: {{ labels, datasets: [{{ data, backgroundColor: colors, borderRadius: 3 }}] }},
    options: {{
      responsive: true, maintainAspectRatio: false,
      indexAxis: 'y',
      plugins: {{ legend: {{ display: false }} }},
      scales: {{
        x: {{ ...(opts.x || {{}}), ticks: {{ color: '#929088', ...(opts.xTicks || {{}}) }}, grid: {{ color: 'rgba(26,26,26,0.06)' }} }},
        y: {{ ticks: {{ color: '#2F2E2B', font: {{ size: 11 }} }}, grid: {{ display: false }} }},
      }},
      ...(opts.extra || {{}})
    }}
  }});
}}

makeBarChart('profileCompareChart', DATA.profiles, DATA.latestRates, DATA.fillColors, {{
  x: {{ min: 0, max: 100 }}, xTicks: {{ callback: v => v + '%' }}
}});

makeBarChart('profileCostChart', DATA.profiles, DATA.latestCosts, DATA.fillColors, {{
  xTicks: {{ callback: v => '$' + v }}
}});

makeBarChart('profileDurationChart', DATA.profiles, DATA.latestDurations, DATA.fillColors, {{
  xTicks: {{}}
}});

makeBarChart('costPerPassChart', DATA.profiles, DATA.latestCostPerPass, DATA.fillColors, {{
  xTicks: {{ callback: v => '$' + v }}
}});

makeBarChart('commandsChart', DATA.profiles, DATA.latestCommands, DATA.fillColors, {{
  xTicks: {{}}
}});

new Chart(document.getElementById('profileDomainChart'), {{
  type: 'bar',
  data: {profile_domain_data},
  options: {{
    responsive: true, maintainAspectRatio: false,
    plugins: {{ legend: {{ labels: {{ color: '#2F2E2B', font: {{ size: 10, family: 'DM Mono' }} }} }} }},
    scales: {{
      x: {{ ticks: {{ color: '#929088', font: {{ size: 10 }} }}, grid: {{ color: 'rgba(26,26,26,0.06)' }} }},
      y: {{ min: 0, max: 100, ticks: {{ color: '#929088', font: {{ size: 10 }}, callback: v => v + '%' }}, grid: {{ color: 'rgba(26,26,26,0.06)' }} }}
    }}
  }}
}});

new Chart(document.getElementById('efficiencyChart'), {{
  type: 'scatter',
  data: {{
    datasets: [{{
      data: DATA.efficiencyPoints,
      backgroundColor: DATA.colors,
      pointRadius: 7,
      pointHoverRadius: 10
    }}]
  }},
  options: {{
    responsive: true, maintainAspectRatio: false,
    plugins: {{
      legend: {{ display: false }},
      tooltip: {{ callbacks: {{
        label: ctx => ctx.raw.label + ': ' + ctx.raw.y + '% @ $' + ctx.raw.x
      }} }}
    }},
    scales: {{
      x: {{ title: {{ display: true, text: 'Cost (USD)', color: '#929088', font: {{ size: 11 }} }}, ticks: {{ color: '#929088', font: {{ size: 10 }}, callback: v => '$' + v }}, grid: {{ color: 'rgba(26,26,26,0.06)' }} }},
      y: {{ min: 0, max: 100, title: {{ display: true, text: 'Pass rate', color: '#929088', font: {{ size: 11 }} }}, ticks: {{ color: '#929088', font: {{ size: 10 }}, callback: v => v + '%' }}, grid: {{ color: 'rgba(26,26,26,0.06)' }} }}
    }}
  }}
}});

function makeGroupedBarChart(id, labels, datasets) {{
  new Chart(document.getElementById(id), {{
    type: 'bar',
    data: {{ labels, datasets }},
    options: {{
      responsive: true, maintainAspectRatio: false,
      plugins: {{ legend: {{ labels: {{ color: '#2F2E2B', font: {{ size: 10, family: 'DM Mono' }} }} }} }},
      scales: {{
        x: {{ ticks: {{ color: '#929088', font: {{ size: 10 }} }}, grid: {{ color: 'rgba(26,26,26,0.06)' }} }},
        y: {{ min: 0, max: 100, ticks: {{ color: '#929088', font: {{ size: 10 }}, callback: v => v + '%' }}, grid: {{ color: 'rgba(26,26,26,0.06)' }} }}
      }}
    }}
  }});
}}

makeGroupedBarChart('difficultyChart', DATA.difficultyLabels, DATA.difficultyDatasets);

if (DATA.hasSkillData) {{
  makeBarChart('skillReadsChart', DATA.profiles, DATA.latestSkillReads, DATA.fillColors, {{ xTicks: {{}} }});
  makeBarChart('skillsConsultedChart', DATA.profiles, DATA.latestSkillsConsulted, DATA.fillColors, {{ xTicks: {{}} }});
}} else {{
  document.getElementById('skillSection').style.display = 'none';
}}

function filterScenarios() {{
  const q = document.getElementById('scenarioSearch').value.toLowerCase();
  const failsOnly = document.getElementById('failsOnly').checked;
  const rows = document.querySelectorAll('#scenarioTable tbody tr');
  let shown = 0;
  rows.forEach(row => {{
    const text = (row.dataset.text || '').toLowerCase();
    const matchText = !q || text.includes(q);
    const matchFail = !failsOnly || row.dataset.fail === '1';
    const visible = matchText && matchFail;
    row.style.display = visible ? '' : 'none';
    if (visible) shown++;
  }});
  document.getElementById('scenarioCount').textContent = shown + ' shown';
}}
filterScenarios();
</script>
</body>
</html>"""


def generate(reports_dir: Path, run: str | None = None) -> str:
    reports = load_reports(reports_dir, run=run)

    total_passed = sum(r.get("passed", 0) for r in reports)
    total_tests = sum(r.get("total_tests", 0) for r in reports)
    total_timed_out = sum(r.get("timed_out", 0) for r in reports)
    total_cost = sum(r.get("total_cost_usd", 0) for r in reports)
    total_in_tokens = sum(r.get("total_input_tokens", 0) for r in reports)
    total_out_tokens = sum(r.get("total_output_tokens", 0) for r in reports)
    total_scenario_runs = sum(r.get("total_tests", 0) for r in reports)
    overall_rate = total_passed / total_tests if total_tests else 0.0

    all_scenarios = set()
    for r in reports:
        for t in r.get("tests", []):
            all_scenarios.add(t.get("test_id", ""))
    scenario_count = len(all_scenarios)

    aggregated = _aggregate_profile_across_reports(reports)

    start_date = _fmt_date(reports[0].get("timestamp", "")) if reports else "?"
    end_date = _fmt_date(reports[-1].get("timestamp", "")) if reports else "?"
    date_range = (
        f"{start_date} \u2013 {end_date}" if start_date != end_date else start_date
    )

    return _render_template(
        TEMPLATE,
        generated_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
        run_count=len(reports),
        overall_rate=overall_rate,
        overall_rate_class=_rate_class(overall_rate),
        total_cost=total_cost,
        total_timed_out=total_timed_out,
        total_in_tokens=_fmt_tokens(total_in_tokens),
        total_out_tokens=_fmt_tokens(total_out_tokens),
        total_scenario_runs=total_scenario_runs,
        scenario_count=scenario_count,
        profile_count=len(aggregated),
        date_range=date_range,
        runs_table=build_runs_table(reports),
        scenario_table_headers=build_scenario_table(reports)[0],
        scenario_table_body=build_scenario_table(reports)[1],
        profile_cards_html=build_profile_cards(aggregated),
        chart_data=build_chart_data(reports),
        profile_domain_data=build_profile_domain_dataset(reports),
    )


def main():
    parser = argparse.ArgumentParser(description="Generate benchmark trend dashboard")
    parser.add_argument(
        "--output", "-o", type=str, default=None, help="Output HTML path"
    )
    parser.add_argument("--no-open", action="store_true", help="Don't open in browser")
    parser.add_argument(
        "--run",
        type=str,
        default=None,
        help="Scope to a single run (run_id / dir name, or 'latest')",
    )
    args = parser.parse_args()

    html = generate(REPORTS_DIR, run=args.run)

    if args.output:
        out_path = Path(args.output)
    else:
        out_path = REPORTS_DIR / "_dashboard.html"
    out_path.write_text(html)
    run_count = len(load_reports(REPORTS_DIR, run=args.run))
    print(f"  Dashboard written to {out_path}")
    print(f"  {run_count} run(s) loaded")

    if not args.no_open:
        webbrowser.open(f"file://{out_path.resolve()}")


if __name__ == "__main__":
    main()
