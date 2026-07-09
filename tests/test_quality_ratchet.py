"""Tests for the CI quality-ratchet checker (scripts/check_quality_ratchet.py).

The script is not an importable package, so load it from its path.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location(
    "check_quality_ratchet", ROOT / "scripts" / "check_quality_ratchet.py"
)
ratchet = importlib.util.module_from_spec(_SPEC)
assert _SPEC.loader is not None
_SPEC.loader.exec_module(ratchet)


def _state(
    complexity=(),
    line_length=None,
    line_length_max=None,
    ruff_select="C901,E501",
    oversized_files=None,
    broad_exceptions=None,
    inline_enum_validation=None,
    raw_settings_saves=None,
):
    return {
        "ruff_select": ruff_select,
        "complexity": list(complexity),
        "line_length": dict(line_length or {}),
        "line_length_max": dict(line_length_max or {}),
        "oversized_files": dict(oversized_files or {}),
        "broad_exceptions": dict(broad_exceptions or {}),
        "inline_enum_validation": dict(inline_enum_validation or {}),
        "raw_settings_saves": dict(raw_settings_saves or {}),
    }


def _patch(monkeypatch, baseline, current):
    monkeypatch.setattr(ratchet, "_load_baseline", lambda: baseline)
    monkeypatch.setattr(ratchet, "_current_baseline", lambda: current)


def test_complexity_key_extracts_function_name():
    diag = {
        "filename": str(ROOT / "src" / "dku_cli" / "errors.py"),
        "message": "`handle_api_error` is too complex (12 > 10)",
    }
    assert ratchet._complexity_key(diag) == "src/dku_cli/errors.py::handle_api_error"


def test_e501_length_parses_actual_length():
    assert ratchet._e501_length({"message": "Line too long (123 > 88)"}) == 123
    assert ratchet._e501_length({"message": "unparseable"}) == 0


def test_count_broad_exceptions_ignores_marked_exception(tmp_path):
    path = tmp_path / "sample.py"
    path.write_text(
        "try:\n"
        "    work()\n"
        "except Exception:  # quality-ratchet: allow-broad-exception\n"
        "    recover()\n"
    )

    assert ratchet._count_broad_exceptions(path) == 0


def test_count_broad_exceptions_counts_unmarked_exception(tmp_path):
    path = tmp_path / "sample.py"
    path.write_text("try:\n    work()\nexcept Exception:\n    recover()\n")

    assert ratchet._count_broad_exceptions(path) == 1


def test_check_passes_when_unchanged(monkeypatch, capsys):
    state = _state(line_length={"a.py": 2}, line_length_max={"a.py": 95})
    _patch(monkeypatch, state, dict(state))
    ratchet._check()  # must not raise
    assert "Quality ratchet OK" in capsys.readouterr().out


def test_check_fails_on_new_complexity(monkeypatch):
    _patch(monkeypatch, _state(), _state(complexity=["a.py::foo"]))
    with pytest.raises(SystemExit):
        ratchet._check()


def test_check_fails_on_increased_count(monkeypatch):
    _patch(
        monkeypatch,
        _state(line_length={"a.py": 1}, line_length_max={"a.py": 90}),
        _state(line_length={"a.py": 2}, line_length_max={"a.py": 90}),
    )
    with pytest.raises(SystemExit):
        ratchet._check()


def test_check_fails_on_new_raw_settings_save(monkeypatch, capsys):
    _patch(
        monkeypatch,
        _state(raw_settings_saves={"src/dku_cli/commands/a.py": 1}),
        _state(raw_settings_saves={"src/dku_cli/commands/a.py": 2}),
    )
    with pytest.raises(SystemExit):
        ratchet._check()
    assert "locked_settings" in capsys.readouterr().err


def test_check_fails_on_increased_max_even_if_count_unchanged(monkeypatch):
    # The gaming case: swap a 90-char line for a 300-char one — count is flat but
    # the longest line grows. The max guard must catch it.
    _patch(
        monkeypatch,
        _state(line_length={"a.py": 1}, line_length_max={"a.py": 90}),
        _state(line_length={"a.py": 1}, line_length_max={"a.py": 300}),
    )
    with pytest.raises(SystemExit):
        ratchet._check()


def test_check_fails_on_ruff_select_mismatch(monkeypatch):
    _patch(monkeypatch, _state(ruff_select="C901"), _state())
    with pytest.raises(SystemExit):
        ratchet._check()


def test_check_passes_when_debt_decreases(monkeypatch, capsys):
    # Debt going DOWN must never turn CI red.
    _patch(
        monkeypatch,
        _state(
            complexity=["a.py::foo"],
            line_length={"a.py": 3},
            line_length_max={"a.py": 120},
        ),
        _state(line_length={"a.py": 1}, line_length_max={"a.py": 100}),
    )
    ratchet._check()  # must not raise
    out = capsys.readouterr().out
    assert "Quality ratchet OK" in out
    assert "baseline can tighten" in out


def test_baseline_diff_reports_widened_debt():
    old = _state(
        complexity=["a.py::foo"],
        line_length={"a.py": 1},
        line_length_max={"a.py": 90},
        oversized_files={"big.py": 251},
        broad_exceptions={"broad.py": 1},
        inline_enum_validation={"enum.py": 1},
    )
    new = _state(
        complexity=["a.py::foo", "b.py::bar"],
        line_length={"a.py": 2},
        line_length_max={"a.py": 120},
        oversized_files={"big.py": 252},
        broad_exceptions={"broad.py": 2},
        inline_enum_validation={"enum.py": 2},
    )

    failures = ratchet._baseline_widenings(old, new)

    assert "New baseline C901 entries" in "\n".join(failures)
    assert "Baseline E501 counts widened" in "\n".join(failures)
    assert "Baseline E501 max widened" in "\n".join(failures)
    assert "Baseline oversized-file debt widened" in "\n".join(failures)
    assert "Baseline broad-exception debt widened" in "\n".join(failures)
    assert "Baseline inline-enum-validation debt widened" in "\n".join(failures)


def test_baseline_diff_allows_tightening():
    old = _state(
        complexity=["a.py::foo"],
        line_length={"a.py": 2},
        line_length_max={"a.py": 120},
        oversized_files={"big.py": 252},
        broad_exceptions={"broad.py": 2},
        inline_enum_validation={"enum.py": 2},
    )
    new = _state(
        line_length={"a.py": 1},
        line_length_max={"a.py": 90},
        oversized_files={"big.py": 251},
        broad_exceptions={"broad.py": 1},
        inline_enum_validation={"enum.py": 1},
    )

    assert ratchet._baseline_widenings(old, new) == []
