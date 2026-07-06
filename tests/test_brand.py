"""Tests for brand module."""

from __future__ import annotations

from dku_cli import __version__
from dku_cli.brand import ICON, status_err, status_ok, version_string, welcome


def test_icon_is_diamond():
    assert ICON == "◆"


def test_version_string():
    result = version_string()
    assert result.startswith("◆ Dataiku Headless ")
    assert __version__ in result


def test_welcome():
    result = welcome("chris", "https://dss.example.com", "14.0.2")
    assert "◆" in result
    assert "chris" in result
    assert "14.0.2" in result


def test_status_ok():
    result = status_ok("All good")
    assert result == "◆ All good"


def test_status_err():
    result = status_err("Something failed")
    assert result == "◆ Something failed"
