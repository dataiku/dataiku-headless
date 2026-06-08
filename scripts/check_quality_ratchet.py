"""Check Ruff complexity and line-length debt against a committed baseline."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "quality" / "ruff-ratchet-baseline.json"
RUFF_SELECT = "C901,E501"


def _run_ruff() -> list[dict[str, Any]]:
    result = subprocess.run(
        [
            "uv",
            "run",
            "ruff",
            "check",
            "--select",
            RUFF_SELECT,
            "--output-format",
            "json",
            ".",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode not in (0, 1):
        print(result.stdout, end="")
        print(result.stderr, end="", file=sys.stderr)
        raise SystemExit(result.returncode)
    return json.loads(result.stdout or "[]")


def _relative_path(filename: str) -> str:
    return Path(filename).resolve().relative_to(ROOT).as_posix()


def _complexity_key(diagnostic: dict[str, Any]) -> str:
    match = re.search(r"`([^`]+)` is too complex", diagnostic["message"])
    name = match.group(1) if match else diagnostic["message"]
    return f"{_relative_path(diagnostic['filename'])}::{name}"


def _e501_length(diagnostic: dict[str, Any]) -> int:
    # Ruff's E501 message is "Line too long (NNN > 88)"; pull the actual length.
    match = re.search(r"\((\d+) >", diagnostic["message"])
    return int(match.group(1)) if match else 0


def _current_baseline() -> dict[str, Any]:
    diagnostics = _run_ruff()
    complexity = sorted(
        _complexity_key(diagnostic)
        for diagnostic in diagnostics
        if diagnostic["code"] == "C901"
    )
    e501 = [diagnostic for diagnostic in diagnostics if diagnostic["code"] == "E501"]
    line_length = Counter(_relative_path(diagnostic["filename"]) for diagnostic in e501)
    # Track the longest over-limit line per file so the count alone cannot be
    # gamed (deleting one long line to "pay" for adding a much longer one).
    line_length_max: dict[str, int] = {}
    for diagnostic in e501:
        path = _relative_path(diagnostic["filename"])
        line_length_max[path] = max(
            line_length_max.get(path, 0), _e501_length(diagnostic)
        )
    return {
        "ruff_select": RUFF_SELECT,
        "complexity": complexity,
        "line_length": dict(sorted(line_length.items())),
        "line_length_max": dict(sorted(line_length_max.items())),
    }


def _write_baseline() -> None:
    baseline = _current_baseline()
    BASELINE.write_text(json.dumps(baseline, indent=2, sort_keys=True) + "\n")
    print(
        "Wrote quality baseline: "
        f"{len(baseline['complexity'])} C901 entries, "
        f"{sum(baseline['line_length'].values())} E501 entries"
    )


def _load_baseline() -> dict[str, Any]:
    if not BASELINE.exists():
        raise SystemExit(
            f"Missing {BASELINE.relative_to(ROOT)}. "
            "Run scripts/check_quality_ratchet.py --write-baseline."
        )
    return json.loads(BASELINE.read_text())


_REGEN = "uv run python scripts/check_quality_ratchet.py --write-baseline"


def _check() -> None:
    baseline = _load_baseline()
    current = _current_baseline()

    if baseline.get("ruff_select") != RUFF_SELECT:
        raise SystemExit(
            f"Baseline ruff_select {baseline.get('ruff_select')!r} does not match "
            f"{RUFF_SELECT!r}. Regenerate it: {_REGEN}"
        )

    baseline_complexity = set(baseline["complexity"])
    current_complexity = set(current["complexity"])
    new_complexity = sorted(current_complexity - baseline_complexity)
    resolved_complexity = sorted(baseline_complexity - current_complexity)

    baseline_lengths = baseline["line_length"]
    current_lengths = current["line_length"]
    increased_lengths = {
        path: count
        for path, count in current_lengths.items()
        if count > baseline_lengths.get(path, 0)
    }
    reduced_lengths = {
        path: count
        for path, count in baseline_lengths.items()
        if current_lengths.get(path, 0) < count
    }

    baseline_max = baseline.get("line_length_max", {})
    current_max = current["line_length_max"]
    increased_max = {
        path: length
        for path, length in current_max.items()
        if length > baseline_max.get(path, 0)
    }

    # A ratchet only tightens: REGRESSIONS fail the build, improvements never do.
    failures: list[str] = []
    if new_complexity:
        failures.append("New C901 complexity violations:\n" + "\n".join(new_complexity))
    if increased_lengths:
        failures.append(
            "E501 line-length counts increased:\n"
            + "\n".join(
                f"{path}: {baseline_lengths.get(path, 0)} -> {count}"
                for path, count in sorted(increased_lengths.items())
            )
        )
    if increased_max:
        failures.append(
            "E501 longest line grew (count-gaming guard):\n"
            + "\n".join(
                f"{path}: {baseline_max.get(path, 0)} -> {length}"
                for path, length in sorted(increased_max.items())
            )
        )

    if failures:
        print("\n\n".join(failures), file=sys.stderr)
        print(
            "\nThese are NEW quality regressions. Fix them — or, if the change is "
            f"intentional, refresh the baseline:\n  {_REGEN}",
            file=sys.stderr,
        )
        raise SystemExit(1)

    # Improvements are advisory: report them, nudge to lock them in, but pass.
    improvements: list[str] = []
    if resolved_complexity:
        improvements.append(
            "C901 resolved (baseline can tighten):\n" + "\n".join(resolved_complexity)
        )
    if reduced_lengths:
        improvements.append(
            "E501 counts reduced (baseline can tighten):\n"
            + "\n".join(
                f"{path}: {count} -> {current_lengths.get(path, 0)}"
                for path, count in sorted(reduced_lengths.items())
            )
        )
    if improvements:
        print("\n\n".join(improvements))
        print(f"\nDebt decreased — lock it in with:\n  {_REGEN}")

    print(
        "Quality ratchet OK: "
        f"{len(current['complexity'])} C901 entries, "
        f"{sum(current['line_length'].values())} E501 entries"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--write-baseline",
        action="store_true",
        help="Refresh the committed Ruff quality baseline.",
    )
    args = parser.parse_args()

    if args.write_baseline:
        _write_baseline()
    else:
        _check()


if __name__ == "__main__":
    main()
