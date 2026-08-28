"""Dataiku licensing status inspection."""

from datetime import datetime, timezone

from fastmcp import Context

from ..server import mcp
from ..auth import get_dss_client, require_admin
from ..executors import run_blocking
from .utils.serialization import compact_json


def _profile_rows(status: dict, include_capabilities: bool) -> list[dict]:
    base = status.get("base", {})
    profile_limits = status.get("limits", {}).get("profileLimits", {})
    profiles = list(base.get("userProfiles", []))
    profiles.extend(sorted(set(profile_limits) - set(profiles)))

    rows = []
    for profile in profiles:
        profile_limit = profile_limits.get(profile, {})
        licensed = profile_limit.get("licensed", {})
        licensed_limit = licensed.get("licensedLimit")
        row = {
            "profile": profile,
            "licensed_limit": None if licensed_limit == -1 else licensed_limit,
            "unlimited": licensed_limit == -1,
            "direct_count": profile_limit.get("directCount", 0),
            "count_with_demoted_to": profile_limit.get("countWithDemotedTo", 0),
            "trials": profile_limit.get("trials", 0),
            "over_quota": profile_limit.get("overQuota", 0),
        }
        if include_capabilities:
            row["capabilities"] = {
                key: value for key, value in licensed.items() if key.startswith("may")
            }
        rows.append(row)
    return rows


@mcp.tool()
async def get_licensing_status(
    ctx: Context,
    include_profile_capabilities: bool = False,
) -> str:
    """Get Dataiku license validity, expiration, and profile capacity.
    Requires global administrator rights on the target Dataiku instance.

    Args:
        include_profile_capabilities: Include detailed per-profile permission flags;
            this quickly bloats the context, so use only if strictly required.
    """
    await require_admin()
    await ctx.info("Retrieving Dataiku licensing status...")

    def _run():
        return get_dss_client().get_licensing_status()

    status = await run_blocking(_run)
    base = status.get("base", {})
    expires_at = datetime.fromtimestamp(base["expiresOn"] / 1000, tz=timezone.utc)

    return compact_json(
        {
            "has_license": base.get("hasLicense", False),
            "valid": base.get("valid", False),
            "expired": base.get("expired", False),
            "expires_at": expires_at.isoformat().replace("+00:00", "Z"),
            "days_until_expiration": (expires_at - datetime.now(timezone.utc)).days,
            "profiles": _profile_rows(status, include_profile_capabilities),
        }
    )
