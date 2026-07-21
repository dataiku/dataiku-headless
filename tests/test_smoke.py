"""Smoke tests: the package imports cleanly and exposes its public surface.

These intentionally avoid any live Dataiku DSS connection — importing the
package must work without credentials (``config.py`` defaults every setting to
an empty value), so CI can run them on a bare runner.
"""

import asyncio
import importlib.metadata

import dataiku_mcp


# The catalog is a product contract, not an incidental result of imports. Add,
# remove, or rename a tool here only after documenting the review decision in
# TOOL_SURFACE_DECISIONS.md. This transport-agnostic set includes the HTTP-only
# row upload; the default stdio registration test accounts for that one delta.
EXPECTED_NON_COBUILD = {
    "audit_project",
    "build_datasets",
    "count_projects",
    "create_project",
    "create_upload_dataset",
    "get_agent_review_run_results",
    "get_connection_info",
    "get_current_instance",
    "get_data_quality_rule",
    "get_data_quality_rule_history",
    "get_data_quality_rule_results",
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
    "get_llm_info",
    "get_managed_folder_contents",
    "get_managed_folder_info",
    "get_ml_analysis_summary",
    "get_ml_model_details",
    "get_object_settings",
    "get_project_metadata",
    "get_project_overview",
    "get_project_variables",
    "get_recipe_settings",
    "get_scenario_run_history",
    "get_scenario_settings",
    "get_webapp_state",
    "list_agent_review_runs",
    "list_agent_review_tests",
    "list_agent_reviews",
    "list_agent_tools",
    "list_agents",
    "list_code_envs",
    "list_connections",
    "list_dashboards",
    "list_data_collection_objects",
    "list_data_collections",
    "list_data_quality_rules",
    "list_datasets",
    "list_evaluation_stores",
    "list_flow_zones",
    "list_insights",
    "list_instances",
    "list_jobs",
    "list_knowledge_banks",
    "list_llms",
    "list_managed_folders",
    "list_messaging_channels",
    "list_ml_analyses",
    "list_ml_analysis_models",
    "list_project_library",
    "list_projects",
    "list_recipes",
    "list_retrieval_augmented_llms",
    "list_saved_models",
    "list_scenarios",
    "list_semantic_models",
    "list_shared_objects",
    "list_webapps",
    "list_wiki_articles",
    "read_project_library_file",
    "run_recipe",
    "run_scenario",
    "search_knowledge_bank",
    "search_project_library",
    "switch_instance",
    "test_connection",
    "upload_file_to_managed_folder",
    "create_upload_dataset_from_rows",
    "validate_project_library_file",
    "wait_for_job",
    "write_project_library_file",
}

KNOWN_COBUILD = {
    "answer_cobuild_confirmation",
    "get_cobuild_turn_status",
    "list_cobuild_conversations",
    "send_cobuild_message",
    "start_cobuild_conversation",
}


def test_public_api():
    assert dataiku_mcp.__all__ == ["mcp", "run_server"]
    assert callable(dataiku_mcp.run_server)


def test_mcp_server_initialized():
    # Importing the package registers every tool module against this server.
    assert dataiku_mcp.mcp.name == "Dataiku DSS"


def test_distribution_version_is_resolvable():
    # The version is the commitizen / PEP 621 source of truth in pyproject.toml
    # and what the release workflow diffs to decide whether to publish.
    version = importlib.metadata.version("dataiku-headless")
    assert version and version[0].isdigit()


def test_registered_tool_catalog_matches_reviewed_allowlist():
    tools = asyncio.run(dataiku_mcp.mcp.list_tools())
    by_name = {tool.name: tool for tool in tools}
    cobuild = {
        name
        for name, tool in by_name.items()
        if tool.fn.__module__ == "dataiku_mcp.tools.cobuild"
    }
    non_cobuild = set(by_name) - cobuild

    assert cobuild == KNOWN_COBUILD
    # stdio deliberately omits only the remote row-upload tool. The complete
    # stdio/HTTP delta is also tested in subprocesses by test_fixed_surface.py.
    assert non_cobuild | {"create_upload_dataset_from_rows"} == EXPECTED_NON_COBUILD
    assert "create_upload_dataset_from_rows" not in non_cobuild
