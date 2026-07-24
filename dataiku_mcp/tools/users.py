"""DSS user administration tools."""

from fastmcp import Context

from .. import mcp
from .utils.async_executor import run_blocking
from .utils.auth import get_dss_client, require_admin
from .utils.identity_sources import require_identity_source_type
from .utils.serialization import columnar, compact_json
from .utils.validation import (
    require_non_empty_string as _require_non_empty_string,
    require_non_negative_int as _require_non_negative_int,
    require_positive_int as _require_positive_int,
)

_USER_COLUMNS = [
    "login",
    "displayName",
    "email",
    "sourceType",
    "groups",
    "userProfile",
    "enabled",
]


def _sanitize_user(raw_user: dict, columns: list[str]) -> dict:
    return {field: raw_user.get(field) for field in columns}


def _validate_groups(groups: list[str] | None) -> list[str] | None:
    if groups is None:
        return None
    return [
        _require_non_empty_string(group, f"groups[{index}]")
        for index, group in enumerate(groups)
    ]


async def _require_licensed_user_profile(profile: str) -> None:
    """Check that ``profile`` is a valid licensed profile type.

    Note: assumes that caller has admin rights; this internal method should
    ideally be called after checking the user is admin with `require_admin`.
    """
    def _run():
        status = get_dss_client().get_licensing_status()
        profiles = status.get("base", {}).get("userProfiles", [])
        if not profiles:
            raise ValueError("DSS did not return any available user profiles")
        if profile not in profiles:
            raise ValueError(
                f"'profile' must be one of the current DSS licensed profile types: "
                f"{', '.join(profiles)}"
            )

    await run_blocking(_run)


async def _require_existing_groups(groups: list[str]) -> None:
    """Check that every supplied group exists on the DSS instance.

    Note: assumes that caller has admin rights; this internal method should
    ideally be called after checking the user is admin with `require_admin`.
    """
    if not groups:
        return

    def _run():
        existing_groups = {
            group["name"] for group in get_dss_client().list_groups()
        }
        missing_groups = [group for group in groups if group not in existing_groups]
        if missing_groups:
            raise ValueError(
                f"The following groups do not exist: {', '.join(missing_groups)}"
            )

    await run_blocking(_run)


@mcp.tool()
async def list_users(
    ctx: Context,
    search: str = "",
    groups: list[str] | None = None,
    offset: int = 0,
    limit: int = 20,
) -> str:
    """List Dataiku users, with optional search and offset pagination.
    Requires global administrator rights on the target Dataiku instance.

    Args:
        search: Case-insensitive substring matched against login, display name, and email.
        groups: Group names. Returns users who belong to at least one supplied group.
        offset: Zero-based offset within the matching users.
        limit: Maximum users to return. Values above 100 are capped at 100.
    """
    search = search.strip()
    groups = _validate_groups(groups)
    offset = _require_non_negative_int(offset, "offset")
    limit = min(_require_positive_int(limit, "limit"), 100)
    await require_admin()
    await ctx.info("Listing DSS users...")

    def _run():
        return get_dss_client().list_users()

    raw_users = await run_blocking(_run)
    users = [_sanitize_user(raw_user, _USER_COLUMNS) for raw_user in raw_users]
    total_users = len(users)

    if search:
        query = search.casefold()
        users = [
            user
            for user in users
            if any(
                query in str(user.get(field) or "").casefold()
                for field in ("login", "displayName", "email")
            )
        ]

    if groups:
        requested_groups = set(groups)
        users = [
            user
            for user in users
            if requested_groups.intersection(user.get("groups") or [])
        ]

    users.sort(
        key=lambda user: (
            str(user["login"]).casefold(),
            str(user["login"]),
        )
    )
    matched_users = len(users)
    page = users[offset : offset + limit]
    returned_users = len(page)
    next_offset = (
        offset + returned_users
        if offset + returned_users < matched_users
        else None
    )

    return compact_json(
        {
            "total_users": total_users,
            "matched_users": matched_users,
            "returned_users": returned_users,
            "next_offset": next_offset,
            "users": columnar(page, _USER_COLUMNS),
        }
    )


