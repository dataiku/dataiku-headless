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
    with pytest.raises(typer.BadParameter):
        handle_api_error(typer.BadParameter("bad -o value"))


def test_handle_errors_propagates_usage_error_instead_of_mapping_it():
    @handle_errors
    def command() -> None:
        raise typer.BadParameter("Output format must be one of: table, json, csv")

    with pytest.raises(typer.BadParameter):
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


def test_handle_api_error_empty_message_does_not_suggest_removed_errors_flag(capsys):
    with pytest.raises(SystemExit) as excinfo:
        handle_api_error(Exception())

    assert excinfo.value.code == 1
    captured = capsys.readouterr()
    assert "--errors" not in captured.err
    assert "dku --format json recipe get-settings" in captured.err


def test_handle_api_error_partial_output_zlib(capsys):
    """ZLIB EOF on a dataset read = truncated file from a FAILED build,
    not data corruption."""
    with pytest.raises(SystemExit) as excinfo:
        handle_api_error(
            Exception(
                "CodedIOException: Failed to read file out-s0.csv.gz, caused by: "
                "java.io.EOFException: Unexpected end of ZLIB input stream"
            )
        )
    assert excinfo.value.code == 1
    err = capsys.readouterr().err
    assert "failed build" in err
    assert "dku dataset usage" in err


def test_handle_api_error_never_built_datastore(capsys):
    """Raw DataStoreIOException passthrough gains a build-first next step."""
    with pytest.raises(SystemExit) as excinfo:
        handle_api_error(
            Exception(
                "com.dataiku.dip.exceptions.DataStoreIOException: "
                "No such file or directory"
            )
        )
    assert excinfo.value.code == 1
    err = capsys.readouterr().err
    assert "no data yet" in err
    assert "RECURSIVE_BUILD" in err


def test_handle_api_error_not_dev_plugin(capsys):
    """Pushed plugins have no API readback — prescribe pre-push zip checks."""
    with pytest.raises(SystemExit):
        handle_api_error(
            Exception(
                "com.dataiku.dip.CodedRuntimeException: "
                "Plugin replicate is not a dev plugin"
            )
        )
    err = capsys.readouterr().err
    assert "write-only" in err
    assert "unzip -p" in err


def test_handle_api_error_root_path_missing(capsys):
    """'Root path of the dataset X does not exist' = no data yet."""
    with pytest.raises(SystemExit):
        handle_api_error(Exception("Root path of the dataset trigger does not exist"))
    err = capsys.readouterr().err
    assert "dku dataset upload" in err


def test_handle_api_error_llm_provider_missing_scope(capsys):
    """A provider 401 (missing_scope) arrives as an LLMException and must surface
    the provider's own error, NOT the generic 'check your API key / dku auth
    login' hint that points at the wrong thing (#226)."""
    from dataikuapi.dss.llm_utils import LLMException

    err_obj = LLMException(
        "Missing scopes: model.request",
        "missing_scope",
        "invalid_request_error",
        "openai",
    )
    with pytest.raises(SystemExit) as excinfo:
        handle_api_error(err_obj)
    assert excinfo.value.code == 2
    err = capsys.readouterr().err
    assert "Missing scopes: model.request" in err
    assert "missing_scope" in err
    assert "NOT your dku API key" in err
    # The misleading generic dku-auth hint must NOT win for a provider error:
    # point at the connection and say re-auth won't help.
    assert "check your API key" not in err
    assert "re-authenticate" not in err
    assert "will NOT help" in err


def test_handle_api_error_llm_provider_non_auth(capsys):
    """A non-auth LLM provider failure still surfaces the provider body, without
    the connection-credential guidance reserved for auth/scope errors."""
    from dataikuapi.dss.llm_utils import LLMException

    err_obj = LLMException(
        "Rate limit exceeded", "rate_limit", "server_error", "anthropic"
    )
    with pytest.raises(SystemExit) as excinfo:
        handle_api_error(err_obj)
    assert excinfo.value.code == 2
    err = capsys.readouterr().err
    assert "Rate limit exceeded" in err
    assert "NOT your dku API key" not in err
