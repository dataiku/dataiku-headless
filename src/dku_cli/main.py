"""Root Typer app — registers sub-commands and global options."""

from __future__ import annotations

import sys
from typing import Optional

import click
import typer
from typer.core import TyperCommand, TyperGroup

from dku_cli.brand import version_string
from dku_cli.commands import (
    agent,
    agent_block,
    agent_hub,
    agent_review,
    agent_tool,
    admin,
    analysis,
    api_deployer,
    api_key,
    api_service,
    app_cmd,
    app_designer,
    auth_cmd,
    bundle,
    cluster,
    codeenv,
    codestudio,
    config_cmd,
    connection,
    continuous,
    dashboard,
    dataset,
    discussion,
    dq,
    eal,
    evaluation_store,
    flow,
    folder,
    git_cmd,
    govern,
    group,
    insight,
    job,
    knowledge,
    library,
    llm,
    macro,
    meaning,
    ml,
    model,
    model_comparison,
    notebook,
    plugin,
    project,
    project_deployer,
    project_folder,
    rag,
    recipe,
    scenario,
    semantic_model,
    sql,
    streaming,
    user,
    webapp,
    wiki,
    workspace,
)

# Raise the csv field-size limit at startup. dataikuapi streams dataset rows
# as CSV and parses them with the stdlib `csv` module, whose default
# field_size_limit (131072 bytes) rejects large cells — geometry WKT/GeoJSON,
# long JSON blobs, big text columns — with "field larger than field limit",
# surfacing as a confusing DSS API error on `dataset head` / `sql query`.
# The limit is a module global, so raising it here fixes every iter_rows read.
# Use the standard decrement-on-OverflowError idiom (sys.maxsize overflows the
# C long on some platforms).
import csv as _csv


