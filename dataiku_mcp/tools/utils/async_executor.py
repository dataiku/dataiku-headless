"""Async executor for running blocking Dataiku API calls."""

import asyncio
import contextvars
from concurrent.futures import ThreadPoolExecutor

from ...config_mcp import DKU_MCP_MAX_COBUILD_WORKERS, DKU_MCP_MAX_WORKERS

_executor = ThreadPoolExecutor(max_workers=DKU_MCP_MAX_WORKERS)
_cobuild_executor = ThreadPoolExecutor(max_workers=DKU_MCP_MAX_COBUILD_WORKERS)


async def run_blocking(func, *args, **kwargs):
    """Run a blocking function in the thread pool executor."""
    loop = asyncio.get_event_loop()
    context = contextvars.copy_context()
    return await loop.run_in_executor(
        _executor,
        context.run,
        lambda: func(*args, **kwargs),
    )


async def run_cobuild_blocking(func, *args, **kwargs):
    """Run a blocking Cobuild SDK call without occupying the general executor."""
    loop = asyncio.get_event_loop()
    context = contextvars.copy_context()
    return await loop.run_in_executor(
        _cobuild_executor,
        context.run,
        lambda: func(*args, **kwargs),
    )
