"""Unit tests for dku_cli.safety — guard, tier resolution, block message shape."""

from __future__ import annotations

import sys
from unittest.mock import patch

import pytest
import typer

from dku_cli.safety import (
    SAFETY_BLOCKED_EXIT,
    Tier,
    _reconstruct_rerun,
    guard,
    is_dangerous_mode,
)


class _FakeCtx:
    def __init__(self, obj: dict | None = None):
        self.obj = obj or {}


def test_is_dangerous_mode_default_is_guarded(monkeypatch):
    monkeypatch.delenv("DKU_DANGEROUS", raising=False)
    with patch("dku_cli.config.get_dangerous_mode", return_value=False):
        enabled, reason = is_dangerous_mode(None)
    assert enabled is False
    assert reason == "default"


def test_is_dangerous_mode_flag_wins(monkeypatch):
    monkeypatch.delenv("DKU_DANGEROUS", raising=False)
    ctx = _FakeCtx({"dangerous": True})
    with patch("dku_cli.config.get_dangerous_mode", return_value=False):
        enabled, reason = is_dangerous_mode(ctx)
    assert enabled is True
    assert reason == "flag"


def test_is_dangerous_mode_env_wins_over_config(monkeypatch):
    monkeypatch.setenv("DKU_DANGEROUS", "1")
    with patch("dku_cli.config.get_dangerous_mode", return_value=False):
        enabled, reason = is_dangerous_mode(None)
    assert enabled is True
    assert reason == "env"


def test_is_dangerous_mode_config_fallback(monkeypatch):
    monkeypatch.delenv("DKU_DANGEROUS", raising=False)
    with patch("dku_cli.config.get_dangerous_mode", return_value=True):
        enabled, reason = is_dangerous_mode(None)
    assert enabled is True
    assert reason == "config"


def test_is_dangerous_mode_hosted_ignores_env(monkeypatch):
    monkeypatch.setenv("DKU_DANGEROUS", "1")
    monkeypatch.setenv("DKU_MCP_HOSTED", "1")
    enabled, reason = is_dangerous_mode(None)
    assert enabled is False
    assert reason == "default"


def test_is_dangerous_mode_hosted_ignores_config(monkeypatch):
    monkeypatch.delenv("DKU_DANGEROUS", raising=False)
    monkeypatch.setenv("DKU_MCP_HOSTED", "1")
    with patch("dku_cli.config.get_dangerous_mode", return_value=True):
        enabled, reason = is_dangerous_mode(None)
    assert enabled is False


def test_is_dangerous_mode_hosted_still_honors_explicit_flag(monkeypatch):
    monkeypatch.setenv("DKU_MCP_HOSTED", "1")
    ctx = _FakeCtx({"dangerous": True})
    enabled, reason = is_dangerous_mode(ctx)
    assert enabled is True
    assert reason == "flag"


@pytest.mark.parametrize("tier", [Tier.READ, Tier.WRITE])
def test_guard_noop_for_read_and_write(tier, monkeypatch):
    monkeypatch.delenv("DKU_DANGEROUS", raising=False)
    guard(None, tier=tier, action="x.y", subject="thing", yes=False)


def test_guard_delete_blocks_without_yes(monkeypatch, capsys):
    monkeypatch.delenv("DKU_DANGEROUS", raising=False)
    with patch("dku_cli.config.get_dangerous_mode", return_value=False):
        with pytest.raises(typer.Exit) as excinfo:
            guard(
                _FakeCtx(),
                tier=Tier.DELETE,
                action="dataset.delete",
                subject="dataset 'ds1' in PROJ1",
                yes=False,
            )
    assert excinfo.value.exit_code == SAFETY_BLOCKED_EXIT
    captured = capsys.readouterr()
    assert "BLOCKED" in captured.err
    assert "AGENT INSTRUCTION" in captured.err
    assert "dataset.delete" in captured.err or "dataset 'ds1'" in captured.err


def test_guard_delete_allows_with_yes(monkeypatch):
    monkeypatch.delenv("DKU_DANGEROUS", raising=False)
    with patch("dku_cli.config.get_dangerous_mode", return_value=False):
        guard(
            _FakeCtx(),
            tier=Tier.DELETE,
            action="dataset.delete",
            subject="dataset 'ds1' in PROJ1",
            yes=True,
        )  # no raise


def test_guard_delete_dangerous_env_bypasses(monkeypatch):
    monkeypatch.setenv("DKU_DANGEROUS", "1")
    guard(
        _FakeCtx(),
        tier=Tier.DELETE,
        action="dataset.delete",
        subject="dataset 'ds1' in PROJ1",
        yes=False,
    )  # no raise


def test_guard_delete_dangerous_flag_bypasses(monkeypatch):
    monkeypatch.delenv("DKU_DANGEROUS", raising=False)
    with patch("dku_cli.config.get_dangerous_mode", return_value=False):
        guard(
            _FakeCtx({"dangerous": True}),
            tier=Tier.DELETE,
            action="dataset.delete",
            subject="dataset 'ds1' in PROJ1",
            yes=False,
        )  # no raise


