"""Project Standards command package."""

from __future__ import annotations

from . import checks as _checks  # noqa: F401
from . import projects as _projects  # noqa: F401
from . import scope_mutations as _scope_mutations  # noqa: F401
from . import scopes as _scopes  # noqa: F401
from ._common import app

__all__ = ["app"]
