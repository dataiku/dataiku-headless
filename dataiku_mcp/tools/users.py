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

"""Dataiku user administration tools."""

from typing import Annotated

from fastmcp import Context
from pydantic import Field

from ..server import mcp
from ..auth import get_dss_client, require_admin
from ..executors import run_blocking
from .utils.identity_sources import IdentitySourceType
from .utils.serialization import columnar, compact_json
from .utils.validation import (
    require_non_empty_string as _require_non_empty_string,
    require_non_empty_strings as _require_non_empty_strings,
    require_non_negative_int as _require_non_negative_int,
    require_positive_int as _require_positive_int,
)

Profile = Annotated[
    str, Field(description="A profile from get_licensing_status; capacity is enforced.")
]
Password = Annotated[
    str | None, Field(description="Required for LOCAL users, rejected for others.")
]
Offset = Annotated[int, Field(description="Zero-based offset into the matches.")]

_BASIC_USER_FIELDS = {
    "login": "login",
    "display_name": "displayName",
    "groups": "groups",
    "enabled": "enabled",
}
_USER_FIELDS = {
    **_BASIC_USER_FIELDS,
    "email": "email",
    "source_type": "sourceType",
    "profile": "userProfile",
}


def _sanitize_user(raw_user: dict, fields: dict[str, str]) -> dict:
    return {field: raw_user.get(raw_field) for field, raw_field in fields.items()}


def _validate_group_names(groups: list[str] | None) -> list[str] | None:
    if groups is None:
        return None
    return _require_non_empty_strings(groups, "groups")


async def _require_licensed_user_profile(profile: str) -> None:
    """Check that ``profile`` is a valid licensed profile type.

    Note: assumes that caller has admin rights; this internal method should
    ideally be called after checking the user is admin with `require_admin`.
    """

    def _run():
        status = get_dss_client().get_licensing_status()
        profiles = status.get("base", {}).get("userProfiles", [])
        if not profiles:
            raise ValueError("Dataiku did not return any available user profiles")
        if profile not in profiles:
            raise ValueError(
                f"'profile' must be one of the current Dataiku licensed profile types: "
                f"{', '.join(profiles)}"
            )

    await run_blocking(_run)


async def _require_existing_groups(groups: list[str]) -> None:
    """Check that every supplied group exists on the Dataiku instance.

    Uses the basic group-information listing available to non-administrators.
    """
    if not groups:
        return

    def _run():
        existing_groups = {
            group.get_raw()["name"] for group in get_dss_client().list_groups_info()
        }
        missing_groups = [group for group in groups if group not in existing_groups]
        if missing_groups:
            raise ValueError(
                f"The following groups do not exist: {', '.join(missing_groups)}"
            )

    await run_blocking(_run)


@mcp.tool(
    title="List Users",
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "openWorldHint": False,
    },
)
async def list_users(
    ctx: Context,
    search: Annotated[
        str,
        Field(description="Substring matched against login, display name, and email."),
    ] = "",
    groups: Annotated[
        list[str] | None,
        Field(description="Keeps users in at least one of these groups."),
    ] = None,
    offset: Offset = 0,
    limit: Annotated[int, Field(description="Capped at 100.")] = 20,
) -> str:
    """Find users and their exact logins; admins also see email, profile, and source."""
    search = search.strip()
    groups = _validate_group_names(groups)
    offset = _require_non_negative_int(offset, "offset")
    limit = min(_require_positive_int(limit, "limit"), 100)
    if groups:
        await _require_existing_groups(groups)

    try:
        await require_admin()
    except PermissionError:
        fields = _BASIC_USER_FIELDS
        raw_users = await run_blocking(
            lambda: [user.get_raw() for user in get_dss_client().list_users_info()]
        )
    else:
        fields = _USER_FIELDS
        raw_users = await run_blocking(lambda: get_dss_client().list_users())

    await ctx.info("Listing Dataiku users...")
    users = [_sanitize_user(raw_user, fields) for raw_user in raw_users]
    total_users = len(users)

    if search:
        query = search.casefold()
        users = [
            user
            for user in users
            if any(
                query in str(user.get(field) or "").casefold()
                for field in ("login", "display_name", "email")
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
        offset + returned_users if offset + returned_users < matched_users else None
    )

    return compact_json(
        {
            "total_users": total_users,
            "matched_users": matched_users,
            "returned_users": returned_users,
            "next_offset": next_offset,
            "users": columnar(page, list(fields)),
        }
    )


@mcp.tool(
    title="Create User",
    annotations={
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
async def create_user(
    login: Annotated[
        str, Field(description="Special characters beyond . _ - @ are rejected.")
    ],
    source_type: IdentitySourceType,
    profile: Profile,
    display_name: str,
    ctx: Context,
    password: Password = None,
    email: str | None = None,
    groups: Annotated[
        list[str] | None, Field(description="Complete group list; none when omitted.")
    ] = None,
) -> str:
    """Add an enabled user to the instance. Admin only."""
    login = _require_non_empty_string(login, "login")
    display_name = _require_non_empty_string(display_name, "display_name")
    profile = _require_non_empty_string(profile, "profile")
    groups = _validate_group_names(groups) or []
    if source_type == "LOCAL":
        password = _require_non_empty_string(password, "password")
    elif password is not None:
        raise ValueError("'password' may only be provided for LOCAL users")

    await require_admin()
    await _require_licensed_user_profile(profile)
    await _require_existing_groups(groups)
    await ctx.info(f"Creating Dataiku user '{login}'...")

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
        return _sanitize_user(user.get_settings().get_raw(), _USER_FIELDS)

    return compact_json({"user": await run_blocking(_run)})


@mcp.tool(
    title="Update User",
    annotations={
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def update_user(
    login: str,
    ctx: Context,
    source_type: IdentitySourceType | None = None,
    profile: Profile | None = None,
    display_name: str | None = None,
    password: Password = None,
    email: str | None = None,
    groups: Annotated[
        list[str] | None,
        Field(description="Complete group list, replacing the current one."),
    ] = None,
    enabled: bool | None = None,
) -> str:
    """Patch a user's settings; nulls are preserved, empty values clear. Admin only."""
    login = _require_non_empty_string(login, "login")
    if display_name is not None:
        display_name = _require_non_empty_string(display_name, "display_name")
    if profile is not None:
        profile = _require_non_empty_string(profile, "profile")
    if password is not None:
        password = _require_non_empty_string(password, "password")
    if groups is not None:
        groups = _validate_group_names(groups)

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
    await ctx.info(f"Updating Dataiku user '{login}'...")

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
        return _sanitize_user(user.get_settings().get_raw(), _USER_FIELDS)

    return compact_json({"user": await run_blocking(_run)})


@mcp.tool(
    title="Delete User",
    annotations={
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
async def delete_user(login: str, ctx: Context) -> str:
    """Remove a user from the instance. Admin only."""
    login = _require_non_empty_string(login, "login")
    await require_admin()
    await ctx.info(f"Deleting Dataiku user '{login}'...")

    def _run():
        get_dss_client().get_user(login).delete()

    await run_blocking(_run)
    return compact_json({"login": login, "deleted": True})
