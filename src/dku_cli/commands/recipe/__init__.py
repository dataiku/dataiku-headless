"""dku recipe command package."""

from __future__ import annotations

from typing import TYPE_CHECKING

from . import (  # noqa: F401
    core,
    genai_embed,
    genai_eval,
    genai_more,
    lint,
    prepare_steps,
    schema,
    settings,
    visual_aggregation,
    visual_code,
    visual_io,
    visual_joins,
    visual_pivot_sampling,
    visual_split_topn,
    visual_window,
)
from ._common import app

if TYPE_CHECKING:
    from dataikuapi.dss.recipe import FuzzyJoinRecipeCreator, GeoJoinRecipeCreator

__all__ = ["FuzzyJoinRecipeCreator", "GeoJoinRecipeCreator", "app"]

# Lazily surface the two dataikuapi recipe creators that DSSProject.new_recipe()
# does not dispatch (visual_joins.py reaches for them as attributes on this
# package). Deferring keeps `import dku_cli.main` from pulling in dataikuapi.
_LAZY_CREATORS = {"FuzzyJoinRecipeCreator", "GeoJoinRecipeCreator"}


def __getattr__(name: str):
    if name in _LAZY_CREATORS:
        from dataikuapi.dss import recipe as _recipe

        return getattr(_recipe, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
