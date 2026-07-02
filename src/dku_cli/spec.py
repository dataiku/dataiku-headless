"""Machine-readable command spec generator for dku CLI.

Introspects a Typer command/group and produces structured JSON so agents learn
exact flags from the command they already reach for. ``--help`` always renders
this JSON:

    dku --help                    groups + root command details + global options
    dku recipe --help             commands in the `recipe` group (concise signatures)
    dku recipe create-join --help full detail for one command (args, flags, types)

Each lookup stays scoped to the requested command/group, instead of dumping the
whole tree from the root.
"""

from __future__ import annotations

from collections.abc import Mapping
import json
import re

import click

from dku_cli.examples import examples_for

# ``UNSET`` is the sentinel Click uses for "no default given". It is only
# importable from ``click.core`` on Click >= 8.3 (pyproject pins ``click>=8.3``).
# Keep this import-safe with a private sentinel fallback so spec generation
# degrades rather than crashes on a host that ignores the pin.
try:
    from click.core import UNSET
except ImportError:  # pragma: no cover - click < 8.3 fallback

    class _Unset:
        pass

    UNSET = _Unset()

# Typer auto-adds these; skip them in the spec
_SKIP_PARAM_NAMES = {"install_completion", "show_completion"}

# Rich console markup like "[blue bold]◆[/blue bold]" leaks into help text.
# Strip style/closing tags only — lowercase words/colors — so usage brackets
# such as "[--profile NAME]" (uppercase / dashes) are left untouched.
_MARKUP = re.compile(r"\[/?[a-z0-9 #_]+\]")


def _clean(text: str | None) -> str:
    if not text:
        return ""
    return _MARKUP.sub("", text).strip()


def _type_str(t: click.ParamType) -> str:
    if isinstance(t, click.types.IntParamType):
        return "int"
    if isinstance(t, click.types.FloatParamType):
        return "float"
    if isinstance(t, click.types.BoolParamType):
        return "bool"
    if isinstance(t, click.types.StringParamType):
        return "str"
    if isinstance(t, click.Path):
        return "path"
    if _is_choice(t):
        return "choice"
    if isinstance(t, click.File):
        return "file"
    name = getattr(t, "name", None)
    if name == "text":
        return "str"
    return name if name else str(t)


def _param_dict(p: click.Parameter) -> dict:
    d: dict = {
        "name": p.name,
        "help": _clean(getattr(p, "help", "")),
        "required": p.required,
        "type": _type_str(p.type),
    }
    if _is_argument(p):
        d["opts"] = []
    elif _is_option(p):
        d["opts"] = p.opts
        d["is_flag"] = p.is_flag
        d["multiple"] = p.multiple
        if p.secondary_opts:
            d["secondary_opts"] = p.secondary_opts
        if p.envvar:
            d["envvar"] = p.envvar
    if _is_choice(p.type):
        d["choices"] = list(p.type.choices)
    if p.default is not None and p.default is not UNSET:
        try:
            json.dumps(p.default)
            d["default"] = p.default
        except (TypeError, OverflowError):
            d["default"] = repr(p.default)
    return d


def _skip_param(p: click.Parameter) -> bool:
    """Mirror Click's own help formatter: omit Typer-injected and hidden params."""
    return p.name in _SKIP_PARAM_NAMES or getattr(p, "hidden", False)


def _is_choice(t: click.ParamType) -> bool:
    return isinstance(t, click.Choice) or hasattr(t, "choices")


def _is_argument(p: click.Parameter) -> bool:
    return getattr(p, "param_type_name", "") == "argument" or isinstance(
        p, click.Argument
    )


def _is_option(p: click.Parameter) -> bool:
    return getattr(p, "param_type_name", "") == "option" or isinstance(p, click.Option)


def _child_commands(cmd: click.Command) -> Mapping[str, click.Command] | None:
    commands = getattr(cmd, "commands", None)
    return commands


def _command_detail(cmd: click.Command) -> dict:
    args, opts = [], []
    for p in cmd.params:
        if _skip_param(p):
            continue
        (opts if _is_option(p) else args).append(_param_dict(p))
    return {
        "name": cmd.name,
        "help": _clean(cmd.help or cmd.short_help),
        "arguments": args,
        "options": opts,
    }


def _long_opt(p: click.Option) -> str:
    """Representative flag for usage strings: prefer the first long option."""
    return next((o for o in p.opts if o.startswith("--")), p.opts[0])


def _flag_token(p: click.Option) -> str:
    """Render a boolean flag for usage strings.

    For a flag with a secondary name (e.g. ``--pass/--fail``) show both as
    ``--pass / --fail`` so agents can discover the alternative; otherwise show
    the single primary long opt. Without this, a required ``--pass/--fail``
    verdict reads as a mandatory literal ``--pass`` and the FAIL path is hidden.
    """
    primary = _long_opt(p)
    secondary = next(
        (o for o in p.secondary_opts if o.startswith("--")),
        p.secondary_opts[0] if p.secondary_opts else None,
    )
    return f"{primary} / {secondary}" if secondary else primary


