"""Smoke tests: the package imports cleanly and exposes its public surface.

These intentionally avoid any live Dataiku DSS connection — importing the
package must work without credentials (``config.py`` defaults every setting to
an empty value), so CI can run them on a bare runner.

``test_registered_tool_surface`` is the curated-surface guard: dataiku-headless
exposes ONE fixed supervisor tool set (no exposure modes). Any tool added to or
removed from that set — other than the concurrently-owned cobuild module — must
update ``EXPECTED_NON_COBUILD`` here, on purpose.
"""

import asyncio
import importlib.metadata

import dataiku_mcp

# The complete, transport-agnostic non-cobuild supervisor surface. Transport
# gating (applied at import time in ``dataiku_mcp/__init__.py``) removes a small
# number of these depending on ``DKU_MCP_TRANSPORT``; the test accounts for it.
EXPECTED_NON_COBUILD = frozenset(
    {
        # projects (6)
        "list_projects",
        "count_projects",
        "create_project",
        "get_project_metadata",
        "get_project_variables",
        "get_project_overview",
        # project audit (1)
        "audit_project",
        # datasets (7)
        "list_datasets",
        "get_dataset_info",
        "get_dataset_sample",
        "get_dataset_metrics",
        "get_dataset_profile",
        "create_upload_dataset",
        "create_upload_dataset_from_rows",
        # recipes (2)
        "list_recipes",
        "get_recipe_settings",
        # flow (3)
        "get_flow_graph",
        "list_flow_zones",
        "get_flow_object_metadata",
        # connections (3)
        "list_connections",
        "get_connection_info",
        "test_connection",
        # scenarios (4)
        "list_scenarios",
        "get_scenario_settings",
        "get_scenario_run_history",
        "run_scenario",
        # jobs (7)
        "list_jobs",
        "get_job_status",
        "get_job_log",
        "wait_for_job",
        "get_future_status",
        "build_datasets",
        "run_recipe",
        # managed folders (4)
        "list_managed_folders",
        "get_managed_folder_contents",
        "get_managed_folder_info",
        "upload_file_to_managed_folder",
        # code environments (1)
        "list_code_envs",
        # data collections (2)
        "list_data_collections",
        "list_data_collection_objects",
        # cross-project sharing (1)
        "list_shared_objects",
        # project libraries (3)
        "list_project_library",
        "read_project_library_file",
        "write_project_library_file",
        # data quality (2)
        "list_data_quality_rules",
        "get_data_quality_status",
        # agents (1)
        "list_agents",
        # llms (1)
        "list_llms",
        # machine learning (2)
        "list_ml_analyses",
        "list_saved_models",
        # instances (3)
        "list_instances",
        "switch_instance",
        "get_current_instance",
    }
)

# The cobuild module's tool surface is exactly these five tools. The concurrent
# cobuild agent may change tool *signatures* (e.g. making confirmation_id
# required) but the name-level surface asserted here must stay exact.
KNOWN_COBUILD = frozenset(
    {
        "start_cobuild_conversation",
        "send_cobuild_message",
        "answer_cobuild_confirmation",
        "list_cobuild_conversations",
        "get_cobuild_turn_status",
    }
)


def _expected_non_cobuild_for_transport() -> set[str]:
    expected = set(EXPECTED_NON_COBUILD)
    if dataiku_mcp.transport == "stdio":
        expected.discard("create_upload_dataset_from_rows")
    elif dataiku_mcp.transport == "streamable-http":
        # Every server-filesystem-reading tool is dropped over HTTP, plus the
        # stdio-only multi-instance controls.
        expected -= {
            "create_upload_dataset",
            "upload_file_to_managed_folder",
            "write_project_library_file",
            "switch_instance",
            "list_instances",
        }
    return expected


def _split_registered_tools() -> tuple[set[str], set[str]]:
    tools = asyncio.run(dataiku_mcp.mcp.list_tools())
    cobuild_names: set[str] = set()
    non_cobuild_names: set[str] = set()
    for tool in tools:
        fn = getattr(tool, "fn", None)
        module = getattr(fn, "__module__", "") or ""
        if module.endswith(".cobuild"):
            cobuild_names.add(tool.name)
        else:
            non_cobuild_names.add(tool.name)
    return cobuild_names, non_cobuild_names


def test_public_api():
    assert dataiku_mcp.__all__ == ["mcp", "run_server"]
    assert callable(dataiku_mcp.run_server)


def test_mcp_server_initialized():
    # Importing the package registers every tool module against this server.
    assert dataiku_mcp.mcp.name == "Dataiku DSS"


def test_distribution_version_is_resolvable():
    # The version is the commitizen / PEP 621 source of truth in pyproject.toml;
    # this asserts the installed distribution metadata actually resolves it, so
    # CI runs against a properly built/installed package rather than a bare tree.
    version = importlib.metadata.version("dataiku-headless")
    assert version and version[0].isdigit()


def test_registered_tool_surface():
    cobuild_names, non_cobuild_names = _split_registered_tools()
    expected = _expected_non_cobuild_for_transport()

    assert non_cobuild_names == expected, (
        "Registered non-cobuild tool surface drifted from the curated allow-list.\n"
        f"Unexpected (present, not allowed): {sorted(non_cobuild_names - expected)}\n"
        f"Missing (allowed, not present):    {sorted(expected - non_cobuild_names)}"
    )
    assert cobuild_names == KNOWN_COBUILD, (
        "Registered cobuild tool surface drifted from the expected five-tool set.\n"
        f"Unexpected (present, not expected): {sorted(cobuild_names - KNOWN_COBUILD)}\n"
        f"Missing (expected, not present):    {sorted(KNOWN_COBUILD - cobuild_names)}"
    )
