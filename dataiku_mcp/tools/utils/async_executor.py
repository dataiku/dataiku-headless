"""Async executor for running blocking Dataiku API calls."""

import asyncio
import contextvars
from concurrent.futures import ThreadPoolExecutor

from ...config_mcp import DKU_MCP_MAX_WORKERS

_executor = ThreadPoolExecutor(max_workers=DKU_MCP_MAX_WORKERS)


async def run_blocking(func, *args, **kwargs):
    """Run a blocking function in the thread pool executor.

    FastMCP keeps request-scoped state — including the incoming HTTP request and
    thus the ``Authorization: Bearer`` token used for streamable-http auth — in
    ``contextvars.ContextVar``s. Threads spawned by ``run_in_executor`` do NOT
    inherit the caller's ContextVars, so a blocking call that later reads the
    request (e.g. ``get_http_request``) would see nothing and bearer auth would
    fail. We snapshot the current context here (still inside the request) and run
    the callable inside it in the worker thread.
    """
    loop = asyncio.get_event_loop()
    parent_context = contextvars.copy_context()
    return await loop.run_in_executor(
        _executor,
        lambda: parent_context.run(func, *args, **kwargs),
    )
