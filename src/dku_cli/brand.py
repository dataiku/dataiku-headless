"""Dataiku-style terminal branding."""

from __future__ import annotations

from dku_cli import __version__

ICON = "◆"
NAME = "dku"
FULL_NAME = "Dataiku Headless"

# Dataiku bird + wordmark — dot-style ASCII art.
LOGO = """\
               ......       ...........                 ...               ...  ...
              .......       ...    ......               ...               ...  ...
            ........        ...       ....   ........ .......  ........   ...  ...   .... ..      ..
           .........        ...        ...  ...   ....  ...   ....  ....  ...  ... .....  ...     ..
         ...........        ...        ...  ..   .....  ...   ...   ....  ...  .......    ...     ..
        ...........         ...        ...  ..........  ...    .........  ...  ......     ...     ..
      ............          ...       ...  ....    ...  ...   ...    ...  ...  .......    ...    ...
    ...... ..........       ............   ....  .....  ..... ...  .....  ...  ...  ....  ..........
   ...     ..........       ..........      ....... ..   ....  ...... ..  ...  ...    ...  .........
 ...
.."""


def print_logo(*, subtitle: str | None = None, dim_logo: bool = False) -> None:
    """Print the Dataiku bird + wordmark logo.

    Uses Rich console for colour output to stderr.
    """
    from rich.console import Console

    con = Console(stderr=True, width=100)
    style = "blue" if not dim_logo else "dim blue"
    for line in LOGO.splitlines():
        con.print(f"[{style}]{line}[/{style}]")
    if subtitle:
        con.print(f"\n  [dim]{subtitle}[/dim]")
    con.print()


def version_string() -> str:
    """Return branded version string: '◆ Dataiku Headless 0.4.1'."""
    return f"{ICON} {FULL_NAME} {__version__}"


def welcome(user: str, url: str, version: str) -> str:
    """Return branded login success message."""
    return f"{ICON} Connected to DSS {version} as {user}"


def status_ok(msg: str) -> str:
    """Return branded OK message."""
    return f"{ICON} {msg}"


def status_err(msg: str) -> str:
    """Return branded error message."""
    return f"{ICON} {msg}"