# ----- CASCADE: requires --yes + matching --confirm-name -----


def test_guard_cascade_blocks_without_yes(monkeypatch):
    monkeypatch.delenv("DKU_DANGEROUS", raising=False)
    with patch("dku_cli.config.get_dangerous_mode", return_value=False):
        with pytest.raises(typer.Exit) as excinfo:
            guard(
                _FakeCtx(),
                tier=Tier.CASCADE,
                action="project.delete",
                subject="project PROJ1",
                yes=False,
                target_id="PROJ1",
            )
    assert excinfo.value.exit_code == SAFETY_BLOCKED_EXIT


def test_guard_cascade_blocks_when_confirm_name_missing(monkeypatch, capsys):
    monkeypatch.delenv("DKU_DANGEROUS", raising=False)
    with patch("dku_cli.config.get_dangerous_mode", return_value=False):
        with pytest.raises(typer.Exit) as excinfo:
            guard(
                _FakeCtx(),
                tier=Tier.CASCADE,
                action="project.delete",
                subject="project PROJ1",
                yes=True,
                target_id="PROJ1",
                confirm_name=None,
            )
    assert excinfo.value.exit_code == SAFETY_BLOCKED_EXIT


def test_guard_cascade_blocks_on_name_mismatch(monkeypatch, capsys):
    monkeypatch.delenv("DKU_DANGEROUS", raising=False)
    with patch("dku_cli.config.get_dangerous_mode", return_value=False):
        with pytest.raises(typer.Exit):
            guard(
                _FakeCtx(),
                tier=Tier.CASCADE,
                action="project.delete",
                subject="project PROJ1",
                yes=True,
                target_id="PROJ1",
                confirm_name="WRONG_NAME",
            )
    err = capsys.readouterr().err
    assert "confirm-name" in err.lower()
    assert "WRONG_NAME" in err


def test_guard_cascade_allows_when_yes_and_name_match(monkeypatch):
    monkeypatch.delenv("DKU_DANGEROUS", raising=False)
    with patch("dku_cli.config.get_dangerous_mode", return_value=False):
        guard(
            _FakeCtx(),
            tier=Tier.CASCADE,
            action="project.delete",
            subject="project PROJ1",
            yes=True,
            target_id="PROJ1",
            confirm_name="PROJ1",
        )


def test_guard_cascade_dangerous_still_needs_confirm_name(monkeypatch, capsys):
    monkeypatch.setenv("DKU_DANGEROUS", "1")
    with pytest.raises(typer.Exit):
        guard(
            _FakeCtx(),
            tier=Tier.CASCADE,
            action="project.delete",
            subject="project PROJ1",
            yes=True,
            target_id="PROJ1",
            confirm_name="WRONG",
        )


def test_guard_cascade_dangerous_with_correct_confirm_name(monkeypatch):
    monkeypatch.setenv("DKU_DANGEROUS", "1")
    guard(
        _FakeCtx(),
        tier=Tier.CASCADE,
        action="project.delete",
        subject="project PROJ1",
        yes=True,
        target_id="PROJ1",
        confirm_name="PROJ1",
    )


# ----- ADMIN: never bypassable even in dangerous mode -----


def test_guard_admin_blocks_dangerous_mode(monkeypatch):
    monkeypatch.setenv("DKU_DANGEROUS", "1")
    with pytest.raises(typer.Exit) as excinfo:
        guard(
            _FakeCtx(),
            tier=Tier.ADMIN,
            action="user.delete",
            subject="user alice",
            yes=True,
            target_id="alice",
            confirm_name="alice",
            i_know=False,
        )
    assert excinfo.value.exit_code == SAFETY_BLOCKED_EXIT


def test_guard_admin_requires_i_know_flag(monkeypatch):
    monkeypatch.delenv("DKU_DANGEROUS", raising=False)
    with pytest.raises(typer.Exit):
        guard(
            _FakeCtx(),
            tier=Tier.ADMIN,
            action="user.delete",
            subject="user alice",
            yes=True,
            target_id="alice",
            confirm_name="alice",
            i_know=False,
        )


def test_guard_admin_allows_with_full_authorization(monkeypatch):
    monkeypatch.delenv("DKU_DANGEROUS", raising=False)
    guard(
        _FakeCtx(),
        tier=Tier.ADMIN,
        action="user.delete",
        subject="user alice",
        yes=True,
        target_id="alice",
        confirm_name="alice",
        i_know=True,
    )


# ----- block message shape -----


