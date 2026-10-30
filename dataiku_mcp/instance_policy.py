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

"""Declared instance policies, enforced before acquiring backend credentials."""

from typing import get_args

from .config.models import InstanceType

# Types served by DSSClient; Govern uses its own SDK client.
SUPPORTED_DSS_INSTANCE_TYPES = frozenset(
    {"design", "automation", "agent-management", "deployer"}
)

# These are @mcp.tool metadata policies. V1 tools expose individual actions;
# v2 tools discover and execute a fixed SDK operation catalog. Project authoring
# still routes through Cobuild and its fixed direct exceptions.
V1_EXPLICIT_TOOL_PROJECT_READS = {
    "allowed_instance_types": ["design", "agent-management", "automation"]
}
V1_EXPLICIT_TOOL_PROJECT_EXECUTION = {
    "allowed_instance_types": ["design", "agent-management", "automation"]
}
V1_EXPLICIT_TOOL_ADMIN = {
    "allowed_instance_types": ["design", "agent-management", "automation"]
}
V1_EXPLICIT_TOOL_PROJECT_EDITS = {
    "allowed_instance_types": ["design", "agent-management"]
}
V2_GENERAL_API_OPERATIONS = {
    "allowed_instance_types": ["agent-management", "deployer", "govern"]
}
INSTANCE_MANAGEMENT = {"allowed_instance_types": list(get_args(InstanceType))}


def require_instance_type(
    tool_name: str, instance_type: InstanceType | None, metadata: dict | None
) -> None:
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
        or len(allowed) != len(set(allowed))
    ):
        raise ValueError(f"Tool '{tool_name}' has an invalid instance-type policy.")
    # Only the connection-management group can run before a profile is selected.
    if instance_type is None and metadata == INSTANCE_MANAGEMENT:
        return
    if instance_type not in allowed:
        raise ValueError(
            f"Tool '{tool_name}' is unavailable for instance type '{instance_type}'. Allowed types: {', '.join(allowed)}. Use switch_instance to choose a supported instance."
        )
