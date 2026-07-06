"""Position-agnostic `--format`/`-o` extraction for the global output flag.

The output format flag lives on the root callback, but agents and humans
reflexively append it after the subcommand (`dku agent list --format json`).
These helpers lift the flag out of the argument list at every parse level;
main.py wires them into TyperGroup/TyperCommand.parse_args.
"""

from __future__ import annotations

import typer

_FORMAT_FLAGS = ("--format", "-o")


def _extract_format_flag(
    args: list[str],
    ctx,
    *,
    owned: frozenset[str] = frozenset(),
    prefix_only: bool = False,
) -> list[str]:
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
                raise typer.BadParameter(f"Option '{tok}' requires an argument.")
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
            raise typer.BadParameter(
                f"Invalid value for '--format': must be one of: "
                f"{', '.join(OUTPUT_FORMATS)}"
            )
        set_output_format(value)
    return rest


def _owned_opts(cmd) -> frozenset[str]:
    return frozenset(
        o for p in cmd.params for o in (*p.opts, *getattr(p, "secondary_opts", ()))
    )
