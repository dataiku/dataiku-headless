"""Result rendering and failure diagnosis helpers for `dku git`.

Shared exit/rendering contract for pull/push/fetch/switch, plus the
prescriptive explanation for DSS's opaque reset-to-upstream failure.
"""

from __future__ import annotations

import typer

from dku_cli.errors import exit_with_error, handle_api_error
from dku_cli.output import error, render_raw, success


def _finish_git_action(data, output: str, ok_msg: str, fail_msg: str) -> None:
    ok = data.get("success", True) if isinstance(data, dict) else True
    if output == "json":
        render_raw(data, output_format="json")
    elif ok:
        success(ok_msg)
    else:
        error(fail_msg)
    if not ok:
        raise typer.Exit(1)


def _explain_reset_to_upstream_failure(e: Exception, git, project_key: str) -> None:
    """Turn DSS's cryptic upstream-reset failure into prescriptive guidance.

    ``reset_to_upstream()`` hard-resets the current branch onto its remote-tracking
    branch. If that branch was created locally and never pushed it has no upstream,
    and DSS fails with an opaque server-side NullPointerException
    (``... because "name" is null``) that tells an agent nothing. Detect that case —
    the current branch has no same-named branch on any remote — and explain exactly
    how to recover. Anything else (auth, connection, a branch that *does* track a
    remote) falls through to the normal ``handle_api_error`` path.
    """
    try:
        status = git.get_status()
        current = status.get("currentBranch") or "<current branch>"
        remote_prefixes = [
            f"{r.get('name')}/" for r in (status.get("remotes") or []) if r.get("name")
        ]
        remote_branches = git.list_branches(remote=True) or []
    except Exception:  # quality-ratchet: allow-broad-exception
        # Can't introspect (e.g. the original failure was a connection error) —
        # surface the original exception through the normal path.
        handle_api_error(e)
        return

    def _local_name(branch: str) -> str:
        for prefix in remote_prefixes:
            if branch.startswith(prefix):
                return branch[len(prefix) :]
        return branch

    if not any(_local_name(b) == current for b in remote_branches):
        exit_with_error(
            f"Cannot reset to upstream: branch '{current}' has no branch on "
            "the remote to reset onto.",
            details=[
                f"'{current}' looks like a local-only branch (never pushed), so there",
                "is no upstream commit to hard-reset onto. DSS reports this as an",
                'opaque server error (NullPointerException: "name" is null).',
                "",
                "Pick one:",
                "  Push it first to create the upstream:  "
                f"dku git push -P {project_key}",
                "  Reset a branch that tracks a remote:   "
                f"dku git switch main -P {project_key} && "
                f"dku git fetch -P {project_key} && "
                f"dku git reset-to-upstream -P {project_key} --yes",
                "  Drop only local uncommitted changes:   "
                f"dku git reset-to-head -P {project_key} --yes",
            ],
        )
    # The branch does track a remote — this is some other failure.
    handle_api_error(e)
