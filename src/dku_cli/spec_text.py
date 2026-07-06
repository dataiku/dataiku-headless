from __future__ import annotations

import json
import os
import shutil
import sys
import textwrap
from collections.abc import Mapping

from dku_cli.output import get_output_format


def render_help(node: dict, command_path: str) -> str:
    if (
        os.environ.get("DKU_TEXT_HELP") == "1"
        and sys.stdout.isatty()
        and get_output_format() != "json"
    ):
        return render_text_help(node, command_path)
    return json.dumps(node, default=str, separators=(",", ":")) + "\n"


def render_text_help(node: dict, command_path: str) -> str:
    width = shutil.get_terminal_size(fallback=(100, 24)).columns
    lines: list[str] = []
    title = command_path.strip() or "dku"
    lines.append(_usage(node, title))
    if help_text := node.get("help"):
        lines.extend(("", str(help_text)))

    if groups := node.get("groups"):
        lines.extend(("", "Groups:"))
        _append_mapping(lines, groups, width)

    if commands := node.get("commands"):
        lines.extend(("", "Commands:"))
        _append_commands(lines, commands, width)

    options = node.get("options") or node.get("global_options")
    if options:
        lines.extend(("", "Options:"))
        _append_options(lines, options, width)

    if arguments := node.get("arguments"):
        lines.extend(("", "Arguments:"))
        _append_params(lines, arguments, width)

    if examples := node.get("examples"):
        lines.extend(("", "Examples:"))
        for example in examples:
            lines.append(f"  {example}")

    return "\n".join(lines).rstrip() + "\n"


def _usage(node: dict, title: str) -> str:
    if node.get("groups") or node.get("commands"):
        return f"Usage: {title} [command] [options]"

    parts = [title]
    for arg in node.get("arguments") or []:
        name = str(arg.get("name", "arg"))
        token = f"<{name}>" if arg.get("required") else f"[{name}]"
        parts.append(token)
    if node.get("options"):
        parts.append("[options]")
    return "Usage: " + " ".join(parts)


def _append_mapping(lines: list[str], values: Mapping[str, str], width: int) -> None:
    for name, help_text in values.items():
        _append_wrapped(lines, name, str(help_text), width)


def _append_commands(lines: list[str], values: Mapping[str, dict], width: int) -> None:
    for name, detail in values.items():
        signature = detail.get("signature")
        label = f"{name} {signature}" if signature else name
        _append_wrapped(lines, label, str(detail.get("help", "")), width)


def _append_options(lines: list[str], options: list[dict], width: int) -> None:
    _append_params(lines, options, width)


def _append_params(lines: list[str], params: list[dict], width: int) -> None:
    for param in params:
        opts = param.get("opts") or [param["name"]]
        label = ", ".join(opts)
        param_type = param.get("type")
        choices = param.get("choices")
        if choices:
            param_type = "|".join(choices)
        if param_type and not param.get("is_flag"):
            label = f"{label} <{param_type}>"
        help_text = str(param.get("help", ""))
        default = param.get("default")
        if default is not None:
            help_text = f"{help_text} Default: {default}.".strip()
        _append_wrapped(lines, label, help_text, width)


def _append_wrapped(lines: list[str], label: str, help_text: str, width: int) -> None:
    head = f"  {label}"
    if not help_text:
        lines.append(head)
        return
    pad = max(28, min(42, len(head) + 2))
    if len(head) >= pad - 1:
        lines.append(head)
        lines.extend(
            textwrap.wrap(
                help_text,
                width=max(60, width),
                initial_indent=" " * 4,
                subsequent_indent=" " * 4,
                break_long_words=False,
            )
        )
        return
    first = head.ljust(pad) + help_text
    wrapped = textwrap.wrap(
        first,
        width=max(60, width),
        subsequent_indent=" " * pad,
        break_long_words=False,
    )
    lines.extend(wrapped or [first])
