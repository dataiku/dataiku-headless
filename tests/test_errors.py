"""Tests for central CLI error handling."""

from __future__ import annotations

import inspect

import click
import pytest
import typer

from dku_cli.errors import handle_api_error, handle_errors


def test_handle_api_error_reraises_typer_exit():
    with pytest.raises(typer.Exit) as excinfo:
        handle_api_error(typer.Exit(77))

    assert excinfo.value.exit_code == 77


def test_handle_api_error_reraises_system_exit():
    with pytest.raises(SystemExit) as excinfo:
        handle_api_error(SystemExit(3))

    assert excinfo.value.code == 3


def test_handle_api_error_reraises_usage_error():
    # Usage errors must reach Click (exit 2 + usage message), not be mapped to a
    # generic "DSS API error" at exit 1.
    err = click.exceptions.UsageError("Output format must be one of ...")
    with pytest.raises(click.exceptions.UsageError):
        handle_api_error(err)


def test_handle_api_error_reraises_bad_parameter():
    # typer.BadParameter (a click.UsageError subclass) is what
    # resolve_project()/resolve_output_format() raise on bad input.
    with pytest.raises(typer.BadParameter):
        handle_api_error(typer.BadParameter("bad -o value"))


def test_handle_errors_propagates_usage_error_instead_of_mapping_it():
    # Regression guard: the decorator wraps the whole command body, so a
    # BadParameter raised inside (e.g. from resolve_output_format) must bubble
    # up to Click rather than being reclassified as a DSS API error.
    @handle_errors
    def command() -> None:
        raise typer.BadParameter("Output format must be one of: table, json, csv")

    with pytest.raises(click.exceptions.UsageError):
        command()


def test_handle_errors_preserves_wrapped_signature():
    def command(ctx: typer.Context, output: str | None = None) -> None:
        return None

    wrapped = handle_errors(command)

    assert inspect.signature(wrapped) == inspect.signature(command)
    assert wrapped.__name__ == "command"


def test_handle_errors_routes_exceptions_to_api_mapper(monkeypatch):
    calls: list[Exception] = []

    def fake_handle_api_error(exc: Exception, *, project_key=None) -> None:
        calls.append(exc)

    monkeypatch.setattr("dku_cli.errors.handle_api_error", fake_handle_api_error)

    @handle_errors
    def command() -> None:
        raise RuntimeError("boom")

    command()

    assert len(calls) == 1
    assert str(calls[0]) == "boom"


def test_handle_errors_threads_project_kwarg_into_api_mapper(monkeypatch):
    """A decorated command invoked with a `project` kwarg must pass it through
    so a project-scoped 401 gets key-vs-name guidance, not a re-auth loop."""
    seen: list[str | None] = []

    def fake_handle_api_error(exc: Exception, *, project_key=None) -> None:
        seen.append(project_key)

    monkeypatch.setattr("dku_cli.errors.handle_api_error", fake_handle_api_error)

    @handle_errors
    def command(project: str | None = None) -> None:
        raise RuntimeError("Failed to read project permissions")

    command(project="AdvisorGPT")
    assert seen == ["AdvisorGPT"]


def test_handle_errors_no_project_kwarg_passes_none(monkeypatch):
    seen: list[str | None] = []

    def fake_handle_api_error(exc: Exception, *, project_key=None) -> None:
        seen.append(project_key)

    monkeypatch.setattr("dku_cli.errors.handle_api_error", fake_handle_api_error)

    @handle_errors
    def command() -> None:
        raise RuntimeError("boom")

    command()
    assert seen == [None]


def test_handle_errors_project_401_gives_key_vs_name_guidance():
    """End-to-end: a 401 from a project-scoped decorated command surfaces the
    prescriptive key-vs-name guidance (exit 3), not 'check your API key'."""

    @handle_errors
    def command(project: str | None = None) -> None:
        raise RuntimeError("401 Unauthorized")

    with pytest.raises(SystemExit) as excinfo:
        command(project="AdvisorGPT")
    # status 3 (not_found / use the right key), not 2 (re-authenticate)
    assert excinfo.value.code == 3