def _raise_csv_field_limit() -> None:
    limit = sys.maxsize
    while True:
        try:
            _csv.field_size_limit(limit)
            return
        except OverflowError:
            limit = int(limit // 10)


_raise_csv_field_limit()

# Monkey-patch TyperGroup/Command help rendering. Two overrides:
#   * DKU_AGENT_HELP=1 → emit compact machine-readable spec JSON instead of
#     human help, so an agent's reflexive `--help` returns exact flags with
#     minimal token overhead.
#   * --compact → use Click plain-text help for non-agent output paths.
_original_group_help = TyperGroup.format_help
_original_command_help = TyperCommand.format_help


def _agent_help_json(self, ctx, formatter) -> bool:
    """If DKU_AGENT_HELP=1, write this command's spec JSON and return True."""
    import os

    if os.environ.get("DKU_AGENT_HELP") != "1":
        return False
    import json

    from dku_cli.spec import spec_node_for

    node = spec_node_for(self, ctx)
    formatter.write(json.dumps(node, default=str, separators=(",", ":")) + "\n")
    return True


def _help_renderer(compact_render, rich_render):
    """Build a format_help override: agent-help JSON > compact plain text > Rich.

    One factory instead of two hand-rolled near-identical patches, so the
    interception order is defined in exactly one place.
    """

    def render(self, ctx, formatter):
        from dku_cli.output import is_compact

        if _agent_help_json(self, ctx, formatter):
            return
        if is_compact():
            compact_render(self, ctx, formatter)
        else:
            rich_render(self, ctx, formatter)

    return render


TyperGroup.format_help = _help_renderer(click.Group.format_help, _original_group_help)
TyperCommand.format_help = _help_renderer(
    click.Command.format_help, _original_command_help
)

# --compact is normally consumed by the app callback, but --help is an eager
# Click option that renders before the callback runs. Detect --compact from
# argv at import time so `dku --compact --help` actually produces plain help.
if "--compact" in sys.argv:
    from dku_cli.output import set_compact

    set_compact(True)

app = typer.Typer(
    name="dku",
    help="[blue bold]◆[/blue bold] Developer CLI for Dataiku DSS",
    no_args_is_help=False,
    invoke_without_command=True,
    rich_markup_mode="rich",
)

# Register sub-commands
app.add_typer(admin.app, name="admin")
app.add_typer(analysis.app, name="analysis")
app.add_typer(api_key.app, name="api-key")
app.add_typer(agent.app, name="agent")
app.add_typer(agent_block.app, name="agent-block")
app.add_typer(agent_hub.app, name="agent-hub")
app.add_typer(agent_review.app, name="agent-review")
app.add_typer(agent_tool.app, name="agent-tool")
app.add_typer(api_deployer.app, name="api-deployer")
app.add_typer(api_service.app, name="api-service")
app.add_typer(app_cmd.app, name="app")
app.add_typer(app_designer.app, name="app-designer")
app.add_typer(auth_cmd.app, name="auth")
app.add_typer(bundle.app, name="bundle")
app.add_typer(codestudio.app, name="code-studio")
app.add_typer(dashboard.app, name="dashboard")
app.add_typer(discussion.app, name="discussion")
app.add_typer(dq.app, name="dq")
app.add_typer(eal.app, name="eal")
app.add_typer(evaluation_store.app, name="evaluation-store")
app.add_typer(project.app, name="project")
app.add_typer(project_deployer.app, name="project-deployer")
app.add_typer(project_folder.app, name="project-folder")
app.add_typer(dataset.app, name="dataset")
app.add_typer(scenario.app, name="scenario")
app.add_typer(semantic_model.app, name="semantic-model")
app.add_typer(job.app, name="job")
app.add_typer(plugin.app, name="plugin")
app.add_typer(config_cmd.app, name="config")
app.add_typer(rag.app, name="rag")
app.add_typer(recipe.app, name="recipe")
app.add_typer(codeenv.app, name="code-env")
app.add_typer(cluster.app, name="cluster")
app.add_typer(connection.app, name="connection")
app.add_typer(continuous.app, name="continuous")
app.add_typer(ml.app, name="ml")
app.add_typer(model.app, name="model")
app.add_typer(model_comparison.app, name="model-comparison")
app.add_typer(notebook.app, name="notebook")
app.add_typer(folder.app, name="folder")
# Hidden alias — DSS UI calls them "managed folders". Surfaces the same
# verbs under the noun agents reach for first.
app.add_typer(folder.app, name="managedfolder", hidden=True)
app.add_typer(folder.app, name="managed-folder", hidden=True)
app.add_typer(group.app, name="group")
app.add_typer(insight.app, name="insight")
app.add_typer(knowledge.app, name="knowledge")
app.add_typer(library.app, name="library")
app.add_typer(llm.app, name="llm")
app.add_typer(webapp.app, name="webapp")
app.add_typer(macro.app, name="macro")
app.add_typer(meaning.app, name="meaning")
app.add_typer(user.app, name="user")
app.add_typer(flow.app, name="flow")
app.add_typer(git_cmd.app, name="git")
app.add_typer(govern.app, name="govern")
app.add_typer(wiki.app, name="wiki")
app.add_typer(workspace.app, name="workspace")
app.add_typer(sql.app, name="sql")
app.add_typer(streaming.app, name="streaming")


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
        None, "--profile", "-p", envvar="DKU_PROFILE", help="Auth profile name"
    ),
    quiet: Optional[bool] = typer.Option(
        None, "--quiet", "-q", help="Suppress info/success messages"
    ),
    compact: Optional[bool] = typer.Option(
        None,
        "--compact",
        help="Compact machine-readable output (no indentation, omit empty fields, plain help text)",
    ),
    errors: str = typer.Option(
        "text", "--errors", help="Error output format (text or json)"
    ),
    dangerous: Optional[bool] = typer.Option(
        None,
        "--dangerous",
        envvar="DKU_DANGEROUS",
        help="Disable safety guards for destructive commands (tiers 2–3). Prints a warning banner.",
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
    if dangerous:
        ctx.obj["dangerous"] = True
    if quiet:
        from dku_cli.output import set_quiet

        set_quiet(True)
    if compact:
        from dku_cli.output import set_compact

        set_compact(True)
    if errors not in ("text", "json"):
        raise typer.BadParameter(
            "Error output format must be one of: text, json", param_hint="--errors"
        )
    from dku_cli.output import set_error_format

    set_error_format(errors)

    if ctx.invoked_subcommand is None:
        from dku_cli.brand import print_logo

        print_logo(subtitle=version_string())
        help_text = ctx.get_help()
        if help_text:
            # Compact mode: get_help() returns plain text from Click
            print(help_text)
        raise typer.Exit()


@app.command()
def whoami(ctx: typer.Context) -> None:
    """Show current authenticated user."""
    from dku_cli.brand import ICON
    from dku_cli.client import resolve_node_type
    from dku_cli.errors import handle_api_error
    from dku_cli.helpers import ALL_NODE_TYPES, get_client_from_ctx

    try:
        client = get_client_from_ctx(ctx, allowed_node_types=ALL_NODE_TYPES)
        auth_info = client.get_auth_info()
        user_name = auth_info.get("authIdentifier", "unknown")
        groups = auth_info.get("groups", [])

        try:
            url = client.host
            version = client.get_instance_info().raw.get("dssVersion", "")
        except Exception:
            version = ""
            url = ""

        opts = ctx.obj or {}
        node_type = resolve_node_type(profile=opts.get("profile"))

        parts = [f"{ICON} {user_name}"]
        if url:
            parts.append(f"on {url}")
        if version:
            parts.append(f"(DSS {version})")
        if node_type:
            parts.append(f"[{node_type}]")
        if groups:
            parts.append(f"[{', '.join(groups)}]")

        print(" ".join(parts))
    except Exception as e:
        handle_api_error(e)
