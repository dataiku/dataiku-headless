"""Smoke tests plus the fixed tool-surface contract.

These intentionally avoid any live Dataiku DSS connection — importing the
package must work without credentials (``config.py`` defaults every setting to
an empty value), so CI can run them on a bare runner.

The server is stdio-only with one fixed catalog: no transport switch, no
tool-exposure mode, no Cobuild mode. ``EXPECTED_NON_COBUILD`` and
``COBUILD_TOOLS`` below are that catalog. They are the surface contract —
changing the registered tool set means changing this file in the same commit.
"""

import asyncio
import importlib.metadata

import dataiku_mcp

# The five Cobuild conversation tools — the only in-project write path.
COBUILD_TOOLS = frozenset(
    {
        "answer_cobuild_confirmation",
        "get_cobuild_turn_status",
        "list_cobuild_conversations",
        "send_cobuild_message",
        "start_cobuild_conversation",
    }
)

# Every other registered tool: read/inspect surface, the three deterministic
# executions (build_datasets, run_recipe, run_scenario), and the bootstrap
# writes (create_project, create_upload_dataset, upload_file_to_managed_folder,
# write_project_library_file) plus the instance controls.
EXPECTED_NON_COBUILD = frozenset(
    {
        "audit_project",
        "build_datasets",
        "count_projects",
        "create_project",
        "create_upload_dataset",
        "get_connection_info",
        "get_current_instance",
        "get_data_quality_status",
        "get_dataset_info",
        "get_dataset_metrics",
        "get_dataset_profile",
        "get_dataset_sample",
        "get_flow_graph",
        "get_flow_object_metadata",
        "get_future_status",
        "get_job_log",
        "get_job_status",
        "get_managed_folder_contents",
        "get_managed_folder_info",
        "get_object_settings",
        "get_project_metadata",
        "get_project_overview",
        "get_project_variables",
        "get_recipe_settings",
        "get_scenario_run_history",
        "get_scenario_settings",
        "list_agents",
        "list_code_envs",
        "list_connections",
        "list_data_collection_objects",
        "list_data_collections",
        "list_data_quality_rules",
        "list_datasets",
        "list_flow_zones",
        "list_instances",
        "list_jobs",
        "list_llms",
        "list_managed_folders",
        "list_ml_analyses",
        "list_project_library",
        "list_projects",
        "list_recipes",
        "list_saved_models",
        "list_scenarios",
        "list_shared_objects",
        "read_project_library_file",
        "run_recipe",
        "run_scenario",
        "switch_instance",
        "test_connection",
        "upload_file_to_managed_folder",
        "wait_for_job",
        "write_project_library_file",
    }
)

EXPECTED_TOOLS = EXPECTED_NON_COBUILD | COBUILD_TOOLS


def _registered_tool_names() -> set[str]:
    tools = asyncio.run(dataiku_mcp.mcp.list_tools())
    return {tool.name for tool in tools}


def test_public_api():
    assert dataiku_mcp.__all__ == ["mcp", "run_server"]
    assert callable(dataiku_mcp.run_server)


def test_mcp_server_initialized():
    # Importing the package registers every tool module against this server.
    assert dataiku_mcp.mcp.name == "Dataiku DSS"


def test_registered_surface_is_the_fixed_catalog():
    # One fixed, directly visible catalog: the registered set must match the
    # pinned contract exactly — nothing added, hidden, or renamed silently.
    assert _registered_tool_names() == EXPECTED_TOOLS


def test_cobuild_and_non_cobuild_partitions_are_disjoint():
    assert not (EXPECTED_NON_COBUILD & COBUILD_TOOLS)
    assert len(EXPECTED_TOOLS) == len(EXPECTED_NON_COBUILD) + len(COBUILD_TOOLS)


def test_distribution_version_is_resolvable():
    # The version is the commitizen / PEP 621 source of truth in pyproject.toml
    # and what the release workflow diffs to decide whether to publish.
    version = importlib.metadata.version("dataiku-headless")
    assert version and version[0].isdigit()
