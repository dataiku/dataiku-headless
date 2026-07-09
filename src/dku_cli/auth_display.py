from __future__ import annotations

from typing import TypedDict, assert_never

from dku_cli.auth import KeyResult, KeyStatus
from dku_cli.client import AUTH_MODE_IN_POD_TICKET

PROFILE_DISPLAY_COLUMNS = ["name", "node_type", "url", "status"]
PROFILE_DISPLAY_HEADERS = {
    "name": "Profile",
    "node_type": "Node Type",
    "url": "URL",
    "status": "Auth",
}


class ProfileListRow(TypedDict):
    name: str
    active: bool
    node_type: str
    url: str
    default_project: str
    auth_mode: str
    has_key: bool


class ProfileDisplayRow(TypedDict):
    name: str
    node_type: str
    url: str
    status: str


def profile_display_row(
    row: ProfileListRow, key_result: KeyResult
) -> ProfileDisplayRow:
    url = row["url"] or (
        "in-pod backend" if row["auth_mode"] == AUTH_MODE_IN_POD_TICKET else "no url"
    )
    name = row["name"] + (" *" if row["active"] else "")
    return {
        "name": name,
        "node_type": row["node_type"],
        "url": url,
        "status": _auth_label(row["auth_mode"], key_result),
    }


def _auth_label(auth_mode: str, key_result: KeyResult) -> str:
    if auth_mode == AUTH_MODE_IN_POD_TICKET:
        return "in-pod ticket"
    match key_result.status:
        case KeyStatus.OK:
            return "key stored"
        case KeyStatus.DENIED:
            return "keychain access denied (entry may exist; re-prompt may be required)"
        case KeyStatus.BACKEND_ERROR:
            return f"keychain error ({key_result.detail or ''})"
        case KeyStatus.MISSING:
            return "no key"
        case unreachable:
            assert_never(unreachable)
