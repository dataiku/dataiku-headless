"""Safety guards for destructive CLI operations.

Every destructive command calls `guard()`, which enforces the active safety
mode (guarded by default, dangerous opt-in). When a guard blocks a command,
it emits a machine-parseable AGENT INSTRUCTION block so an LLM agent driving
the CLI can stop, ask the user, and re-run with the exact confirmation flags.

Exit code 77 is reserved for safety_blocked.

See docs/design/safety-stance.md for the design rationale and call-site conventions.
"""

from __future__ import annotations

import os
import sys
from enum import IntEnum
from typing import Optional

import typer


SAFETY_BLOCKED_EXIT = 77


class Tier(IntEnum):
    """Risk tier for a command.

    READ / WRITE — never guarded.
    DELETE       — requires --yes (or dangerous mode).
    CASCADE      — requires --yes AND --confirm-name matching target (or dangerous).
    ADMIN        — requires --yes AND --confirm-name AND --i-know-what-im-doing.
                   NOT bypassable by dangerous mode.
    """

    READ = 0
    WRITE = 1
    DELETE = 2
    CASCADE = 3
    ADMIN = 4


_dangerous_banner_emitted = False


def _tier_label(tier: Tier) -> str:
    return {
        Tier.READ: "read",
        Tier.WRITE: "write",
        Tier.DELETE: "delete",
        Tier.CASCADE: "cascade",
        Tier.ADMIN: "admin",
    }[tier]


