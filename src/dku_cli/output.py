"""Agent-first output. Dense by default; --format json|csv|ids|quiet to override.

Default rendering (no --format):
  - lists  → TSV: one header row of column keys, then rows. Leanest parseable
    shape — headers once, values after, no padding, no truncation.
  - single objects → compact JSON (inherently nested).

Data goes to stdout. Messages, hints, and list titles go to stderr, so stdout
is always safe to pipe. ``quiet`` keeps the data and silences stderr chatter;
``ids`` emits one identifier per line for piping.
"""

from __future__ import annotations

import csv
import io
import json
from collections.abc import Sequence
from typing import Any

from rich.console import Console
from rich.tree import Tree

from dku_cli.brand import ICON

# soft_wrap: never hard-wrap messages at terminal width — wrapped commands
# can't be copy-pasted and break line-based parsing.
# emoji=False: Rich otherwise rewrites :shortcode: sequences — an error
# echoing user input like --mappings 'a:b:c' rendered as 'a🅱c'.
console = Console(soft_wrap=True, emoji=False)
err_console = Console(stderr=True, soft_wrap=True, emoji=False)

_quiet = False
_output_format = "dense"

# "dense" is the implicit default, never a flag value.
OUTPUT_FORMATS = ("json", "csv", "ids", "quiet")


def set_output_format(value: str | None) -> None:
    """Set the invocation-wide output format. None restores the dense default."""
    global _output_format, _quiet
    if value is None:
        _output_format = "dense"
        return
    normalized = value.strip().lower()
    if normalized not in OUTPUT_FORMATS:
        raise ValueError(f"Output format must be one of: {', '.join(OUTPUT_FORMATS)}")
    _output_format = normalized
    if normalized in ("quiet", "ids"):
        _quiet = True


def get_output_format() -> str:
    """Return the active invocation-wide output format."""
    return _output_format


def resolve_output_format() -> str:
    """The format a command should branch on: dense, json, csv, ids, or quiet.

    Dense (and quiet/ids) callers take their lean summary path; ``json``
    callers may emit a richer raw payload.
    """
    return _output_format


def set_quiet(value: bool) -> None:
    """Enable/disable quiet mode (suppresses info/success/warn/hint on stderr)."""
    global _quiet
    _quiet = value


def is_quiet() -> bool:
    """Check if quiet mode is active."""
    return _quiet


def reset_output_modes() -> None:
    """Restore all output-mode globals to their defaults.

    The single authoritative reset — used by the test harness between tests,
    and the right hook for any embedder that runs multiple CLI invocations in
    one process. Adding a new output-mode global? Reset it here, or it WILL
    leak across invocations.
    """
    set_output_format(None)
    set_quiet(False)


def filter_fields(
    data: Sequence[dict[str, Any]], columns: list[str], fields: str | None
) -> tuple[list[dict[str, Any]], list[str]]:
    """Filter data dicts to include only requested fields.

    Returns (filtered_data, filtered_columns).  If *fields* is None or
    empty the original data is returned unchanged.
    """
    if not fields:
        return list(data), columns
    wanted = [f.strip() for f in fields.split(",") if f.strip()]
    filtered: list[dict[str, Any]] = [
        {k: row[k] for k in wanted if k in row} for row in data
    ]
    return filtered, wanted


def render(
    data: Sequence[dict[str, Any]],
    columns: list[str],
    *,
    output_format: str | None = None,
    title: str | None = None,
    headers: dict[str, str] | None = None,
) -> None:
    """Render list-shaped data.

    Args:
        data: List of dicts to display.
        columns: Keys to include, in order.
        output_format: Explicit override; defaults to the invocation format.
        title: Context line (counts, scope) — printed to stderr, never stdout.
        headers: Display name mapping {key: "Display Name"}, used by csv only.
    """
    fmt = output_format or _output_format
    if fmt == "json":
        filtered = [{k: row.get(k, "") for k in columns} for row in data]
        print(json.dumps(filtered, indent=2, default=str))
    elif fmt == "csv":
        _render_delimited(data, columns, headers=headers, delimiter=",")
    elif fmt == "ids":
        for row in data:
            print(str(row.get(columns[0], "")))
    else:
        if title:
            info(title)
        _render_delimited(data, columns, headers=None, delimiter="\t")


