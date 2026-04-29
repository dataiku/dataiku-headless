"""dku git — status, log, diff, commit, pull, push, fetch, branches, create-branch, delete-branch, switch, tags, create-tag, remote."""

from __future__ import annotations

import typer

from dku_cli.errors import handle_api_error
from dku_cli.helpers import get_client_from_ctx, resolve_project
from dku_cli.output import error, render, render_raw, resolve_output_format, success

app = typer.Typer(help="Manage a DSS project's git repository.")


@app.command()
def status(
    ctx: typer.Context,
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Show the current state of the project's git repository."""
    project_key = resolve_project(project)
    output = resolve_output_format(output)
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

            render_raw(summary, output_format="table")
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
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """List commits in the project's git repository."""
    project_key = resolve_project(project)
    output = resolve_output_format(output)
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
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Show changes between commits or working copy and last commit.

    No flags: working copy vs last commit.
    --from only: changes in that commit.
    --from and --to: changes between two commits.
    """
    project_key = resolve_project(project)
    output = resolve_output_format(output)
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
            render_raw(summary, output_format="table")
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
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Pull changes from the remote repository (rebase)."""
    project_key = resolve_project(project)
    output = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        git = proj.get_project_git()
        data = git.pull(branch_name=branch)
        if output == "json":
            render_raw(data, output_format="json")
        else:
            ok = data.get("success", False) if isinstance(data, dict) else True
            out = data.get("output", "") if isinstance(data, dict) else str(data)
            if ok:
                success(f"Pull complete in {project_key}: {out}")
            else:
                error(f"Pull failed in {project_key}: {out}")
    except Exception as e:
        handle_api_error(e)


@app.command()
def push(
    ctx: typer.Context,
    branch: str | None = typer.Option(
        None, "--branch", "-b", help="Branch to push (default: current)"
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Push local commits to the remote repository."""
    project_key = resolve_project(project)
    output = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        git = proj.get_project_git()
        data = git.push(branch_name=branch)
        if output == "json":
            render_raw(data, output_format="json")
        else:
            ok = data.get("success", False) if isinstance(data, dict) else True
            out = data.get("output", "") if isinstance(data, dict) else str(data)
            if ok:
                success(f"Push complete in {project_key}: {out}")
            else:
                error(f"Push failed in {project_key}: {out}")
    except Exception as e:
        handle_api_error(e)


@app.command()
def fetch(
    ctx: typer.Context,
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Fetch refs from the remote repository."""
    project_key = resolve_project(project)
    output = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        git = proj.get_project_git()
        data = git.fetch()
        if output == "json":
            render_raw(data, output_format="json")
        else:
            ok = data.get("success", False) if isinstance(data, dict) else True
            if ok:
                success(f"Fetch complete in {project_key}")
            else:
                error(f"Fetch failed in {project_key}")
    except Exception as e:
        handle_api_error(e)


@app.command()
def branches(
    ctx: typer.Context,
    remote: bool = typer.Option(
        False, "--remote", "-r", help="Include remote branches"
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """List branches in the project's git repository."""
    project_key = resolve_project(project)
    output = resolve_output_format(output)
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
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Switch to a different branch."""
    project_key = resolve_project(project)
    output = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        git = proj.get_project_git()
        data = git.switch(branch_name)
        if output == "json":
            render_raw(data, output_format="json")
        else:
            success(f"Switched to branch '{branch_name}' in {project_key}")
    except Exception as e:
        handle_api_error(e)


@app.command()
def tags(
    ctx: typer.Context,
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """List tags in the project's git repository."""
    project_key = resolve_project(project)
    output = resolve_output_format(output)
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
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Get or set the remote URL for the project's git repository.

    Without --set: shows the current remote URL.
    With --set URL: sets the remote URL.
    """
    project_key = resolve_project(project)
    output = resolve_output_format(output)
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
            else:
                print(url or "(no remote configured)")
    except Exception as e:
        handle_api_error(e)
