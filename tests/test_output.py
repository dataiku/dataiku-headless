"""Tests for output module."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest
import typer

from dku_cli.output import error, render, resolve_output_format, set_error_format


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


def test_error_always_writes_rich_text(capsys):
    """error() always writes Rich text to stderr, even in JSON error mode."""
    set_error_format("json")
    error("something went wrong")
    captured = capsys.readouterr()
    assert "something went wrong" in captured.err
    # Should NOT be JSON — error() is a human-readable stderr helper
    assert '"error"' not in captured.err
    set_error_format("text")


def test_exit_with_error_text_mode(capsys):
    """exit_with_error in text mode prints to stderr and exits."""
    from dku_cli.errors import exit_with_error

    set_error_format("text")
    with pytest.raises(SystemExit) as exc_info:
        exit_with_error("bad thing happened", code="test_error", status=1)
    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert "bad thing happened" in captured.err


def test_exit_with_error_json_mode(capsys):
    """exit_with_error in JSON mode emits structured error to stderr."""
    from dku_cli.errors import exit_with_error

    set_error_format("json")
    with pytest.raises(SystemExit) as exc_info:
        exit_with_error("broken", code="my_code", details=["detail1"], status=3)
    assert exc_info.value.code == 3
    captured = capsys.readouterr()
    payload = json.loads(captured.err)
    assert payload["error"]["code"] == "my_code"
    assert payload["error"]["message"] == "broken"
    assert payload["error"]["details"] == ["detail1"]
    assert payload["error"]["exit_code"] == 3
    set_error_format("text")


def test_exit_with_error_json_defaults(capsys):
    """exit_with_error defaults: code='cli_error', status=1, details=[]."""
    from dku_cli.errors import exit_with_error

    set_error_format("json")
    with pytest.raises(SystemExit) as exc_info:
        exit_with_error("oops")
    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    payload = json.loads(captured.err)
    assert payload["error"]["code"] == "cli_error"
    assert payload["error"]["details"] == []
    set_error_format("text")


def test_set_error_format_rejects_invalid():
    with pytest.raises(ValueError, match="Error format must be"):
        set_error_format("xml")


def test_resolve_output_format_uses_config_default():
    with patch("dku_cli.config.get_default_output", return_value="json"):
        assert resolve_output_format(None) == "json"


def test_resolve_output_format_rejects_invalid_explicit_value():
    with pytest.raises(typer.BadParameter):
        resolve_output_format("yaml")


def test_resolve_output_format_falls_back_when_config_is_incompatible():
    with patch("dku_cli.config.get_default_output", return_value="csv"):
        assert (
            resolve_output_format(None, allowed=("text", "json"), default="text")
            == "text"
        )
