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

"""Declared instance-type policies for MCP dispatch."""

from typing import get_args

from .config.models import InstanceType


SUPPORTED_DSS_INSTANCE_TYPES = frozenset({"design", "automation", "agent-management"})
ALL_INSTANCE_TOOL_META = {"allowed_instance_types": list(get_args(InstanceType))}
DSS_TOOL_META = {"allowed_instance_types": sorted(SUPPORTED_DSS_INSTANCE_TYPES)}
PROJECT_EDIT_TOOL_META = {"allowed_instance_types": ["design", "agent-management"]}
INSTANCE_CONTROL_TOOLS = frozenset(
    {"list_instances", "switch_instance", "configure_instance", "delete_instance"}
)


def require_instance_type(
    tool_name: str, instance_type: InstanceType | None, metadata: dict | None
) -> None:
    """Reject missing policy declarations and calls on unsupported node types."""
    allowed = (
        metadata.get("allowed_instance_types") if isinstance(metadata, dict) else None
    )
    if (
        not isinstance(allowed, list)
        or not allowed
        or any(
            not isinstance(value, str) or value not in get_args(InstanceType)
            for value in allowed
        )
        or len(set(allowed)) != len(allowed)
    ):
        raise ValueError(f"Tool '{tool_name}' has an invalid instance-type policy.")
    if instance_type is None and tool_name in INSTANCE_CONTROL_TOOLS:
        return
    if instance_type not in allowed:
        raise ValueError(
            f"Tool '{tool_name}' is unavailable for instance type '{instance_type}'. "
            f"Allowed types: {', '.join(allowed)}. Use switch_instance to choose a supported instance."
        )
