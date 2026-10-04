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

"""Request-scoped instance selection for local tool calls."""

from contextvars import ContextVar, Token

from . import stdio
from .models import DSSInstance


_pinned_instance: ContextVar[DSSInstance | None] = ContextVar(
    "dataiku_mcp_pinned_instance", default=None
)


def get_instances() -> dict[str, DSSInstance]:
    """Return the configured local instances."""
    return stdio.get_instances()


def pin_current_instance() -> Token:
    """Snapshot the active instance for the current MCP request."""
    return _pinned_instance.set(stdio.get_current_instance())


def reset_pinned_instance(token: Token) -> None:
    _pinned_instance.reset(token)


def get_pinned_instance() -> DSSInstance:
    """Return the pinned instance or agent guidance for selecting one."""
    pinned_instance = _pinned_instance.get()
    if pinned_instance is not None:
        return pinned_instance

    if not get_instances():
        raise ValueError("No Dataiku instances are configured. Run configure_instance.")
    raise ValueError(
        "No active Dataiku instance is selected. Run list_instances, then ask "
        "the user which configured instance to switch to, or whether to "
        "configure a new one."
    )


def set_current_instance(name: str) -> dict:
    """Select an instance for later local tool calls."""
    instances = get_instances()
    if name not in instances:
        raise ValueError(f"Unknown instance '{name}'. Available: {list(instances)}")

    selected = instances[name]
    stdio.set_current_instance(selected)
    return {
        "name": selected.name,
        "url": selected.url,
        "description": selected.description,
    }
