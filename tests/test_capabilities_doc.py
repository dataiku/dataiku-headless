# Copyright 2026 Dataiku
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

"""``docs/capabilities.md`` must stay in lockstep with the registered tool surface.

The doc is the user-facing answer to "can Headless do X, and does Cobuild or
Headless do it". Its tool names and total are maintained by hand, so they rot
silently: a renamed tool leaves a name nobody can call, and a new tool is simply
missing. Neither shows up until someone in the field quotes the doc and is wrong.

Only backticked tool names and the headline total are checked. The per-bucket
counts (read / write / execute) are deliberately not: that split is a judgment
call at the edges, and pinning it here would make this test the arbiter of a
debatable taxonomy instead of a drift alarm.

A backticked lowercase word that is not a tool trips
``test_documented_tools_are_registered``. That is intentional: unbacktick it, or
use the real tool name.
"""

import asyncio
import re
from pathlib import Path

import dataiku_mcp

DOC = Path(__file__).resolve().parent.parent / "docs" / "capabilities.md"

# Tool names are lowercase snake_case. Paths and prose keep punctuation or stay
# short, so shape alone separates a tool reference from `uv` or `README.md`.
TOOL_TOKEN = re.compile(r"^[a-z][a-z0-9_]{3,}$")


def _registered_tools() -> set[str]:
    return {tool.name for tool in asyncio.run(dataiku_mcp.mcp.list_tools())}


def _documented_tools() -> set[str]:
    text = DOC.read_text(encoding="utf-8")
    return {
        token for token in re.findall(r"`([^`]+)`", text) if TOOL_TOKEN.match(token)
    }


def test_documented_tools_are_registered():
    unknown = sorted(_documented_tools() - _registered_tools())
    assert not unknown, (
        f"docs/capabilities.md references tools that are not registered: {unknown}. "
        "They were renamed or removed; update the doc so the field is not told "
        "to call something that does not exist."
    )


def test_registered_tools_are_documented():
    undocumented = sorted(_registered_tools() - _documented_tools())
    assert not undocumented, (
        f"docs/capabilities.md is missing registered tools: {undocumented}. Add each "
        "to the table for its area, and refresh the tool total."
    )


def test_documented_tool_total_matches_registered():
    total = re.search(r"\*\*(\d+) tools\*\*", DOC.read_text(encoding="utf-8"))
    assert total, "docs/capabilities.md lost its '**N tools**' headline total"
    assert int(total.group(1)) == len(_registered_tools()), (
        f"docs/capabilities.md says {total.group(1)} tools but "
        f"{len(_registered_tools())} are registered"
    )
