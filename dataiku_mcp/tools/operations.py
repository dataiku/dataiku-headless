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

"""Stable discovery and effect-separated dispatch for audited operations."""

import json
from typing import Literal

from ..config import request
from ..instance_policy import V2_GENERAL_API_OPERATIONS
from ..operation_registry import (
    get_operation,
    get_operations,
    require_operation,
    require_transport,
)
from ..server import DSS_INDEPENDENT_TOOL_TAG, mcp
from .utils.serialization import compact_json


@mcp.tool(
    meta=V2_GENERAL_API_OPERATIONS,
    title="Search Operations",
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "openWorldHint": False,
    },
    tags={DSS_INDEPENDENT_TOOL_TAG},
)
async def search_operations(
    query: str = "",
    domain: Literal["deployer", "govern", "agent-management"] | None = None,
    effect: Literal["read", "write"] | None = None,
    limit: int = 10,
    offset: int = 0,
) -> str:
    """Find relevant operations for the selected instance before loading argument schemas."""
    if not 1 <= limit <= 50:
        raise ValueError("limit must be between 1 and 50")
    if offset < 0:
        raise ValueError("offset must be non-negative")
    instance = request.get_pinned_instance()
    words = query.casefold().split()
    matches = [
        op
        for op in get_operations().values()
        if instance.instance_type in op.allowed_instance_types
        and (domain is None or domain == op.domain)
        and (effect is None or effect == op.effect)
        and all(
            word in (op.operation_id + " " + op.description).casefold()
            for word in words
        )
    ]
    return compact_json(
        {
            "instance_name": instance.name,
            "server_support": "unknown",
            "total": len(matches),
            "operations": [op.summary() for op in matches[offset : offset + limit]],
            "truncated": len(matches) > offset + limit,
            "next_offset": offset + limit if len(matches) > offset + limit else None,
        }
    )


@mcp.tool(
    meta=V2_GENERAL_API_OPERATIONS,
    title="Describe Operation",
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "openWorldHint": False,
    },
    tags={DSS_INDEPENDENT_TOOL_TAG},
)
async def describe_operation(operation_id: str) -> str:
    """Load one operation's input schema, example, policy and backend requirements."""
    operation = get_operation(operation_id)
    instance = request.get_pinned_instance()
    return compact_json(
        {
            **operation.describe(),
            "instance_name": instance.name,
            "allowed_on_selected_instance": instance.instance_type
            in operation.allowed_instance_types,
        }
    )


async def _dispatch(
    operation_id: str,
    arguments: dict,
    effect: Literal["read", "write"],
    expected_instance: str | None,
) -> str:
    instance = request.get_pinned_instance()
    if expected_instance is not None and instance.name != expected_instance:
        raise ValueError(
            "Selected instance changed. Inspect get_current_instance before retrying."
        )
    operation = require_operation(operation_id, effect, instance.instance_type)
    values = operation.validate(arguments)
    require_transport(operation, values, request.is_http_request())
    result = json.loads(await operation.handler(**values))
    return compact_json(
        {"operation_id": operation_id, "instance_name": instance.name, "result": result}
    )


@mcp.tool(
    meta=V2_GENERAL_API_OPERATIONS,
    title="Run Read Operation",
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "openWorldHint": False,
    },
)
async def run_read_operation(
    operation_id: str, arguments: dict, expected_instance: str | None = None
) -> str:
    """Run a catalogued read; expected_instance rejects a stale instance selection."""
    return await _dispatch(operation_id, arguments, "read", expected_instance)


@mcp.tool(
    meta=V2_GENERAL_API_OPERATIONS,
    title="Run Write Operation",
    annotations={
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
async def run_write_operation(
    operation_id: str, arguments: dict, expected_instance: str | None = None
) -> str:
    """Run a catalogued mutation after reviewing its schema, scope and execution effects."""
    return await _dispatch(operation_id, arguments, "write", expected_instance)
