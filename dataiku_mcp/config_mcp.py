import os
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("dataiku-mcp")

DKU_MCP_MAX_WORKERS = int(os.environ.get("DKU_MCP_MAX_WORKERS", "4"))
# Bounds parallel blocking Cobuild calls; additional retained turns queue locally.
DKU_MCP_MAX_COBUILD_WORKERS = int(
    os.environ.get("DKU_MCP_MAX_COBUILD_WORKERS", "4")
)
