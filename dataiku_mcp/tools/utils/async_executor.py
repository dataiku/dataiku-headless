# Copyright 2026 Dataiku SAS
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

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
