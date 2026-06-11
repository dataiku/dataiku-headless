"""Shared Typer option aliases for command modules."""

from __future__ import annotations

from typing import Annotated

import typer

PROJECT_HELP = "Project key"
YES_HELP = "Confirm destructive action"

ProjectOption = Annotated[
    str | None,
    typer.Option("--project", "-P", help=PROJECT_HELP),
]
YesOption = Annotated[
    bool,
    typer.Option("--yes", "-y", help=YES_HELP),
]
