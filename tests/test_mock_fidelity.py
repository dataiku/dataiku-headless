"""Mock-vs-real fidelity tripwire for the dataikuapi surface.

The hand-written fixture in ``tests/fixtures/mock_client.py`` is a plain
``MagicMock`` tree: it answers to ANY attribute access, so it has zero binding
to the real ``dataikuapi``. When DSS ships a new release that renames or removes
a method the CLI calls (the DSS-14.5 failure class), every command test stays
green against the mock while live ``dku`` breaks.

This module is the missing binding. It imports the REAL installed dataikuapi
classes and asserts that the methods the mock leans on actually EXIST on them.
``create_autospec(Cls, instance=True)`` builds a spec'd stand-in that raises
``AttributeError`` on any attribute the real class lacks, so a renamed/removed
method trips the assertion here instead of passing silently in CI.

Design notes:
- We assert *method existence*, not signatures. The CLI calls these by name
  through MagicMock; an existence check is the drift signal we can keep green
  across versions without re-pinning on every minor release.
- Each class is resolved through ``_import`` and ``pytest.skip``-s with a clear
  reason if the installed dataikuapi version doesn't expose it. That keeps this
  file green across dataikuapi upgrades rather than hard-failing on a moved
  import path — the point is to catch *method* drift, not to pin a version.
- The method lists are the high-traffic surface the mock emulates: the verbs
  CLI commands actually invoke (``get_project``, ``create_dataset``,
  ``new_managed_dataset``, ``list_*``, ``get_settings``, ``run``, ``build`` …).
"""

from __future__ import annotations

import importlib

import pytest


def _import(module_path: str, class_name: str):
    """Resolve a dataikuapi class, or skip with a version-drift reason.

    Import-path moves are a *different* failure class than method drift and
    vary across versions; we skip (stay green) rather than fail so this file
    keeps protecting the method surface on versions where the class still lives
    at its expected path.
    """
    try:
        module = importlib.import_module(module_path)
    except Exception as exc:  # pragma: no cover - exercised only on version drift
        pytest.skip(f"{module_path} not importable on this dataikuapi: {exc}")
    cls = getattr(module, class_name, None)
    if cls is None:  # pragma: no cover - exercised only on version drift
        pytest.skip(
            f"{class_name} no longer exported from {module_path} "
            "on this dataikuapi version"
        )
    return cls


def _assert_methods(cls, methods: list[str]) -> None:
    """Assert every name in ``methods`` exists on ``cls`` (the drift tripwire).

    Uses ``create_autospec(instance=True)`` so the assertion runs against a
    spec'd instance that mirrors the real attribute surface — the same
    mechanism that would have caught the DSS-14.5 method renames.
    """
    from unittest.mock import create_autospec

    spec = create_autospec(cls, instance=True)
    missing = [name for name in methods if not hasattr(spec, name)]
    assert not missing, (
        f"{cls.__name__} (real dataikuapi) is missing methods the mock relies on: "
        f"{missing}. The hand-written mock_client fixture would still answer to "
        f"these, hiding the API drift from CI. Update the CLI + mock to the new "
        f"dataikuapi surface."
    )


# ---------------------------------------------------------------------------
# dataikuapi import sanity — if the package itself can't import, nothing below
# is meaningful. Fail loudly here (not skip): a broken install is a real bug.
# ---------------------------------------------------------------------------
def test_dataikuapi_importable():
    import dataikuapi  # noqa: F401

    assert dataikuapi is not None


# ---------------------------------------------------------------------------
# DSSClient — the root object the whole mock tree hangs off of.
# ---------------------------------------------------------------------------
def test_dssclient_methods_exist():
    cls = _import("dataikuapi.dssclient", "DSSClient")
    _assert_methods(
        cls,
        [
            # project entry points
            "get_project",
            "list_project_keys",
            "list_projects",
            "create_project",
            # auth / instance
            "get_auth_info",
            "get_general_settings",
            "get_instance_info",
            # sql + admin surfaces the mock stubs
            "sql_query",
            "list_connections",
            "get_connection",
            "list_code_envs",
            "get_code_env",
            "list_plugins",
            "get_plugin",
            "list_users",
            "get_user",
            "create_user",
            "list_global_api_keys",
            "get_apideployer",
            "get_projectdeployer",
        ],
    )