def _usage_string(cmd: click.Command) -> str:
    """Compact one-line usage for group listings.

    Shows positional args and *required* options inline (choices expanded so the
    agent can pick one without drilling in); collapses all optional flags into a
    trailing ``[options]`` marker. Exact flags/types/defaults live in the
    command-level detail (`dku <group> <command> --help`).
    """
    parts: list[str] = []
    for p in cmd.params:
        if _skip_param(p) or not _is_argument(p):
            continue
        token = f"<{p.name}>" if p.required else f"[{p.name}]"
        if p.nargs == -1 or getattr(p, "multiple", False):
            token += "..."
        parts.append(token)

    has_optional = False
    for p in cmd.params:
        if _skip_param(p) or not _is_option(p):
            continue
        if not p.required:
            has_optional = True
            continue
        if p.is_flag:
            parts.append(_flag_token(p))
            continue
        flag = _long_opt(p)
        if isinstance(p.type, click.Choice):
            value = "|".join(p.type.choices)
        else:
            value = _type_str(p.type)
        token = f"{flag} <{value}>"
        if p.multiple:
            token += "..."
        parts.append(token)
    if has_optional:
        parts.append("[options]")
    return " ".join(parts)


def _command_signature(cmd: click.Command) -> dict:
    # No "name": the group listing keys each entry by command name already.
    return {
        "help": _one_line(cmd),
        "signature": _usage_string(cmd),
    }


def _one_line(cmd: click.Command) -> str:
    return _clean(cmd.short_help or cmd.help).split("\n", 1)[0]


def _group_detail(group: click.Group) -> dict:
    """Direct children of a group with concise command signatures.

    Commands get a one-line usage signature; nested subgroups stay one-line
    (drill in with `dku <group> <subgroup> --help`). This keeps even large
    groups small enough to load cheaply.
    """
    commands, groups = {}, {}
    for name, cmd in sorted(group.commands.items()):
        if getattr(cmd, "hidden", False):
            continue
        child_commands = _child_commands(cmd)
        if child_commands is not None:
            groups[name] = _clean(cmd.help).split("\n", 1)[0]
        else:
            commands[name] = _command_signature(cmd)
    out: dict = {}
    if group.help:
        out["help"] = _clean(group.help).split("\n", 1)[0]
    if commands:
        out["commands"] = commands
    if groups:
        out["groups"] = groups
    return out


def _root_detail(group: click.Group) -> dict:
    """Root index: root commands are detailed, groups stay one-line."""
    commands, groups = {}, {}
    for name, cmd in sorted(group.commands.items()):
        if getattr(cmd, "hidden", False):
            continue
        child_commands = _child_commands(cmd)
        if child_commands is not None:
            groups[name] = _clean(cmd.help).split("\n", 1)[0]
        else:
            detail = _command_detail(cmd)
            detail.pop("name")  # keyed by name already
            commands[name] = detail
    out: dict = {}
    if group.help:
        out["help"] = _clean(group.help).split("\n", 1)[0]
    if commands:
        out["commands"] = commands
    if groups:
        out["groups"] = groups
    return out


def _flat_index_commands(group: click.Command) -> dict[str, str]:
    entries: dict[str, str] = {}

    def walk(cmd: click.Command, prefix: tuple[str, ...]) -> None:
        commands = _child_commands(cmd)
        if commands is None:
            return
        for name, child in sorted(commands.items()):
            if getattr(child, "hidden", False):
                continue
            path = (*prefix, name)
            entries[" ".join(path)] = _one_line(child)
            walk(child, path)

    walk(group, ())
    return entries


def full_index(root: click.Group) -> dict[str, dict]:
    """Every group's commands with a one-line description, in one pass.

    Powers `references/command-index.md` and `dku commands`: a single,
    generated artifact an agent reads once instead of drilling `--help` into
    each group it hasn't touched yet. Only names and one-liners — exact
    flags/types/defaults stay behind `--help`, unchanged.
    """
    index: dict[str, dict] = {}
    root_commands: dict[str, str] = {}
    for name, cmd in sorted(root.commands.items()):
        if getattr(cmd, "hidden", False):
            continue
        commands = _child_commands(cmd)
        if commands is None:
            root_commands[name] = _one_line(cmd)
            continue
        index[name] = {
            "help": _clean(cmd.help).split("\n", 1)[0],
            "commands": _flat_index_commands(cmd),
        }
    if root_commands:
        index["root"] = {
            "help": "Root-level commands.",
            "commands": root_commands,
        }
    return index


def command_index_rows(index: dict[str, dict]) -> list[dict[str, str]]:
    return [
        {
            "path": command if group == "root" else f"{group} {command}",
            "group": group,
            "command": command,
            "description": one_liner,
        }
        for group, node in index.items()
        for command, one_liner in node["commands"].items()
    ]


def spec_node_for(cmd: click.Command, ctx: click.Context | None = None) -> dict:
    """Spec node for a single Click command/group, built from the object itself.

    Used by ``--help``: a group renders concise
    signatures for its direct child commands, and a command renders its own
    full arg/flag detail. The root group also surfaces global options.
    *ctx* supplies the command path for the examples lookup. No tool/version/
    path meta is emitted — it would repeat what the agent just typed, on
    every probe.
    """
    path: list[str] = []
    if ctx is not None and ctx.command_path:
        path = ctx.command_path.split()[1:]  # drop the "dku" tool name

    child_commands = _child_commands(cmd)
    if child_commands is not None:
        if not path:
            body = _root_detail(cmd)
            globals_ = [
                _param_dict(p)
                for p in cmd.params
                if _is_option(p) and not _skip_param(p)
            ]
            if globals_:
                body["global_options"] = globals_
        else:
            body = _group_detail(cmd)
        return body

    body = _command_detail(cmd)
    examples = examples_for(path)
    if examples:
        body["examples"] = examples
    return body
