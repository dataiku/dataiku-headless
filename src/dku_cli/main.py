"""Root Typer app — registers sub-commands and global options."""

from __future__ import annotations

from typing import Optional

import typer

from dku_cli.brand import version_string
from dku_cli.commands import (
    agent,
    agent_block,
    agent_hub,
    agent_review,
    agent_tool,
    analysis,
    api_deployer,
    api_service,
    auth_cmd,
    bundle,
    codeenv,
    codestudio,
    config_cmd,
    connection,
    dashboard,
    dataset,
    discussion,
    dq,
    evaluation_store,
    flow,
    folder,
    git_cmd,
    group,
    insight,
    job,
    knowledge,
    library,
    llm,
    macro,
    ml,
    model,
    notebook,
    plugin,
    project,
    project_deployer,
    rag,
    recipe,
    scenario,
    semantic_model,
    sql,
    user,
    webapp,
    wiki,
)

app = typer.Typer(
    name="dku",
    help="[blue bold]◆[/blue bold] Developer CLI for Dataiku DSS",
    no_args_is_help=False,
    invoke_without_command=True,
    rich_markup_mode="rich",
)

# Register sub-commands
app.add_typer(analysis.app, name="analysis")
app.add_typer(agent.app, name="agent")
app.add_typer(agent_block.app, name="agent-block")
app.add_typer(agent_hub.app, name="agent-hub")
app.add_typer(agent_review.app, name="agent-review")
app.add_typer(agent_tool.app, name="agent-tool")
app.add_typer(api_deployer.app, name="api-deployer")
app.add_typer(api_service.app, name="api-service")
app.add_typer(auth_cmd.app, name="auth")
app.add_typer(bundle.app, name="bundle")
app.add_typer(codestudio.app, name="code-studio")
app.add_typer(dashboard.app, name="dashboard")
app.add_typer(discussion.app, name="discussion")
app.add_typer(dq.app, name="dq")
app.add_typer(evaluation_store.app, name="evaluation-store")
app.add_typer(project.app, name="project")
app.add_typer(project_deployer.app, name="project-deployer")
app.add_typer(dataset.app, name="dataset")
app.add_typer(scenario.app, name="scenario")
app.add_typer(semantic_model.app, name="semantic-model")
app.add_typer(job.app, name="job")
app.add_typer(plugin.app, name="plugin")
app.add_typer(config_cmd.app, name="config")
app.add_typer(rag.app, name="rag")
app.add_typer(recipe.app, name="recipe")
app.add_typer(codeenv.app, name="code-env")
app.add_typer(connection.app, name="connection")
app.add_typer(ml.app, name="ml")
app.add_typer(model.app, name="model")
app.add_typer(notebook.app, name="notebook")
app.add_typer(folder.app, name="folder")
app.add_typer(group.app, name="group")
app.add_typer(insight.app, name="insight")
app.add_typer(knowledge.app, name="knowledge")
app.add_typer(library.app, name="library")
app.add_typer(llm.app, name="llm")
app.add_typer(webapp.app, name="webapp")
app.add_typer(macro.app, name="macro")
app.add_typer(user.app, name="user")
app.add_typer(flow.app, name="flow")
app.add_typer(git_cmd.app, name="git")
app.add_typer(wiki.app, name="wiki")
app.add_typer(sql.app, name="sql")


def _version_callback(value: bool) -> None:
    if value:
        from dku_cli.brand import print_logo

        print_logo(subtitle=version_string())
        raise typer.Exit()


@app.callback()
def main(
    ctx: typer.Context,
    url: Optional[str] = typer.Option(
        None, "--url", envvar="DKU_URL", help="DSS instance URL"
    ),
    api_key: Optional[str] = typer.Option(
        None, "--api-key", envvar="DKU_API_KEY", help="API key"
    ),
    profile: Optional[str] = typer.Option(
        None, "--profile", "-p", help="Auth profile name"
    ),
    quiet: Optional[bool] = typer.Option(
        None, "--quiet", "-q", help="Suppress info/success messages"
    ),
    errors: str = typer.Option(
        "text", "--errors", help="Error output format (text or json)"
    ),
    version: Optional[bool] = typer.Option(
        None,
        "--version",
        "-V",
        callback=_version_callback,
        is_eager=True,
        help="Show version",
    ),
) -> None:
    """[blue bold]◆[/blue bold] Developer CLI for Dataiku DSS — like kubectl for your DSS instance."""
    ctx.ensure_object(dict)
    if url:
        ctx.obj["url"] = url
    if api_key:
        ctx.obj["api_key"] = api_key
    if profile:
        ctx.obj["profile"] = profile
    if quiet:
        from dku_cli.output import set_quiet

        set_quiet(True)
    if errors not in ("text", "json"):
        raise typer.BadParameter(
            "Error output format must be one of: text, json", param_hint="--errors"
        )
    from dku_cli.output import set_error_format

    set_error_format(errors)

    if ctx.invoked_subcommand is None:
        from dku_cli.brand import print_logo

        print_logo(subtitle=version_string())
        ctx.get_help()
        raise typer.Exit()


@app.command()
def whoami(ctx: typer.Context) -> None:
    """Show current authenticated user."""
    from dku_cli.brand import ICON
    from dku_cli.errors import handle_api_error
    from dku_cli.helpers import get_client_from_ctx

    try:
        client = get_client_from_ctx(ctx)
        auth_info = client.get_auth_info()
        user_name = auth_info.get("authIdentifier", "unknown")
        groups = auth_info.get("groups", [])

        try:
            url = client.host
            version = client.get_instance_info().raw.get("dssVersion", "")
        except Exception:
            version = ""
            url = ""

        parts = [f"{ICON} {user_name}"]
        if url:
            parts.append(f"on {url}")
        if version:
            parts.append(f"(DSS {version})")
        if groups:
            parts.append(f"[{', '.join(groups)}]")

        print(" ".join(parts))
    except Exception as e:
        handle_api_error(e)
