"""Tests for output module."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest
import typer

from dku_cli.output import render, resolve_output_format


def test_render_json(capsys):
    data = [{"name": "test", "value": "123"}]
    render(data, ["name", "value"], output_format="json")
    captured = capsys.readouterr()
    parsed = json.loads(captured.out)
    assert len(parsed) == 1
    assert parsed[0]["name"] == "test"
    assert parsed[0]["value"] == "123"


def test_render_csv(capsys):
    data = [{"name": "test", "value": "123"}]
    render(data, ["name", "value"], output_format="csv")
    captured = capsys.readouterr()
    lines = captured.out.strip().split("\n")
    assert len(lines) == 2
    assert "name" in lines[0]
    assert "test" in lines[1]


def test_render_json_filters_columns(capsys):
    data = [{"name": "test", "value": "123", "extra": "hidden"}]
    render(data, ["name", "value"], output_format="json")
    captured = capsys.readouterr()
    parsed = json.loads(captured.out)
    assert "extra" not in parsed[0]


def test_render_empty_data(capsys):
    render([], ["name"], output_format="json")
    captured = capsys.readouterr()
    parsed = json.loads(captured.out)
    assert parsed == []


def test_resolve_output_format_uses_config_default():
    with patch("dku_cli.config.get_default_output", return_value="json"):
        assert resolve_output_format(None) == "json"


def test_resolve_output_format_rejects_invalid_explicit_value():
    with pytest.raises(typer.BadParameter):
        resolve_output_format("yaml")


def test_resolve_output_format_falls_back_when_config_is_incompatible():
    with patch("dku_cli.config.get_default_output", return_value="csv"):
        assert resolve_output_format(None, allowed=("text", "json"), default="text") == "text"
