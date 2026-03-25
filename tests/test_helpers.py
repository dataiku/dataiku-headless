"""Tests for helpers module."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import typer

from dku_cli.helpers import resolve_project, get_client_from_ctx


def test_resolve_project_flag():
    assert resolve_project("MYPROJ") == "MYPROJ"


def test_resolve_project_env(monkeypatch):
    monkeypatch.setenv("DKU_PROJECT", "ENVPROJ")
    assert resolve_project(None) == "ENVPROJ"


def test_resolve_project_config(monkeypatch):
    monkeypatch.delenv("DKU_PROJECT", raising=False)
    with patch("dku_cli.helpers.get_default_project", return_value="CFGPROJ"):
        assert resolve_project(None) == "CFGPROJ"


def test_resolve_project_missing(monkeypatch):
    monkeypatch.delenv("DKU_PROJECT", raising=False)
    with patch("dku_cli.helpers.get_default_project", return_value=None):
        with pytest.raises(typer.BadParameter):
            resolve_project(None)


def test_resolve_project_flag_takes_precedence(monkeypatch):
    monkeypatch.setenv("DKU_PROJECT", "ENVPROJ")
    assert resolve_project("FLAGPROJ") == "FLAGPROJ"


def test_get_client_from_ctx():
    ctx = MagicMock()
    ctx.obj = {"url": "https://dss.example.com", "api_key": "abc123"}
    with patch("dku_cli.helpers.get_client") as mock_get:
        mock_get.return_value = MagicMock()
        get_client_from_ctx(ctx)
        mock_get.assert_called_once_with(
            url="https://dss.example.com", api_key="abc123"
        )


def test_get_client_from_ctx_empty_obj():
    ctx = MagicMock()
    ctx.obj = None
    with patch("dku_cli.helpers.get_client") as mock_get:
        mock_get.return_value = MagicMock()
        get_client_from_ctx(ctx)
        mock_get.assert_called_once_with()
