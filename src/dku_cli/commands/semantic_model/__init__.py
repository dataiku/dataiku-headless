"""Semantic-model command package."""

from __future__ import annotations

from ._common import app
from . import core as _core  # noqa: F401
from . import versions as _versions  # noqa: F401
from . import structure as _structure  # noqa: F401
from . import collections as _collections  # noqa: F401

__all__ = ["app"]