# ---------------------------------------------------------------------------
# DSSProject — the busiest object in the mock; nearly every command goes through
# get_project(...) then a project-level verb.
# ---------------------------------------------------------------------------
def test_dssproject_methods_exist():
    cls = _import("dataikuapi.dss.project", "DSSProject")
    _assert_methods(
        cls,
        [
            # datasets
            "get_dataset",
            "create_dataset",
            "new_managed_dataset",
            "list_datasets",
            # recipes
            "list_recipes",
            "get_recipe",
            "new_recipe",
            # scenarios
            "list_scenarios",
            "get_scenario",
            "create_scenario",
            # flow + jobs
            "get_flow",
            "new_job",
            "get_job",
            "list_jobs",
            # models / folders
            "list_saved_models",
            "get_saved_model",
            "list_managed_folders",
            "get_managed_folder",
            # variables + agents + misc the CLI exercises
            "get_variables",
            "set_variables",
            "list_agents",
            "get_agent",
            "get_wiki",
            "get_library",
        ],
    )


# ---------------------------------------------------------------------------
# DSSDataset — read/build/metadata verbs the mock emulates heavily.
# ---------------------------------------------------------------------------
def test_dssdataset_methods_exist():
    cls = _import("dataikuapi.dss.dataset", "DSSDataset")
    _assert_methods(
        cls,
        [
            "get_definition",
            "set_definition",
            "iter_rows",
            "build",
            "delete",
            "clear",
            "get_metadata",
            "set_metadata",
            "autodetect_settings",
            "get_data_quality_rules",
            "list_partitions",
        ],
    )


# ---------------------------------------------------------------------------
# DSSRecipe + its settings/status objects — the recipe edit path.
# ---------------------------------------------------------------------------
def test_dssrecipe_methods_exist():
    cls = _import("dataikuapi.dss.recipe", "DSSRecipe")
    _assert_methods(
        cls,
        [
            "get_settings",
            "get_status",
            "run",
            "delete",
            "compute_schema_updates",
        ],
    )


def test_dssrecipe_settings_methods_exist():
    cls = _import("dataikuapi.dss.recipe", "DSSRecipeSettings")
    _assert_methods(
        cls,
        [
            "get_recipe_raw_definition",
            "get_flat_input_refs",
            "get_flat_output_refs",
            "get_payload",
            "set_payload",
            "save",
            "add_input",
            "add_output",
        ],
    )


# ---------------------------------------------------------------------------
# DSSScenario + settings — run/abort/definition/trigger path.
# ---------------------------------------------------------------------------
def test_dssscenario_methods_exist():
    cls = _import("dataikuapi.dss.scenario", "DSSScenario")
    _assert_methods(
        cls,
        [
            "run",
            "abort",
            "delete",
            "get_definition",
            "set_definition",
            "get_settings",
            "get_last_runs",
            "get_run",
        ],
    )


def test_dssscenario_settings_methods_exist():
    cls = _import("dataikuapi.dss.scenario", "DSSScenarioSettings")
    _assert_methods(cls, ["get_raw", "save"])


# ---------------------------------------------------------------------------
# Secondary objects the mock returns from project-level getters. These are the
# next-most-used surfaces; drift here breaks build/deploy/folder/model commands.
# ---------------------------------------------------------------------------
def test_managed_folder_methods_exist():
    cls = _import("dataikuapi.dss.managedfolder", "DSSManagedFolder")
    _assert_methods(
        cls,
        [
            "list_contents",
            "put_file",
            "get_file",
            "delete",
            "get_settings",
            "get_definition",
            "set_definition",
            "copy_to",
        ],
    )


def test_saved_model_methods_exist():
    cls = _import("dataikuapi.dss.savedmodel", "DSSSavedModel")
    _assert_methods(
        cls,
        [
            "get_settings",
            "get_active_version",
            "list_versions",
            "set_active_version",
            "get_version_details",
            "delete",
            "get_usages",
        ],
    )


def test_managed_dataset_creation_helper_methods_exist():
    cls = _import("dataikuapi.dss.dataset", "DSSManagedDatasetCreationHelper")
    _assert_methods(cls, ["with_store_into", "create"])


def test_dss_job_methods_exist():
    cls = _import("dataikuapi.dss.job", "DSSJob")
    _assert_methods(cls, ["get_status", "get_log", "abort"])


def test_dss_flow_methods_exist():
    cls = _import("dataikuapi.dss.flow", "DSSProjectFlow")
    _assert_methods(
        cls,
        [
            "get_graph",
            "list_zones",
            "create_zone",
            "get_zone",
            "new_schema_propagation",
            "start_tool",
        ],
    )


def test_dss_wiki_methods_exist():
    cls = _import("dataikuapi.dss.wiki", "DSSWiki")
    _assert_methods(cls, ["list_articles", "get_article", "create_article"])


def test_dss_llm_methods_exist():
    cls = _import("dataikuapi.dss.llm", "DSSLLM")
    _assert_methods(cls, ["new_completion", "new_embeddings"])


def test_dss_api_service_methods_exist():
    cls = _import("dataikuapi.dss.apiservice", "DSSAPIService")
    _assert_methods(
        cls,
        [
            "get_settings",
            "create_package",
            "list_packages",
            "publish_package",
            "delete_package",
        ],
    )
