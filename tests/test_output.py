"""Tests for output module."""

from __future__ import annotations

import json

import pytest

from dku_cli.output import (
    error,
    get_output_format,
    info,
    is_quiet,
    render,
    render_raw,
    resolve_output_format,
    set_output_format,
)


def test_render_json(capsys):
    data = [{"name": "test", "value": "123"}]
    render(data, ["name", "value"], output_format="json")
    captured = capsys.readouterr()
    parsed = json.loads(captured.out)
    assert len(parsed) == 1
    assert parsed[0]["name"] == "test"
    assert parsed[0]["value"] == "123"


def test_render_json_is_indented(capsys):
    render([{"name": "test"}], ["name"], output_format="json")
    captured = capsys.readouterr()
    assert captured.out.startswith("[\n")


def test_render_csv(capsys):
    data = [{"name": "test", "value": "123"}]
    render(data, ["name", "value"], output_format="csv")
    captured = capsys.readouterr()
    lines = captured.out.strip().split("\n")
    assert len(lines) == 2
    assert "name" in lines[0]
    assert "test" in lines[1]


def test_render_csv_uses_display_headers(capsys):
    data = [{"name": "test"}]
    render(data, ["name"], output_format="csv", headers={"name": "Display Name"})
    captured = capsys.readouterr()
    assert captured.out.splitlines()[0] == "Display Name"


def test_render_default_is_tsv(capsys):
    data = [{"name": "test", "value": "123"}]
    render(data, ["name", "value"])
    captured = capsys.readouterr()
    assert captured.out == "name\tvalue\ntest\t123\n"


def test_render_default_title_goes_to_stderr(capsys):
    data = [{"name": "test"}]
    render(data, ["name"], title="Datasets (1)")
    captured = capsys.readouterr()
    assert "Datasets (1)" not in captured.out
    assert "Datasets (1)" in captured.err


def test_render_default_missing_keys_are_empty(capsys):
    render([{"name": "test"}], ["name", "value"])
    captured = capsys.readouterr()
    assert captured.out == "name\tvalue\ntest\t\n"


def test_render_raw_default_is_compact_json(capsys):
    render_raw({"name": "test"})
    captured = capsys.readouterr()
    assert captured.out == '{"name":"test"}\n'


def test_render_raw_json_is_indented(capsys):
    render_raw({"name": "test"}, output_format="json")
    captured = capsys.readouterr()
    assert captured.out == '{\n  "name": "test"\n}\n'


def test_render_raw_non_dict_prints_str(capsys):
    render_raw("plain text")
    captured = capsys.readouterr()
    assert captured.out == "plain text\n"


def test_render_json_filters_columns(capsys):
    data = [{"name": "test", "value": "123", "extra": "hidden"}]
    render(data, ["name", "value"], output_format="json")
    captured = capsys.readouterr()
    parsed = json.loads(captured.out)
    assert "extra" not in parsed[0]


def test_render_json_fills_missing_keys(capsys):
    render([{"name": "test"}], ["name", "value"], output_format="json")
    captured = capsys.readouterr()
    parsed = json.loads(captured.out)
    assert parsed[0]["value"] == ""


def test_render_empty_data(capsys):
    render([], ["name"], output_format="json")
    captured = capsys.readouterr()
    parsed = json.loads(captured.out)
    assert parsed == []


def test_error_always_writes_text(capsys):
    """error() writes plain text to stderr, even in quiet mode."""
    set_output_format("quiet")
    error("something went wrong")
    captured = capsys.readouterr()
    assert "something went wrong" in captured.err


def test_quiet_suppresses_info(capsys):
    set_output_format("quiet")
    info("chatter")
    captured = capsys.readouterr()
    assert captured.err == ""


def test_exit_with_error_prints_message_and_details(capsys):
    from dku_cli.errors import exit_with_error

    with pytest.raises(SystemExit) as exc_info:
        exit_with_error("broken", details=["detail1"], status=3)
    assert exc_info.value.code == 3
    captured = capsys.readouterr()
    assert "broken" in captured.err
    assert "detail1" in captured.err


def test_set_output_format_rejects_invalid():
    with pytest.raises(ValueError, match="Output format must be"):
        set_output_format("table")


def test_set_output_format_none_restores_dense():
    set_output_format("json")
    set_output_format(None)
    assert get_output_format() == "dense"


def test_set_output_format_ids_implies_quiet():
    set_output_format("ids")
    assert is_quiet()


def test_resolve_output_format_defaults_to_dense():
    assert resolve_output_format() == "dense"


def test_resolve_output_format_returns_active_format():
    set_output_format("json")
    assert resolve_output_format() == "json"
