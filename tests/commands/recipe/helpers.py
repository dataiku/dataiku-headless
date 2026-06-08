from __future__ import annotations

from typer.testing import CliRunner

from dku_cli.main import app as app

runner = CliRunner()


def setup_prepare_mock(patch_client, steps=None):
    """Configure mock for prepare recipe tests. Returns (proj, recipe_mock, settings)."""
    proj = patch_client.get_project("PROJ1")
    recipe_mock = proj.get_recipe.return_value
    settings = recipe_mock.get_settings.return_value
    settings.get_recipe_raw_definition.return_value = {
        "type": "shaker",
        "name": "prep1",
    }
    payload = {"steps": list(steps) if steps else []}
    settings.obj_payload = payload
    settings.raw_steps = payload["steps"]
    settings._obj_payload = payload
    return proj, recipe_mock, settings
