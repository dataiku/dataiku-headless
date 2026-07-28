"""Contract tests for the fixed MCP tool surface."""

import asyncio
from collections import defaultdict

import pytest

import dataiku_mcp


EXPECTED_TOOLS_BY_MODULE = {
    "agent_reviews": frozenset(
        {
            "get_agent_review",
            "get_agent_review_run_results",
            "list_agent_review_runs",
            "list_agent_review_tests",
            "list_agent_reviews",
        }
    ),
    "agents": frozenset(
        {
            "get_agent_settings",
            "get_agent_tool_settings",
            "list_agent_tools",
            "list_agent_versions",
            "list_agents",
        }
    ),
    "cobuild": frozenset(
        {
            "answer_cobuild_confirmation",
            "list_cobuild_conversations",
            "send_cobuild_message",
            "start_cobuild_conversation",
        }
    ),
    "code_environments": frozenset({"list_code_envs"}),
    "connections": frozenset(
        {"get_connection_info", "list_connections", "test_connection"}
    ),
    "cross_project_sharing": frozenset({"list_shared_objects"}),
    "dashboards": frozenset({"get_dashboard_settings", "list_dashboards"}),
    "data_collections": frozenset(
        {"list_data_collection_objects", "list_data_collections"}
    ),
    "data_quality": frozenset(
        {
            "get_data_quality_rule",
            "get_data_quality_rule_history",
            "get_data_quality_rule_results",
            "get_data_quality_status",
            "list_data_quality_rules",
        }
    ),
    "datasets": frozenset(
        {
            "create_upload_dataset",
            "get_dataset_column_descriptions",
            "get_dataset_info",
            "get_dataset_metrics",
            "get_dataset_profile",
            "get_dataset_sample",
            "list_datasets",
        }
    ),
    "evaluation_stores": frozenset(
        {"get_evaluation_store_details", "list_evaluation_stores"}
    ),
    "flow": frozenset(
        {
            "get_flow_items_in_traversal_order",
            "get_flow_object_metadata",
            "list_flow_zones",
        }
    ),
    "insights": frozenset({"get_insight_settings", "list_insights"}),
    "instances": frozenset(
        {
            "configure_instance",
            "delete_instance",
            "get_current_instance",
            "list_instances",
            "switch_instance",
        }
    ),
    "jobs": frozenset(
        {
            "build_datasets",
            "get_future_status",
            "get_job_log",
            "get_job_status",
            "list_jobs",
            "run_recipe",
            "wait_for_job",
        }
    ),
    "llms_and_knowledge_banks": frozenset(
        {
            "get_knowledge_bank_settings",
            "get_llm_info",
            "get_retrieval_augmented_llm_settings",
            "list_knowledge_banks",
            "list_llms",
            "list_retrieval_augmented_llms",
            "search_knowledge_bank",
        }
    ),
    "machine_learning.analyses": frozenset(
        {
            "get_ml_analysis_settings",
            "get_ml_analysis_summary",
            "get_ml_model_details",
            "list_ml_analyses",
            "list_ml_analysis_models",
        }
    ),
    "machine_learning.saved_models": frozenset(
        {
            "get_saved_model_version_details",
            "list_saved_model_versions",
            "list_saved_models",
        }
    ),
    "managed_folders": frozenset(
        {
            "create_managed_folder",
            "get_managed_folder_contents",
            "get_managed_folder_info",
            "list_managed_folders",
            "upload_file_to_managed_folder",
        }
    ),
    "project_folders": frozenset(
        {
            "create_project_folder",
            "delete_project_folder",
            "get_project_folder",
            "list_project_folders",
            "move_project_to_folder",
        }
    ),
    "project_libraries": frozenset(
        {
            "list_project_library",
            "read_project_library_file",
            "search_project_library",
            "validate_project_library_file",
            "write_project_library_file",
        }
    ),
    "projects": frozenset(
        {
            "count_projects",
            "create_project",
            "get_project_metadata",
            "get_project_variables",
            "set_project_variables",
            "list_projects",
        }
    ),
    "recipes": frozenset({"get_recipe_settings", "list_recipes"}),
    "scenarios": frozenset(
        {
            "get_scenario_run_history",
            "get_scenario_settings",
            "list_messaging_channels",
            "list_scenarios",
            "run_scenario",
        }
    ),
    "semantic_models": frozenset(
        {"get_semantic_model_version_settings", "list_semantic_models"}
    ),
    "webapps": frozenset({"get_webapp_settings", "get_webapp_state", "list_webapps"}),
    "wikis": frozenset({"get_wiki_article", "list_wiki_articles"}),
}


@pytest.fixture(scope="module")
def registered_tools_by_module() -> dict[str, frozenset[str]]:
    tools_by_module = defaultdict(set)
    for tool in asyncio.run(dataiku_mcp.mcp.list_tools()):
        module = tool.fn.__module__.removeprefix("dataiku_mcp.tools.")
        tools_by_module[module].add(tool.name)
    return {
        module: frozenset(tool_names) for module, tool_names in tools_by_module.items()
    }


def test_registered_tool_modules_are_fixed(registered_tools_by_module):
    assert registered_tools_by_module.keys() == EXPECTED_TOOLS_BY_MODULE.keys()


@pytest.mark.parametrize("module", EXPECTED_TOOLS_BY_MODULE)
def test_registered_tools_are_fixed_for_module(module, registered_tools_by_module):
    assert registered_tools_by_module[module] == EXPECTED_TOOLS_BY_MODULE[module]