def render_raw(data: Any, output_format: str | None = None) -> None:
    """Render a single object: compact JSON by default, indented under --format json."""
    fmt = output_format or _output_format
    if fmt == "json":
        print(json.dumps(data, indent=2, default=str))
    elif isinstance(data, (dict, list)):
        print(json.dumps(data, default=str, separators=(",", ":")))
    else:
        print(str(data))


def _render_delimited(
    data: Sequence[dict[str, Any]],
    columns: list[str],
    *,
    headers: dict[str, str] | None = None,
    delimiter: str,
) -> None:
    headers = headers or {}
    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=delimiter, lineterminator="\n")
    writer.writerow([headers.get(c, c) for c in columns])
    for row in data:
        writer.writerow([str(row.get(c, "")) for c in columns])
    print(buf.getvalue(), end="")


def success(msg: str) -> None:
    if not _quiet:
        err_console.print(f"[green]{ICON}[/green] {msg}")


def error(msg: str) -> None:
    err_console.print(f"[red]{ICON}[/red] {msg}")


def warn(msg: str) -> None:
    if not _quiet:
        err_console.print(f"[yellow]{ICON}[/yellow] {msg}")


def info(msg: str) -> None:
    if not _quiet:
        err_console.print(f"[dim]{msg}[/dim]")


def hint(next_command: str) -> None:
    if not _quiet:
        err_console.print(f"[dim]Next: {next_command}[/dim]")


def emit_created(obj: Any, *, message: str, next_command: str | None = None) -> None:
    """Report a created/mutated object so its id is always machine-readable.

    The object must carry an ``id``. Output to stdout by format:
      - dense   → compact JSON object (pipe-clean; ``| jq -r .id`` works)
      - json    → indented JSON object, nothing else
      - ids     → the bare id line (honors the module's ids contract)
      - quiet   → compact JSON object, no chrome
    The human banner and next-step hint go to stderr and are suppressed under
    json/quiet/ids, keeping the data stream pipe-clean.
    """
    if _output_format == "ids":
        print(obj["id"])
        return
    render_raw(obj)
    if _output_format == "json":
        return
    success(message)
    if next_command:
        hint(next_command)


def print_text(text: str) -> None:
    """Print server-provided text (logs, code) verbatim.

    Disables Rich markup and highlighting: log lines containing brackets
    (e.g. ``[/SUP001_contract.pdf, ...]``) otherwise raise ``MarkupError``
    and hide the real content.
    """
    console.print(text, markup=False, highlight=False)


def render_dag(nodes: dict[str, Any], title: str) -> None:
    """Render a flow DAG as a Rich ASCII tree.

    Traverses from source nodes (no predecessors), color-codes datasets (cyan)
    vs recipes (yellow), and marks already-visited nodes with (↑) to handle
    shared nodes in non-tree DAGs.
    """
    has_predecessor: set[str] = set()
    for node in nodes.values():
        for s in node.get("successors", []):
            has_predecessor.add(s)
    sources = [nid for nid in nodes if nid not in has_predecessor]

    visited: set[str] = set()

    def add_branch(parent: Tree, node_id: str) -> None:
        node = nodes.get(node_id, {})
        ntype = node.get("type", "?")
        ref = node.get("ref", node_id)
        color = "cyan" if ntype == "DATASET" else "yellow"
        already = node_id in visited
        label = f"[{color}][{ntype}][/{color}] {ref}" + (
            " [dim](↑)[/dim]" if already else ""
        )
        branch = parent.add(label)
        if not already:
            visited.add(node_id)
            for s in node.get("successors", []):
                add_branch(branch, s)

    root = Tree(f"[bold]{title}[/bold]")
    for src in sources:
        add_branch(root, src)
    console.print(root)
