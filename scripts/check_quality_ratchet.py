from __future__ import annotations

import argparse
import ast
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


def _count_source_lines(filepath: Path) -> int:
    try:
        tree = ast.parse(filepath.read_text())
    except SyntaxError:
        return 0
    docstring_lines: set[int] = set()
    for node in ast.walk(tree):
        is_docstr_node = isinstance(
            node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
        )
        if is_docstr_node and node.body and isinstance(node.body[0], ast.Expr):
            val = node.body[0].value
            if isinstance(val, ast.Constant) and isinstance(val.value, str):
                start = node.body[0].lineno
                end = getattr(node.body[0], "end_lineno", start) or start
                for ln in range(start, end + 1):
                    docstring_lines.add(ln)
    significant = 0
    for i, line in enumerate(filepath.read_text().splitlines(), 1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or i in docstring_lines:
            continue
        significant += 1
    return significant


def _count_broad_exceptions(filepath: Path) -> int:
    try:
        tree = ast.parse(filepath.read_text())
    except SyntaxError:
        return 0

    class _BroadExceptFinder(ast.NodeVisitor):
        def __init__(self):
            self.count = 0

        def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
            if node.type is None:
                self.count += 1
            elif (isinstance(node.type, ast.Name) and node.type.id == "Exception") or (
                isinstance(node.type, ast.Attribute) and node.type.attr == "Exception"
            ):
                self.count += 1
            self.generic_visit(node)

    finder = _BroadExceptFinder()
    finder.visit(tree)
    return finder.count


_INLINE_ENUM_RE = re.compile(r"\.upper\(\)\s*not in\s*\{|\.lower\(\)\s*not in\s*\{")


def _count_inline_enum_validation(filepath: Path) -> int:
    content = filepath.read_text()
    return len(_INLINE_ENUM_RE.findall(content))


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
    src = ROOT / "src" / "dku_cli"
    oversized: dict[str, int] = {}
    broad_exceptions: dict[str, int] = {}
    inline_enum: dict[str, int] = {}

    for pyfile in sorted(src.rglob("*.py")):
        rel = pyfile.relative_to(ROOT).as_posix()
        lines = _count_source_lines(pyfile)
        if lines > 250:
            oversized[rel] = lines
        be = _count_broad_exceptions(pyfile)
        if be > 0:
            broad_exceptions[rel] = be
        ie = _count_inline_enum_validation(pyfile)
        if ie > 0:
            inline_enum[rel] = ie

    return {
        "ruff_select": RUFF_SELECT,
        "complexity": complexity,
        "line_length": dict(sorted(line_length.items())),
        "line_length_max": dict(sorted(line_length_max.items())),
        "oversized_files": dict(sorted(oversized.items())),
        "broad_exceptions": dict(sorted(broad_exceptions.items())),
        "inline_enum_validation": dict(sorted(inline_enum.items())),
    }


def _write_baseline() -> None:
    baseline = _current_baseline()
    BASELINE.write_text(json.dumps(baseline, indent=2, sort_keys=True) + "\n")
    print(
        "Wrote quality baseline: "
        f"{len(baseline['complexity'])} C901 entries, "
        f"{sum(baseline['line_length'].values())} E501 entries, "
        f"{len(baseline['oversized_files'])} oversized files, "
        f"{sum(baseline['broad_exceptions'].values())} broad exceptions, "
        f"{sum(baseline['inline_enum_validation'].values())} inline enum validations"
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

    def _dict_regression(
        baselines: dict[str, int], currents: dict[str, int]
    ) -> dict[str, int]:
        return {
            path: count
            for path, count in currents.items()
            if count > baselines.get(path, 0)
        }

    baseline_oversized = baseline.get("oversized_files", {})
    current_oversized = current.get("oversized_files", {})
    new_oversized = _dict_regression(baseline_oversized, current_oversized)

    baseline_be = baseline.get("broad_exceptions", {})
    current_be = current.get("broad_exceptions", {})
    new_be = _dict_regression(baseline_be, current_be)

    baseline_ie = baseline.get("inline_enum_validation", {})
    current_ie = current.get("inline_enum_validation", {})
    new_ie = _dict_regression(baseline_ie, current_ie)

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
    if new_oversized:
        failures.append(
            "New or worsened oversized files (>250 significant lines):\n"
            + "\n".join(
                f"{path}: {baseline_oversized.get(path, '-')} -> {count}"
                for path, count in sorted(new_oversized.items())
            )
        )
    if new_be:
        failures.append(
            "New or worsened broad exception counts:\n"
            + "\n".join(
                f"{path}: {baseline_be.get(path, '-')} -> {count}"
                for path, count in sorted(new_be.items())
            )
        )
    if new_ie:
        failures.append(
            "New or worsened inline enum validation patterns:\n"
            + "\n".join(
                f"{path}: {baseline_ie.get(path, '-')} -> {count}"
                for path, count in sorted(new_ie.items())
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
        f"{len(current['complexity'])} C901, "
        f"{sum(current['line_length'].values())} E501, "
        f"{len(current['oversized_files'])} oversized, "
        f"{sum(current['broad_exceptions'].values())} broad-except, "
        f"{sum(current['inline_enum_validation'].values())} inline-enum"
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
