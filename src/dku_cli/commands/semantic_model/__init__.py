"""Semantic-model command package."""

from __future__ import annotations

from . import collections as _collections  # noqa: F401
from . import core as _core  # noqa: F401
from . import structure as _structure  # noqa: F401
from . import versions as _versions  # noqa: F401
from ._common import app

__all__ = ["app"]
