"""Scan and load benchmark summary.json files."""

from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def get_reports_dir() -> Path:
    """Return the default reports directory (benchmark/reports/)."""
    return Path(__file__).parent.parent / "reports"


def load_run(run_id: str, reports_dir: Path | None = None) -> dict | None:
    """Load a specific run's summary.json.

    Returns None if the run directory or summary.json does not exist
    or the file is malformed.
    """
    reports = reports_dir or get_reports_dir()
    summary_path = reports / run_id / "summary.json"
    if not summary_path.is_file():
        logger.warning("Summary not found: %s", summary_path)
        return None
    try:
        with open(summary_path) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Failed to load %s: %s", summary_path, exc)
        return None


def load_all_runs(reports_dir: Path | None = None) -> list[dict]:
    """Scan benchmark/reports/bench_*/summary.json files.

    Returns a list of summary dicts sorted by run_id (chronological,
    oldest first). Malformed or missing files are silently skipped
    with a warning log.
    """
    reports = reports_dir or get_reports_dir()
    if not reports.is_dir():
        logger.warning("Reports directory does not exist: %s", reports)
        return []

    runs: list[dict] = []
    for run_dir in sorted(reports.iterdir()):
        if not run_dir.is_dir() or not run_dir.name.startswith("bench_"):
            continue
        summary_path = run_dir / "summary.json"
        if not summary_path.is_file():
            logger.warning("No summary.json in %s, skipping", run_dir.name)
            continue
        try:
            with open(summary_path) as f:
                data = json.load(f)
            runs.append(data)
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Failed to load %s: %s", summary_path, exc)
            continue

    return runs