@mcp.tool()
async def create_user(
    login: str,
    source_type: str,
    profile: str,
    display_name: str,
    ctx: Context,
    password: str | None = None,
    email: str | None = None,
    groups: list[str] | None = None,
) -> str:
    """Create an enabled Dataiku user and return its core settings.
    Requires global administrator rights on the target Dataiku instance.

    Before assigning ``profile``, call ``get_licensing_status`` to confirm the
    profile is available and review its licensing capacity.

    Args:
        login: Does not accept special characters beyond '.', '_', '-', '@'.
        source_type: Authentication source: LOCAL, LDAP, AZURE_AD, LOCAL_NO_AUTH
            (SSO), CUSTOM, or PAM.
        profile: User profile available under the DSS license.
        password: Required for LOCAL users and invalid for external users.
        groups: Complete initial list of group names. Defaults to no groups.
    """
    login = _require_non_empty_string(login, "login")
    source_type = require_identity_source_type(source_type)
    display_name = _require_non_empty_string(display_name, "display_name")
    profile = _require_non_empty_string(profile, "profile")
    groups = _validate_groups(groups) or []
    if source_type == "LOCAL":
        password = _require_non_empty_string(password, "password")
    elif password is not None:
        raise ValueError("'password' may only be provided for LOCAL users")

    await require_admin()
    await _require_licensed_user_profile(profile)
    await _require_existing_groups(groups)
    await ctx.info(f"Creating DSS user '{login}'...")

    def _run():
        client = get_dss_client()
        user = client.create_user(
            login,
            password,
            display_name=display_name,
            source_type=source_type,
            groups=groups,
            profile=profile,
            email=email,
        )
        return _sanitize_user(user.get_settings().get_raw(), _USER_COLUMNS)

    return compact_json({"user": await run_blocking(_run)})


@mcp.tool()
async def update_user(
    login: str,
    ctx: Context,
    source_type: str | None = None,
    profile: str | None = None,
    display_name: str | None = None,
    password: str | None = None,
    email: str | None = None,
    groups: list[str] | None = None,
    enabled: bool | None = None,
) -> str:
    """Patch supplied core settings for one Dataiku user.
    Requires global administrator rights on the target Dataiku instance.

    Omitted (null) fields are preserved. An empty groups list removes all memberships,
    and an empty email clears the email address. Before changing ``profile``, call
    ``get_licensing_status`` to confirm the profile is available and review its
    licensing capacity.

    Args:
        source_type: Authentication source: LOCAL, LDAP, AZURE_AD, LOCAL_NO_AUTH
            (SSO), CUSTOM, or PAM.
        profile: User profile available under the DSS license.
        password: Required for LOCAL users and invalid for external users.
        groups: Complete list of group names. Defaults to no groups.
    """
    login = _require_non_empty_string(login, "login")
    if display_name is not None:
        display_name = _require_non_empty_string(display_name, "display_name")
    if groups is not None:
        groups = _validate_groups(groups)
    if profile is not None:
        profile = _require_non_empty_string(profile, "profile")
    if source_type is not None:
        source_type = require_identity_source_type(source_type)
    if password is not None:
        password = _require_non_empty_string(password, "password")

    changes = {
        "displayName": display_name,
        "email": email,
        "groups": groups,
        "userProfile": profile,
        "enabled": enabled,
        "sourceType": source_type,
        "password": password,
    }
    if all(value is None for value in changes.values()):
        raise ValueError("Provide at least one user field to update")

    await require_admin()
    if profile is not None:
        await _require_licensed_user_profile(profile)
    if groups is not None:
        await _require_existing_groups(groups)
    await ctx.info(f"Updating DSS user '{login}'...")

    def _run():
        client = get_dss_client()
        user = client.get_user(login)
        settings = user.get_settings()
        raw_settings = settings.get_raw()

        current_source_type = raw_settings.get("sourceType")
        target_source_type = source_type or current_source_type

        if (
            source_type == "LOCAL"
            and current_source_type != "LOCAL"
            and password is None
        ):
            raise ValueError(
                "'password' is required when changing a user to source_type LOCAL"
            )
        if password is not None and target_source_type != "LOCAL":
            raise ValueError("'password' may only be provided for LOCAL users")

        for field, value in changes.items():
            if value is not None:
                raw_settings[field] = value
        settings.save()
        return _sanitize_user(user.get_settings().get_raw(), _USER_COLUMNS)

    return compact_json({"user": await run_blocking(_run)})


@mcp.tool()
async def delete_user(login: str, ctx: Context) -> str:
    """Delete one DSS user. Self-deletion remains prohibited.
    Requires global administrator rights on the target Dataiku instance.
    """
    login = _require_non_empty_string(login, "login")
    await require_admin()
    await ctx.info(f"Deleting DSS user '{login}'...")

    def _run():
        get_dss_client().get_user(login).delete()

    await run_blocking(_run)
    return compact_json({"login": login, "deleted": True})
