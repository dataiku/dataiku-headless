"""Async executor for running blocking Dataiku API calls."""

import asyncio
from concurrent.futures import ThreadPoolExecutor

from ...config_mcp import DKU_MCP_MAX_WORKERS

_executor = ThreadPoolExecutor(max_workers=DKU_MCP_MAX_WORKERS)


async def run_blocking(func, *args, **kwargs):
    """Run a blocking function in the thread pool executor."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        _executor,
        lambda: func(*args, **kwargs),
    )
