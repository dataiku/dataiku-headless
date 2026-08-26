"""Shared executors for blocking Dataiku and Cobuild operations."""

import asyncio
import contextvars
import os
from concurrent.futures import ThreadPoolExecutor

_executor = ThreadPoolExecutor(
    max_workers=int(os.environ.get("DKU_MCP_MAX_WORKERS", "4"))
)
# Bounds parallel blocking Cobuild calls; additional retained turns queue locally.
_cobuild_executor = ThreadPoolExecutor(
    max_workers=int(os.environ.get("DKU_MCP_MAX_COBUILD_WORKERS", "4"))
)


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
