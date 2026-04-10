"""Manage the benchmark baselines.json file."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from .reader import load_run

logger = logging.getLogger(__name__)

BASELINES_PATH = Path(__file__).parent.parent / "baselines.json"


def load_baselines() -> dict:
    """Load baselines.json.

    Returns empty dict structure if the file does not exist or is
    malformed.
    """
    if not BASELINES_PATH.is_file():
        return {}
    try:
        with open(BASELINES_PATH) as f:
            data = json.load(f)
        if not isinstance(data, dict):
            logger.warning("baselines.json is not a dict, returning empty")
            return {}
        return data
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Failed to load baselines.json: %s", exc)
        return {}


def set_baseline(run_id: str) -> dict:
    """Read a run's summary, extract per-test scores, write baselines.json.

    Returns the baselines dict that was written.
    Raises ValueError if the run cannot be loaded.
    """
    run = load_run(run_id)
    if run is None:
        raise ValueError(f"Cannot load run: {run_id}")

    agent = run.get("agent", "claude")
    scores: dict[str, dict] = {}
    for test in run.get("tests", []):
        tid = test.get("test_id")
        if tid is None:
            continue
        scores[tid] = {
            "agent": agent,
            "score": test.get("overall_score", 0.0),
        }

    baselines = {
        "baseline_run_id": run_id,
        "set_at": datetime.now(timezone.utc).isoformat(),
        "scores": scores,
    }

    try:
        with open(BASELINES_PATH, "w") as f:
            json.dump(baselines, f, indent=2)
            f.write("\n")
    except OSError as exc:
        logger.error("Failed to write baselines.json: %s", exc)
        raise

    return baselines


def get_baseline_score(test_id: str, agent: str = "claude") -> float | None:
    """Get baseline score for a specific test, or None if no baseline.

    Only returns the score if the baseline agent matches the requested
    agent.
    """
    baselines = load_baselines()
    scores = baselines.get("scores", {})
    entry = scores.get(test_id)
    if entry is None:
        return None
    if entry.get("agent") != agent:
        return None
    return entry.get("score")