def test_guard_block_message_shape(monkeypatch, capsys):
    monkeypatch.delenv("DKU_DANGEROUS", raising=False)
    with patch("dku_cli.config.get_dangerous_mode", return_value=False):
        with pytest.raises(typer.Exit):
            guard(
                _FakeCtx(),
                tier=Tier.DELETE,
                action="dataset.delete",
                subject="dataset 'ds1' in PROJ1",
                yes=False,
                prompt="Proceed with deletion?",
            )

    err = capsys.readouterr().err
    assert "BLOCKED" in err
    assert "tier-2" in err
    assert "AGENT INSTRUCTION" in err
    assert "Proceed with deletion?" in err
    assert "--yes" in err
    assert "DKU_DANGEROUS=1" in err
    assert str(SAFETY_BLOCKED_EXIT) in err


def test_guard_cascade_mismatch_message(monkeypatch, capsys):
    monkeypatch.delenv("DKU_DANGEROUS", raising=False)
    with patch("dku_cli.config.get_dangerous_mode", return_value=False):
        with pytest.raises(typer.Exit):
            guard(
                _FakeCtx(),
                tier=Tier.CASCADE,
                action="project.delete",
                subject="project PROJ1",
                yes=True,
                target_id="PROJ1",
                confirm_name="WRONG",
            )

    err = capsys.readouterr().err
    assert "PROJ1" in err
    assert "WRONG" in err


# ----- ADMIN refusal message content -----


def test_guard_admin_refusal_lists_missing_flags(monkeypatch, capsys):
    """Tier-4 refusal names every missing flag and states it is dangerous-immune."""
    monkeypatch.setenv("DKU_DANGEROUS", "1")
    with pytest.raises(typer.Exit):
        guard(
            _FakeCtx(),
            tier=Tier.ADMIN,
            action="admin.license.upload",
            subject="the active DSS license",
            yes=False,
            target_id="license",
            confirm_name=None,
            i_know=False,
        )
    err = capsys.readouterr().err
    assert "tier-4" in err
    assert "Even --dangerous" in err
    assert "--yes" in err
    assert "--confirm-name license" in err
    assert "--i-know-what-im-doing" in err


# ----- guard() fails loud when CASCADE/ADMIN omit target_id -----


def test_guard_cascade_requires_target_id(monkeypatch):
    monkeypatch.delenv("DKU_DANGEROUS", raising=False)
    with pytest.raises(ValueError, match="target_id"):
        guard(
            _FakeCtx(),
            tier=Tier.CASCADE,
            action="project.delete",
            subject="project PROJ1",
            yes=True,
            target_id=None,
            confirm_name="PROJ1",
        )


def test_guard_admin_requires_target_id(monkeypatch):
    monkeypatch.delenv("DKU_DANGEROUS", raising=False)
    with pytest.raises(ValueError, match="target_id"):
        guard(
            _FakeCtx(),
            tier=Tier.ADMIN,
            action="admin.settings.set",
            subject="DSS general settings",
            yes=True,
            target_id="",
            confirm_name="general-settings",
            i_know=True,
        )


# ----- is_dangerous_mode fails closed on config error -----


def test_is_dangerous_mode_fails_closed_on_config_error(monkeypatch):
    monkeypatch.delenv("DKU_DANGEROUS", raising=False)
    with patch("dku_cli.config.get_dangerous_mode", side_effect=RuntimeError("boom")):
        enabled, reason = is_dangerous_mode(None)
    assert enabled is False
    assert reason == "default"


# ----- _reconstruct_rerun: clean, idempotent rerun command -----


def test_reconstruct_rerun_strips_attached_confirm_name(monkeypatch):
    """--confirm-name=VALUE (attached form) is stripped, never duplicated."""
    monkeypatch.setattr(
        sys,
        "argv",
        ["dku", "project", "delete", "PROJ1", "--yes", "--confirm-name=WRONG", "-y"],
    )
    rerun = _reconstruct_rerun(["--yes", "--confirm-name", "PROJ1"])
    assert rerun == "dku project delete PROJ1 --yes --confirm-name PROJ1"
    assert rerun.count("--confirm-name") == 1
    assert "WRONG" not in rerun


def test_reconstruct_rerun_strips_spaced_confirm_name(monkeypatch):
    """--confirm-name VALUE (spaced form) and its stale value are both stripped."""
    monkeypatch.setattr(
        sys,
        "argv",
        ["dku", "project", "delete", "PROJ1", "--confirm-name", "OLD", "--yes"],
    )
    rerun = _reconstruct_rerun(["--yes", "--confirm-name", "PROJ1"])
    assert rerun == "dku project delete PROJ1 --yes --confirm-name PROJ1"
    assert "OLD" not in rerun


def test_reconstruct_rerun_normalizes_non_dku_head(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["pytest", "dataset", "delete", "ds1"])
    assert _reconstruct_rerun(["--yes"]) == "dku dataset delete ds1 --yes"


def test_reconstruct_rerun_empty_argv(monkeypatch):
    monkeypatch.setattr(sys, "argv", [])
    assert _reconstruct_rerun(["--yes"]) == "dku --yes"
