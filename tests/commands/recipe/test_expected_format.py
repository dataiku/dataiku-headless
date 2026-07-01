"""Prompt recipe resultValidation.expectedFormat guard (#227)."""

from __future__ import annotations

import pytest

from dku_cli.commands.recipe.settings import _reject_unsafe_expected_format


def test_expected_format_json_is_rejected(capsys):
    with pytest.raises(SystemExit) as excinfo:
        _reject_unsafe_expected_format(
            "prompt", {"resultValidation": {"expectedFormat": "JSON"}}
        )
    assert excinfo.value.code == 2
    err = capsys.readouterr().err
    assert "expectedFormat" in err
    assert "NONE" in err


def test_expected_format_none_is_allowed():
    # Returns without raising for the only verified-safe value.
    _reject_unsafe_expected_format(
        "prompt", {"resultValidation": {"expectedFormat": "NONE"}}
    )


def test_expected_format_absent_is_allowed():
    _reject_unsafe_expected_format(
        "prompt", {"resultValidation": {"requiredJSONObjectKeys": []}}
    )
    _reject_unsafe_expected_format("prompt", {"engineType": "CPU"})


def test_expected_format_ignored_for_non_prompt_recipe():
    # A non-prompt recipe is never gated, even with a bogus expectedFormat.
    _reject_unsafe_expected_format(
        "sync", {"resultValidation": {"expectedFormat": "JSON"}}
    )


def test_unknown_expected_format_value_is_rejected(capsys):
    with pytest.raises(SystemExit):
        _reject_unsafe_expected_format(
            "prompt", {"resultValidation": {"expectedFormat": "YAML"}}
        )
    assert "YAML" in capsys.readouterr().err