def is_dangerous_mode(ctx: Optional[typer.Context] = None) -> tuple[bool, str]:
    """Return (enabled, reason).

    Precedence: --dangerous flag > DKU_DANGEROUS env > config.toml.

    In a hosted MCP shell (``DKU_MCP_HOSTED`` set by the executor) ``DKU_DANGEROUS``
    inherited from the process env or config.toml is ignored, so a leaked or
    operator-set danger signal can't silently disable the DELETE/CASCADE guards.
    This is a speed-bump, not a boundary: an agent that fully controls its shell
    can still override the marker (``DKU_MCP_HOSTED=0 DKU_DANGEROUS=1 dku ...``).
    That's acceptable because the real authorization boundary in hosted mode is
    the DSS API key's RBAC, never this guard — see ``docs/design/safety-stance.md``.
    """
    if ctx is not None and (ctx.obj or {}).get("dangerous"):
        return True, "flag"
    hosted = os.environ.get("DKU_MCP_HOSTED", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
    if hosted:
        return False, "default"
    env = os.environ.get("DKU_DANGEROUS", "").strip().lower()
    if env in ("1", "true", "yes", "on"):
        return True, "env"
    try:
        from dku_cli.config import get_dangerous_mode

        if get_dangerous_mode():
            return True, "config"
    except Exception:
        pass
    return False, "default"


def _reconstruct_rerun(extra_flags: list[str]) -> str:
    """Rebuild the current invocation with extra confirmation flags appended.

    Uses sys.argv; strips any existing duplicate confirmation flag before
    adding the canonical ones so the agent-facing rerun command is clean.
    """
    head = os.path.basename(sys.argv[0]) if sys.argv else "dku"
    if "dku" not in head.lower():
        head = "dku"

    cleaned: list[str] = []
    skip_next = False
    for arg in sys.argv[1:]:
        if skip_next:
            skip_next = False
            continue
        flag = arg.split("=", 1)[0]
        if flag in ("--yes", "-y", "--confirm", "--i-know-what-im-doing"):
            continue
        if flag == "--confirm-name":
            skip_next = "=" not in arg
            continue
        cleaned.append(arg)

    return " ".join([head] + cleaned + extra_flags)


def _emit_block(
    tier: Tier,
    prompt_to_user: str,
    rerun_with_confirmation: str,
    session_bypass: str,
) -> None:
    """Emit the AGENT INSTRUCTION block to stderr."""
    from dku_cli.output import err_console

    err_console.print(
        f"[red]◆[/red] BLOCKED by guarded mode — tier-{int(tier)} "
        f"({_tier_label(tier)}) blast radius."
    )
    err_console.print("")
    err_console.print("[bold]AGENT INSTRUCTION:[/bold]")
    err_console.print("  1. Stop. Do not retry automatically.")
    err_console.print("  2. Ask the user verbatim:", highlight=False)
    err_console.print(f"       {prompt_to_user!r}", highlight=False, markup=False)
    err_console.print("  3. If they say yes, run this exact command:")
    err_console.print(
        f"       {rerun_with_confirmation}", highlight=False, markup=False
    )
    err_console.print("  4. To authorise everything for this session, ask the user:")
    err_console.print(f"       export {session_bypass}", highlight=False, markup=False)
    err_console.print("")
    err_console.print(f"[dim]Exit code: {SAFETY_BLOCKED_EXIT}  (safety_blocked)[/dim]")


def _warn_dangerous_once(ctx: Optional[typer.Context], reason: str) -> None:
    global _dangerous_banner_emitted
    if _dangerous_banner_emitted:
        return
    _dangerous_banner_emitted = True
    from dku_cli.output import warn

    warn(f"DANGEROUS MODE active ({reason}) — safety guards disabled.")


def _require_named_target(tier: Tier, action: str, target_id: Optional[str]) -> None:
    if tier >= Tier.CASCADE and not target_id:
        raise ValueError(
            f"guard(action={action!r}) tier {_tier_label(tier)} needs a non-empty "
            "target_id: CASCADE/ADMIN must name their target."
        )


def guard(
    ctx: Optional[typer.Context],
    *,
    tier: Tier,
    action: str,
    subject: str,
    yes: bool = False,
    target_id: Optional[str] = None,
    confirm_name: Optional[str] = None,
    i_know: bool = False,
    prompt: Optional[str] = None,
) -> None:
    """Enforce safety policy for a destructive operation.

    Args:
        ctx: Typer context (for --dangerous flag detection).
        tier: Tier.DELETE / CASCADE / ADMIN. READ/WRITE are no-ops.
        action: Dotted identifier like "dataset.delete" — used in JSON error payload.
        subject: Human-readable target ("dataset 'ds1' in project PROJ1").
        yes: Whether --yes/-y was passed on the command.
        target_id: For CASCADE/ADMIN, the identifier --confirm-name must match.
        confirm_name: Value of --confirm-name flag.
        i_know: Whether --i-know-what-im-doing was passed (ADMIN only).
        prompt: Override the user-facing approval question on the generic
                DELETE / first-time CASCADE block (defaults to a generic
                "Proceed with <action> on <subject>?"). The name-mismatch and
                ADMIN refusals use their own fixed wording.

    Raises:
        typer.Exit(77) if the operation is refused.
    """
    if tier < Tier.DELETE:
        return

    _require_named_target(tier, action, target_id)

    dangerous, reason = is_dangerous_mode(ctx)

    if tier == Tier.ADMIN:
        if not (yes and confirm_name and confirm_name == target_id and i_know):
            _emit_admin_refusal(action, subject, target_id, yes, confirm_name, i_know)
            raise typer.Exit(SAFETY_BLOCKED_EXIT)
        return

    if dangerous and tier <= Tier.CASCADE:
        if tier == Tier.CASCADE and target_id and confirm_name != target_id:
            _emit_cascade_name_mismatch(target_id, confirm_name)
            raise typer.Exit(SAFETY_BLOCKED_EXIT)
        _warn_dangerous_once(ctx, reason)
        return

    if tier == Tier.CASCADE:
        if not yes:
            _emit_generic_block(
                action, subject, tier, prompt, extra_flags=_cascade_flags(target_id)
            )
            raise typer.Exit(SAFETY_BLOCKED_EXIT)
        if not confirm_name or confirm_name != target_id:
            _emit_cascade_name_mismatch(target_id, confirm_name)
            raise typer.Exit(SAFETY_BLOCKED_EXIT)
        return

    if not yes:
        _emit_generic_block(action, subject, tier, prompt, extra_flags=["--yes"])
        raise typer.Exit(SAFETY_BLOCKED_EXIT)


def _cascade_flags(target_id: str) -> list[str]:
    return ["--yes", "--confirm-name", target_id]


def _emit_generic_block(
    action: str,
    subject: str,
    tier: Tier,
    prompt_override: Optional[str],
    extra_flags: list[str],
) -> None:
    prompt_to_user = (
        prompt_override or f"Proceed with {action} on {subject}? This is irreversible."
    )
    rerun = _reconstruct_rerun(extra_flags)
    _emit_block(
        tier=tier,
        prompt_to_user=prompt_to_user,
        rerun_with_confirmation=rerun,
        session_bypass="DKU_DANGEROUS=1",
    )


def _emit_cascade_name_mismatch(
    target_id: str,
    confirm_name: Optional[str],
) -> None:
    rerun = _reconstruct_rerun(["--yes", "--confirm-name", target_id])

    from dku_cli.output import err_console

    err_console.print(
        "[red]◆[/red] BLOCKED — tier-3 cascade requires --confirm-name to match the target."
    )
    err_console.print("")
    err_console.print("[bold]AGENT INSTRUCTION:[/bold]")
    err_console.print(f"  Expected: --confirm-name {target_id!r}")
    err_console.print(f"  Got:      --confirm-name {confirm_name!r}")
    err_console.print(
        "  Verify the target identifier with the user and re-run with the matching --confirm-name."
    )
    err_console.print(f"  Re-run: {rerun}", markup=False, highlight=False)


def _emit_admin_refusal(
    action: str,
    subject: str,
    target_id: Optional[str],
    yes: bool,
    confirm_name: Optional[str],
    i_know: bool,
) -> None:
    missing = []
    if not yes:
        missing.append("--yes")
    if not confirm_name or confirm_name != target_id:
        missing.append(f"--confirm-name {target_id or '<TARGET>'}")
    if not i_know:
        missing.append("--i-know-what-im-doing")

    rerun = _reconstruct_rerun(
        ["--yes", "--confirm-name", target_id or "<TARGET>", "--i-know-what-im-doing"]
    )

    from dku_cli.output import err_console

    err_console.print(
        "[red]◆[/red] BLOCKED — tier-4 admin op requires explicit full authorization."
    )
    err_console.print("  Even --dangerous / DKU_DANGEROUS=1 do not bypass tier-4.")
    err_console.print("")
    err_console.print("[bold]AGENT INSTRUCTION:[/bold]")
    err_console.print(f"  1. Stop. Ask the user to confirm: {action} on {subject}.")
    err_console.print(f"  2. Missing authorization flags: {' '.join(missing)}")
    err_console.print(
        f"  3. If fully authorised, re-run: {rerun}", markup=False, highlight=False
    )
