"""Trace coherence: does a profile only use the tool surface it was granted?

The sandbox image guarantees most of this by construction (no repo, no skills,
no .env baked; DSS creds withheld from MCP profiles; skills copied in only when
granted). This is the trace-level sanity net on top of that — it flags a run
where the agent reached for a surface its profile was not meant to have, which
is what makes a cross-profile comparison fair.
"""

from __future__ import annotations

import re

_DSSCLIENT = re.compile(r"DSSClient\s*\(")
_DKU = re.compile(r'(?:^|[\n;&|"]|\s)dku\s+[a-z]')
_DOTENV = re.compile(
    r"(?:cat|source|\.|less|more|head|tail|grep\b[^\n]*?)\s+\S*\.env(?:\b|/)"
)
# The agent's own CLI config (under /cfg) — MCP wiring, API keys. Reading it is a
# benchmark-integrity leak: an agent should use its granted surface blind, not
# introspect how it was wired. Post-sidecar /cfg holds only a URL, but flagging
# the read still catches an agent probing its own configuration.
_CFG_CONFIG = re.compile(r"/cfg/(?:config\.toml|auth\.json|mcp\.json)")


def surface(profile: str) -> str:
    """The granted tool surface implied by a profile name."""
    for s in ("mcp_skills", "dku_skills", "mcp", "dku", "vanilla"):
        if s in profile:
            return s
    return "?"


def check(profile: str, bash_commands: list[str], mcp_calls: list[str]) -> list[str]:
    """Return a list of coherence violations for one trace (empty == coherent)."""
    joined = "\n".join(bash_commands)
    raw_api = bool(_DSSCLIENT.search(joined))
    used_dku = bool(_DKU.search(joined))
    used_mcp = bool(mcp_calls)
    issues: list[str] = []

    # Benchmark integrity — the image ships none of these, so any hit is a leak.
    if "/opt/bench" in joined:
        issues.append("read the baked /opt/bench tree")
    if "solution.md" in joined:
        issues.append("read solution.md")
    if _DOTENV.search(joined):
        issues.append("read a .env file")
    if _CFG_CONFIG.search(joined):
        issues.append("read its own agent config under /cfg")

    s = surface(profile)
    if s == "vanilla":
        if used_dku:
            issues.append("vanilla used the dku CLI")
        if used_mcp:
            issues.append("vanilla used MCP")
    elif s in ("dku", "dku_skills"):
        if raw_api:
            issues.append(f"{s} used raw DSSClient instead of the dku CLI")
        if used_mcp:
            issues.append(f"{s} used MCP")
    elif s in ("mcp", "mcp_skills"):
        if raw_api:
            issues.append(f"{s} used raw DSSClient (MCP-only profile)")
        if used_dku:
            issues.append(f"{s} used the dku CLI (MCP-only profile)")
        if not used_mcp:
            issues.append(f"{s} made no MCP calls")
    return issues
