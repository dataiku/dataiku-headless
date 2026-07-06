"""dku git — status, log, diff, commit, pull, push, fetch, branches, create-branch, delete-branch, switch, tags, create-tag, remote, reset-to-upstream, reset-to-head."""

from __future__ import annotations

import typer

from dku_cli.commands._git_actions import (
    _explain_reset_to_upstream_failure,
    _finish_git_action,
)
from dku_cli.errors import handle_api_error
from dku_cli.helpers import get_client_from_ctx, resolve_project
from dku_cli.output import render, render_raw, resolve_output_format, success, warn

app = typer.Typer(help="Manage a DSS project's git repository.")


@app.command()
def status(
    ctx: typer.Context,
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Show the current state of the project's git repository."""
    project_key = resolve_project(project)
    output = resolve_output_format()
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        git = proj.get_project_git()
        data = git.get_status()

        if output == "json":
            render_raw(data, output_format="json")
        else:
            # Key-value summary
            summary = {
                "Branch": data.get("currentBranch", ""),
                "Clean": str(data.get("clean", "")),
                "Uncommitted changes": str(data.get("hasUncommittedChanges", "")),
            }
            # Collect changed file lists
            for key in (
                "added",
                "changed",
                "removed",
                "modified",
                "untracked",
                "conflicting",
            ):
                files = data.get(key, [])
                if files:
                    summary[key.capitalize()] = ", ".join(files)

            render_raw(summary)
    except Exception as e:
        handle_api_error(e)


@app.command()
def log(
    ctx: typer.Context,
    count: int = typer.Option(
        20, "--count", "-n", help="Max number of commits to return"
    ),
    path: str | None = typer.Option(
        None, "--path", help="Filter log to commits affecting this path"
    ),
    start_commit: str | None = typer.Option(
        None, "--start-commit", help="Start listing from this commit ID"
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """List commits in the project's git repository."""
    project_key = resolve_project(project)
    output = resolve_output_format()
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        git = proj.get_project_git()
        data = git.log(path=path, start_commit=start_commit, count=count)

        if output == "json":
            render_raw(data, output_format="json")
        else:
            entries = data.get("entries", [])
            rows = []
            for e in entries:
                rows.append(
                    {
                        "commit": e.get("commitId", "")[:8],
                        "author": e.get("author", ""),
                        "message": e.get("message", "").split("\n")[0],
                    }
                )
            render(
                rows,
                ["commit", "author", "message"],
                output_format=output,
                title=f"Git Log ({project_key})",
            )
    except Exception as e:
        handle_api_error(e)


@app.command()
def diff(
    ctx: typer.Context,
    commit_from: str | None = typer.Option(None, "--from", help="Start commit ID"),
    commit_to: str | None = typer.Option(None, "--to", help="End commit ID"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Show changes between commits or working copy and last commit.

    No flags: working copy vs last commit.
    --from only: changes in that commit.
    --from and --to: changes between two commits.
    """
    project_key = resolve_project(project)
    output = resolve_output_format()
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        git = proj.get_project_git()
        data = git.diff(commit_from=commit_from, commit_to=commit_to)

        if output == "json":
            render_raw(data, output_format="json")
        else:
            summary = {
                "Added lines": data.get("addedLines", 0),
                "Removed lines": data.get("removedLines", 0),
                "Changed files": data.get("changedFiles", 0),
            }
            render_raw(summary)
    except Exception as e:
        handle_api_error(e)


@app.command()
def commit(
    ctx: typer.Context,
    message: str = typer.Option(..., "--message", "-m", help="Commit message"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Commit pending changes in the project's git repository.

    DSS auto-adds untracked files before committing. There is no
    separate 'git add' step -- all changes are included automatically.
    """
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        git = proj.get_project_git()
        git.commit(message)
        success(f"Committed changes in {project_key}")
    except Exception as e:
        handle_api_error(e)


@app.command()
def pull(
    ctx: typer.Context,
    branch: str | None = typer.Option(
        None, "--branch", "-b", help="Branch to pull (default: current)"
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Pull changes from the remote repository (rebase)."""
    project_key = resolve_project(project)
    output = resolve_output_format()
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        git = proj.get_project_git()
        data = git.pull(branch_name=branch)
        out = data.get("output", "") if isinstance(data, dict) else str(data)
        _finish_git_action(
            data,
            output,
            f"Pull complete in {project_key}: {out}",
            f"Pull failed in {project_key}: {out}",
        )
    except Exception as e:
        handle_api_error(e)


@app.command()
def push(
    ctx: typer.Context,
    branch: str | None = typer.Option(
        None, "--branch", "-b", help="Branch to push (default: current)"
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Push local commits to the remote repository."""
    project_key = resolve_project(project)
    output = resolve_output_format()
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        git = proj.get_project_git()
        data = git.push(branch_name=branch)
        out = data.get("output", "") if isinstance(data, dict) else str(data)
        _finish_git_action(
            data,
            output,
            f"Push complete in {project_key}: {out}",
            f"Push failed in {project_key}: {out}",
        )
    except Exception as e:
        handle_api_error(e)


@app.command()
def fetch(
    ctx: typer.Context,
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Fetch refs from the remote repository."""
    project_key = resolve_project(project)
    output = resolve_output_format()
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        git = proj.get_project_git()
        data = git.fetch()
        _finish_git_action(
            data,
            output,
            f"Fetch complete in {project_key}",
            f"Fetch failed in {project_key}",
        )
    except Exception as e:
        handle_api_error(e)


@app.command()
def branches(
    ctx: typer.Context,
    remote: bool = typer.Option(
        False, "--remote", "-r", help="Include remote branches"
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """List branches in the project's git repository."""
    project_key = resolve_project(project)
    output = resolve_output_format()
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        git = proj.get_project_git()
        data = git.list_branches(remote=remote)

        if output == "json":
            render_raw(data, output_format="json")
        else:
            rows = [{"branch": b} for b in data]
            render(
                rows,
                ["branch"],
                output_format=output,
                title=f"Branches ({project_key})",
            )
    except Exception as e:
        handle_api_error(e)


@app.command("create-branch")
def create_branch(
    ctx: typer.Context,
    branch_name: str = typer.Argument(help="Name of the branch to create"),
    from_commit: str | None = typer.Option(
        None, "--from", help="Commit hash to branch from"
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Create a new local branch and switch to it."""
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        git = proj.get_project_git()
        git.create_branch(branch_name, commit=from_commit)
        success(f"Created branch '{branch_name}' in {project_key}")
    except Exception as e:
        handle_api_error(e)


@app.command("delete-branch")
def delete_branch(
    ctx: typer.Context,
    branch_name: str = typer.Argument(help="Name of the branch to delete"),
    force: bool = typer.Option(
        False, "--force", "-f", help="Force delete even with unpushed commits"
    ),
    remote: bool = typer.Option(False, "--remote", "-r", help="Delete a remote branch"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip safety guard"),
    confirm_name: str = typer.Option(
        None,
        "--confirm-name",
        help="With --force, must match BRANCH_NAME to proceed (tier-3 guard).",
    ),
) -> None:
    """Delete a local or remote branch.

    Without --force: tier-2 guard, requires --yes.
    With --force (may destroy unpushed commits): tier-3 guard,
    requires --yes + --confirm-name BRANCH_NAME.
    """
    from dku_cli.safety import Tier, guard

    project_key = resolve_project(project)
    tier = Tier.CASCADE if force else Tier.DELETE
    guard(
        ctx,
        tier=tier,
        action="git.delete_branch",
        subject=(
            f"branch '{branch_name}' in {project_key}"
            + (" (FORCE — may destroy unpushed commits)" if force else "")
        ),
        yes=yes,
        target_id=branch_name if force else None,
        confirm_name=confirm_name,
        prompt=(
            f"Delete {'remote' if remote else 'local'} branch '{branch_name}' in project {project_key}"
            + (" even if it has unpushed commits?" if force else "?")
        ),
    )
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        git = proj.get_project_git()
        git.delete_branch(branch_name, force_delete=force, remote=remote)
        success(f"Deleted branch '{branch_name}' in {project_key}")
    except Exception as e:
        handle_api_error(e)


@app.command()
def switch(
    ctx: typer.Context,
    branch_name: str = typer.Argument(help="Name of the branch to switch to"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Switch to a different branch."""
    project_key = resolve_project(project)
    output = resolve_output_format()
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        git = proj.get_project_git()
        data = git.switch(branch_name)
        out = data.get("output", "") if isinstance(data, dict) else ""
        _finish_git_action(
            data,
            output,
            f"Switched to branch '{branch_name}' in {project_key}",
            f"Switch to '{branch_name}' failed in {project_key}"
            + (f": {out}" if out else ""),
        )
    except Exception as e:
        handle_api_error(e)


@app.command()
def tags(
    ctx: typer.Context,
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """List tags in the project's git repository."""
    project_key = resolve_project(project)
    output = resolve_output_format()
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        git = proj.get_project_git()
        data = git.list_tags()

        if output == "json":
            render_raw(data, output_format="json")
        else:
            rows = []
            for t in data:
                rows.append(
                    {
                        "name": t.get("shortName", t.get("name", "")),
                        "commit": t.get("commit", "")[:8],
                        "annotations": t.get("annotations", ""),
                    }
                )
            render(
                rows,
                ["name", "commit", "annotations"],
                output_format=output,
                title=f"Tags ({project_key})",
            )
    except Exception as e:
        handle_api_error(e)


@app.command("create-tag")
def create_tag(
    ctx: typer.Context,
    name: str = typer.Argument(help="Tag name"),
    ref: str = typer.Option(
        "HEAD", "--ref", help="Commit reference to tag (default: HEAD)"
    ),
    message: str | None = typer.Option(
        None, "--message", "-m", help="Tag annotation message"
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Create a tag on the project's git repository."""
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        git = proj.get_project_git()
        git.create_tag(name, reference=ref, message=message or "")
        success(f"Created tag '{name}' in {project_key}")
    except Exception as e:
        handle_api_error(e)


@app.command()
def remote(
    ctx: typer.Context,
    set_url: str | None = typer.Option(
        None, "--set", help="Set remote URL (if omitted, shows current URL)"
    ),
    name: str = typer.Option("origin", "--name", help="Remote name (default: origin)"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Get or set the remote URL for the project's git repository.

    Without --set: shows the current remote URL.
    With --set URL: sets the remote URL.
    """
    project_key = resolve_project(project)
    output = resolve_output_format()
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        git = proj.get_project_git()

        if set_url is not None:
            git.set_remote(set_url, name=name)
            success(f"Set remote '{name}' to {set_url} in {project_key}")
        else:
            url = git.get_remote(name=name)
            if output == "json":
                render_raw({"name": name, "url": url}, output_format="json")
            elif url:
                render_raw(url)
            else:
                warn(f"No remote '{name}' configured in {project_key}.")
    except Exception as e:
        handle_api_error(e)


@app.command("reset-to-upstream")
def reset_to_upstream(
    ctx: typer.Context,
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip safety guard"),
) -> None:
    """Hard-reset the current branch to its upstream (remote) state.

    Drops ALL local changes: uncommitted edits AND local-only commits that have
    not been pushed. Tier-2 guard: requires --yes.
    """
    from dku_cli.safety import Tier, guard

    project_key = resolve_project(project)
    guard(
        ctx,
        tier=Tier.DELETE,
        action="git.reset_to_upstream",
        subject=(
            f"git working copy of project {project_key} "
            "(drops uncommitted changes AND local-only commits)"
        ),
        yes=yes,
        prompt=(
            f"Hard-reset project '{project_key}' to its upstream branch? This drops all "
            "uncommitted changes and any local commits that have not been pushed."
        ),
    )
    try:
        client = get_client_from_ctx(ctx)
        git = client.get_project(project_key).get_project_git()
    except Exception as e:
        handle_api_error(e)
        return
    try:
        git.reset_to_upstream()
        success(f"Reset {project_key} to upstream")
    except Exception as e:
        _explain_reset_to_upstream_failure(e, git, project_key)


@app.command("reset-to-head")
def reset_to_head(
    ctx: typer.Context,
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip safety guard"),
) -> None:
    """Drop uncommitted changes, hard-resetting the working copy to HEAD.

    Local commits are preserved -- only uncommitted edits are discarded.
    Tier-2 guard: requires --yes.
    """
    from dku_cli.safety import Tier, guard

    project_key = resolve_project(project)
    guard(
        ctx,
        tier=Tier.DELETE,
        action="git.reset_to_head",
        subject=f"git working copy of project {project_key} (drops uncommitted changes)",
        yes=yes,
        prompt=(
            f"Drop all uncommitted changes in project '{project_key}' and reset to HEAD? "
            "Committed work is preserved."
        ),
    )
    try:
        client = get_client_from_ctx(ctx)
        git = client.get_project(project_key).get_project_git()
        git.reset_to_head()
        success(f"Reset {project_key} working copy to HEAD")
    except Exception as e:
        handle_api_error(e)
