"""Root Typer app — registers sub-commands and global options."""

from __future__ import annotations

import sys
from typing import Optional

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


# Monkey-patch TyperGroup/Command help rendering: --help always emits the
# compact machine-readable spec JSON for the node asked about, so a reflexive
# `--help` returns exact flags, types, and choices with minimal token overhead.
def _spec_help(self, ctx, formatter) -> None:
    import json

    from dku_cli.spec import spec_node_for

    node = spec_node_for(self, ctx)
    formatter.write(json.dumps(node, default=str, separators=(",", ":")) + "\n")


TyperGroup.format_help = _spec_help
TyperCommand.format_help = _spec_help


# The output format flag is global (`--format`/`-o` on the root callback), but
# agents and humans reflexively append it after the subcommand
# (`dku agent list --format json`). Click only accepts group-level options
# before the noun, so each parse level extracts the flag from its own args and
# applies it directly — the flag works at any position. Two guards keep this
# from colliding with command-owned flags:
#   * a command that defines `--format`/`-o` itself (e.g. file/export formats)
#     keeps it — those spellings are never extracted there;
#   * groups only scan their leading flag run (a subcommand name ends it), so
#     a trailing flag is always interpreted by the leaf that owns it.
# Tokens after `--` are left untouched.
_FORMAT_FLAGS = ("--format", "-o")


def _extract_format_flag(
    args: list[str],
    ctx,
    *,
    owned: frozenset[str] = frozenset(),
    prefix_only: bool = False,
) -> list[str]:
    import click

    flags = tuple(f for f in _FORMAT_FLAGS if f not in owned)
    rest: list[str] = []
    value: str | None = None
    i = 0
    while i < len(args):
        tok = args[i]
        if tok == "--" or (prefix_only and not tok.startswith("-")):
            rest.extend(args[i:])
            break
        if tok in flags:
            if i + 1 >= len(args):
                raise click.exceptions.UsageError(
                    f"Option '{tok}' requires an argument.", ctx=ctx
                )
            value = args[i + 1]
            i += 2
            continue
        if any(tok.startswith(f + "=") for f in flags):
            value = tok.split("=", 1)[1]
            i += 1
            continue
        rest.append(tok)
        i += 1
    if value is not None:
        from dku_cli.output import OUTPUT_FORMATS, set_output_format

        if value.lower() not in OUTPUT_FORMATS:
            raise click.exceptions.UsageError(
                f"Invalid value for '--format': must be one of: "
                f"{', '.join(OUTPUT_FORMATS)}",
                ctx=ctx,
            )
        set_output_format(value)
    return rest


def _owned_opts(cmd) -> frozenset[str]:
    return frozenset(
        o for p in cmd.params for o in (*p.opts, *getattr(p, "secondary_opts", ()))
    )


_original_group_parse_args = TyperGroup.parse_args
_original_command_parse_args = TyperCommand.parse_args


def _group_parse_args(self, ctx, args):
    args = _extract_format_flag(args, ctx, owned=_owned_opts(self), prefix_only=True)
    return _original_group_parse_args(self, ctx, args)


def _command_parse_args(self, ctx, args):
    args = _extract_format_flag(args, ctx, owned=_owned_opts(self))
    return _original_command_parse_args(self, ctx, args)


TyperGroup.parse_args = _group_parse_args
TyperCommand.parse_args = _command_parse_args

app = typer.Typer(
    name="dku",
    help="Dataiku Headless — the headless DSS control plane for AI agents",
    no_args_is_help=False,
    invoke_without_command=True,
    # Plain Click error rendering — no Rich panel boxes around usage errors.
    rich_markup_mode=None,
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
        print(version_string())
        raise typer.Exit()


def _configure_output(format_: str | None) -> None:
    from dku_cli.output import OUTPUT_FORMATS, set_output_format

    # None means "flag not passed here" — never reset, because the flag may
    # already have been applied by _extract_format_flag at any parse level.
    if format_ is None:
        return
    if format_.lower() not in OUTPUT_FORMATS:
        raise typer.BadParameter(
            f"Output format must be one of: {', '.join(OUTPUT_FORMATS)}",
            param_hint="--format",
        )
    set_output_format(format_)


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
    format_: Optional[str] = typer.Option(
        None,
        "--format",
        "-o",
        envvar="DKU_FORMAT",
        help="Output override: json (indented), csv, ids (one id per line, "
        "to pipe), or quiet (data only, no stderr messages). Default: TSV "
        "for lists, compact JSON for objects. Accepted at any position.",
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
    """Dataiku Headless — the headless DSS control plane for AI agents."""
    ctx.ensure_object(dict)
    if url:
        ctx.obj["url"] = url
    if api_key:
        ctx.obj["api_key"] = api_key
    if profile:
        ctx.obj["profile"] = profile
    if dangerous:
        ctx.obj["dangerous"] = True

    _configure_output(format_)

    if ctx.invoked_subcommand is None:
        print(ctx.get_help())
        raise typer.Exit()


@app.command()
def whoami(ctx: typer.Context) -> None:
    """Show current authenticated user."""
    from dku_cli.client import resolve_node_type
    from dku_cli.errors import handle_api_error
    from dku_cli.helpers import ALL_NODE_TYPES, get_client_from_ctx
    from dku_cli.output import render, render_raw, resolve_output_format

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

        payload = {
            "user": user_name,
            "url": url,
            "dss_version": version,
            "node_type": node_type,
            "groups": groups,
        }
        output = resolve_output_format()
        if output == "ids":
            render([{"user": user_name}], ["user"], output_format="ids")
        elif output == "csv":
            render(
                [{**payload, "groups": ",".join(groups)}],
                ["user", "url", "dss_version", "node_type", "groups"],
                output_format="csv",
            )
        else:
            render_raw(payload, output_format=output)
    except Exception as e:
        handle_api_error(e)
