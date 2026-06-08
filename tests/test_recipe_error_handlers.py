"""Tests for prescriptive error messages on recipe-build failures."""

from __future__ import annotations

from dku_cli.errors import _handle_fold_plugin_missing, _handle_pivot_modality_scan


def test_pivot_modality_scan_matched():
    msg = (
        "DSS API error: Job run did not finish. Status: FAILED\n"
        "com.dataiku.dip.recipes.RecipeSchemaComputer$DontWantToCompute: "
        "Modality lists stored in output schema are not up-to-date"
    )
    result = _handle_pivot_modality_scan(msg)
    assert result is not None
    message, details = result
    assert "modality" in message.lower()
    assert "UI-only" in message
    # Detail must explain the explicit-values pitfall and the restructure fix
    joined = "\n".join(details)
    assert "explicitValues" in joined
    assert "redesign" in joined.lower() or "restructure" in joined.lower()
    assert "add-formula" in joined


def test_pivot_modality_unrelated_error_returns_none():
    msg = "ApplicativeException: Empty column name"
    assert _handle_pivot_modality_scan(msg) is None


def test_fold_plugin_missing_matched():
    msg = "FoldColumnsByName was available in a plugin that is not installed."
    result = _handle_fold_plugin_missing(msg)
    assert result is not None
    message, details = result
    assert "FoldColumnsByName" in message
    assert "plugin" in message.lower()
    joined = "\n".join(details)
    assert "uv tool install" in joined
    assert "MultiColumnFold" in joined
    # Must explicitly forbid the pd.melt fallback
    assert "pd.melt" in joined.lower() or "pd.melt" in joined


def test_fold_plugin_partial_match_returns_none():
    """Only the FoldColumnsByName + plugin combo should fire."""
    assert _handle_fold_plugin_missing("FoldColumnsByName step added.") is None
    assert (
        _handle_fold_plugin_missing("Some other plugin that is not installed") is None
    )
