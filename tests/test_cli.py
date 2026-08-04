"""Tests for the command-line interface."""

import importlib.metadata

import pytest

from dataiku_mcp import cli


def test_no_arguments_runs_the_server(monkeypatch):
    calls = []
    monkeypatch.setattr(cli, "run_server", lambda: calls.append(True))

    cli.main([])

    assert calls == [True]


def test_help_prints_usage_without_running_the_server(monkeypatch, capsys):
    monkeypatch.setattr(cli, "run_server", lambda: pytest.fail("server started"))

    with pytest.raises(SystemExit) as exc_info:
        cli.main(["--help"])

    assert exc_info.value.code == 0
    assert "usage: dataiku-headless" in capsys.readouterr().out


def test_version_prints_package_version_without_running_the_server(
    monkeypatch, capsys
):
    monkeypatch.setattr(cli, "run_server", lambda: pytest.fail("server started"))

    with pytest.raises(SystemExit) as exc_info:
        cli.main(["--version"])

    assert exc_info.value.code == 0
    assert capsys.readouterr().out == (
        f"dataiku-headless {importlib.metadata.version('dataiku-headless')}\n"
    )


def test_unknown_argument_fails_without_running_the_server(monkeypatch, capsys):
    monkeypatch.setattr(cli, "run_server", lambda: pytest.fail("server started"))

    with pytest.raises(SystemExit) as exc_info:
        cli.main(["--unknown"])

    assert exc_info.value.code == 2
    assert "unrecognized arguments: --unknown" in capsys.readouterr().err
