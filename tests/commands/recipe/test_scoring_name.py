"""Unit tests for scoring-recipe name reconciliation.

DSS auto-names ML scoring recipes ``score_<input>`` server-side, ignoring the
name the creator was given. _reconcile_scoring_name renames the freshly-built
recipe back to the requested name so the schema apply + the agent's follow-up
``recipe run <name>`` target a recipe that exists (otherwise the output stays at
0 columns and the first build fails on a schema incompatibility).
"""

from __future__ import annotations

from dku_cli.commands.recipe._common import _reconcile_scoring_name


class _FakeRecipe:
    def __init__(self, name: str):
        self.recipe_name = name
        self.renamed_to: str | None = None

    def rename(self, new_name: str) -> None:
        self.renamed_to = new_name
        self.recipe_name = new_name


def test_reconcile_renames_when_dss_autonames():
    # DSS named it 'score_orders'; the agent asked for 'score_anom'.
    recipe = _FakeRecipe("score_orders")
    assert _reconcile_scoring_name(recipe, "score_anom") == "score_anom"
    assert recipe.renamed_to == "score_anom"


def test_reconcile_noop_when_name_matches():
    recipe = _FakeRecipe("score_anom")
    assert _reconcile_scoring_name(recipe, "score_anom") == "score_anom"
    assert recipe.renamed_to is None


def test_reconcile_falls_back_to_real_name_when_rename_fails():
    class _Boom(_FakeRecipe):
        def rename(self, new_name: str) -> None:
            raise RuntimeError("rename blocked")

    recipe = _Boom("score_orders")
    # Cannot rename → callers must use DSS's real name, not the requested one.
    assert _reconcile_scoring_name(recipe, "score_anom") == "score_orders"


def test_reconcile_handles_name_attribute_fallback():
    # Some handles expose .name instead of .recipe_name.
    class _NameOnly:
        def __init__(self):
            self.name = "score_orders"
            self.renamed_to = None

        def rename(self, new_name):
            self.renamed_to = new_name

    recipe = _NameOnly()
    assert _reconcile_scoring_name(recipe, "score_anom") == "score_anom"
    assert recipe.renamed_to == "score_anom"
