import os
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("dataiku-mcp")

FULL_COBUILD_DISABLED_TOOLS = frozenset(
    {
        "get_agent_review_run_results",
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
        "list_dashboards",
        "list_data_quality_rules",
        "list_datasets",
        "list_evaluation_stores",
        "list_flow_zones",
        "list_insights",
        "list_jobs",
        "list_knowledge_banks",
        "list_llms",
        "list_managed_folders",
        "list_ml_analyses",
        "list_ml_analysis_models",
        "list_project_library",
        "list_recipes",
        "list_retrieval_augmented_llms",
        "list_saved_models",
        "list_scenarios",
        "list_semantic_models",
        "list_webapps",
        "list_wiki_articles",
        "read_project_library_file",
        "search_knowledge_bank",
        "wait_for_job",
    }
)


def _parse_tool_exposure_mode(value: str) -> str:
    mode = value.strip().lower()
    if mode in {"", "full"}:
        return "full"
    if mode == "search":
        return "search"
    raise ValueError(
        f"Invalid DKU_MCP_TOOL_EXPOSURE '{value}'. Allowed values: ['full', 'search']"
    )


def _parse_cobuild_mode(value: str) -> str:
    mode = value.strip().upper()
    if mode in {"", "CREATE_ONLY"}:
        return "CREATE_ONLY"
    if mode == "FULL":
        return "FULL"
    raise ValueError(
        f"Invalid DKU_MCP_COBUILD_MODE '{value}'. Allowed values: ['FULL', 'CREATE_ONLY']"
    )


def _parse_positive_int(value: str, env_name: str, default: int) -> int:
    stripped = value.strip()
    if not stripped:
        return default

    parsed = int(stripped)
    if parsed <= 0:
        raise ValueError(f"{env_name} must be a positive integer, got '{value}'")
    return parsed


def _parse_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


DKU_MCP_MAX_WORKERS = int(os.environ.get("DKU_MCP_MAX_WORKERS", "4"))
DKU_MCP_TRANSPORT = os.environ.get("DKU_MCP_TRANSPORT", "stdio")
DKU_MCP_COBUILD_MODE = _parse_cobuild_mode(
    os.environ.get("DKU_MCP_COBUILD_MODE", "CREATE_ONLY")
)
DKU_MCP_TOOL_EXPOSURE = _parse_tool_exposure_mode(
    os.environ.get("DKU_MCP_TOOL_EXPOSURE", "full")
)
DKU_MCP_SEARCH_MAX_RESULTS = _parse_positive_int(
    os.environ.get("DKU_MCP_SEARCH_MAX_RESULTS", ""),
    "DKU_MCP_SEARCH_MAX_RESULTS",
    5,
)
DKU_MCP_SEARCH_ALWAYS_VISIBLE = _parse_csv(
    os.environ.get("DKU_MCP_SEARCH_ALWAYS_VISIBLE", "")
)
