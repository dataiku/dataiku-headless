"""Shared test helpers usable from every test package.

Importable as ``from tests.helpers import strip_ansi`` because ``tests`` is a
package (``tests/__init__.py`` exists); no sys.path manipulation required.
"""

from __future__ import annotations

import re

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def strip_ansi(text: str) -> str:
    """Strip ANSI SGR escape codes from rich-formatted CLI output."""
    return _ANSI_RE.sub("", text)
