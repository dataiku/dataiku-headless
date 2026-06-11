"""Unit tests for dku_cli.safety — guard, tier resolution, block message shape."""

from __future__ import annotations

from unittest.mock import patch

import pytest
import typer

from dku_cli.safety import SAFETY_BLOCKED_EXIT, Tier, guard, is_dangerous_mode


class _FakeCtx:
    """Stand-in for typer.Context for unit tests that don't need the runner."""

    def __init__(self, obj: dict | None = None):
        self.obj = obj or {}


# ----- is_dangerous_mode precedence -----


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


# ----- tier gating: READ / WRITE are no-ops -----


@pytest.mark.parametrize("tier", [Tier.READ, Tier.WRITE])
def test_guard_noop_for_read_and_write(tier, monkeypatch):
    monkeypatch.delenv("DKU_DANGEROUS", raising=False)
    # Should not raise even with yes=False
    guard(None, tier=tier, action="x.y", subject="thing", yes=False)


# ----- DELETE: requires --yes -----


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
