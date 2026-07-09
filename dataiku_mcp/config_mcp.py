import os
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("dataiku-mcp")


def _parse_tool_exposure_mode(value: str) -> str:
    mode = value.strip().lower()
    if mode in {"", "full"}:
        return "full"
    if mode == "search":
        return "search"
    raise ValueError(
        f"Invalid DKU_MCP_TOOL_EXPOSURE '{value}'. Allowed values: ['full', 'search']"
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
