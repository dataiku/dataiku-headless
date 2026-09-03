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

"""Unit tests for the user administration tools."""

import asyncio
import json

import pytest

from dataiku_mcp.tools import users

from tests.utils.fakes import FakeContext


class FakeUserInfo:
    def __init__(self, raw: dict):
        self.raw = raw

    def get_raw(self) -> dict:
        return self.raw


class FakeGroupInfo:
    def __init__(self, raw: dict):
        self.raw = raw

    def get_raw(self) -> dict:
        return self.raw


class FakeUsersClient:
    def __init__(
        self,
        *,
        admin_users: list[dict] | None = None,
        user_info=None,
        group_info=None,
    ):
        self.admin_users = admin_users or []
        self.user_info = user_info if user_info is not None else []
        self.group_info = group_info if group_info is not None else []
        self.list_users_calls = 0
        self.list_users_info_calls = 0
        self.list_groups_calls = 0
        self.list_groups_info_calls = 0

    def list_users(self) -> list[dict]:
        self.list_users_calls += 1
        return self.admin_users

    def list_users_info(self):
        self.list_users_info_calls += 1
        if isinstance(self.user_info, Exception):
            raise self.user_info
        return self.user_info

    def list_groups(self) -> list[dict]:
        self.list_groups_calls += 1
        return []

    def list_groups_info(self):
        self.list_groups_info_calls += 1
        if isinstance(self.group_info, Exception):
            raise self.group_info
        return self.group_info


def _load(coro) -> dict:
    return json.loads(asyncio.run(coro))


async def _allow_admin() -> None:
    pass


async def _deny_admin() -> None:
    raise PermissionError("not an administrator")


def test_list_users_uses_full_admin_result(monkeypatch):
    client = FakeUsersClient(
        admin_users=[
            {
                "login": "alice",
                "displayName": "Alice Example",
                "email": "alice@example.test",
                "sourceType": "LOCAL",
                "groups": ["team"],
                "userProfile": "DATA_SCIENTIST",
                "enabled": True,
            }
        ]
    )
    monkeypatch.setattr(users, "get_dss_client", lambda: client)
    monkeypatch.setattr(users, "require_admin", _allow_admin)

    result = _load(users.list_users(FakeContext()))

    assert client.list_users_calls == 1
    assert client.list_users_info_calls == 0
    assert result["users"] == {
        "columns": [
            "login",
            "display_name",
            "groups",
            "enabled",
            "email",
            "source_type",
            "profile",
        ],
        "rows": [
            [
                "alice",
                "Alice Example",
                ["team"],
                True,
                "alice@example.test",
                "LOCAL",
                "DATA_SCIENTIST",
            ]
        ],
    }


def test_list_users_falls_back_to_basic_info_and_filters(monkeypatch):
    client = FakeUsersClient(
        user_info=[
            FakeUserInfo(
                {
                    "login": "zed",
                    "displayName": "Target Person",
                    "groups": ["team"],
                    "enabled": True,
                }
            ),
            FakeUserInfo(
                {
                    "login": "amy",
                    "displayName": "Target Person",
                    "groups": ["team"],
                    "enabled": False,
                }
            ),
            FakeUserInfo(
                {
                    "login": "other",
                    "displayName": "Target Person",
                    "groups": ["other-team"],
                    "enabled": True,
                }
            ),
        ],
        group_info=[FakeGroupInfo({"name": "team"})],
    )
    monkeypatch.setattr(users, "get_dss_client", lambda: client)
    monkeypatch.setattr(users, "require_admin", _deny_admin)

    result = _load(
        users.list_users(
            FakeContext(), search="target", groups=["team"], offset=0, limit=1
        )
    )

    assert client.list_users_calls == 0
    assert client.list_users_info_calls == 1
    assert client.list_groups_calls == 0
    assert client.list_groups_info_calls == 1
    assert result == {
        "total_users": 3,
        "matched_users": 2,
        "returned_users": 1,
        "next_offset": 1,
        "users": {
            "columns": ["login", "display_name", "groups", "enabled"],
            "rows": [["amy", "Target Person", ["team"], False]],
        },
    }


def test_list_users_rejects_unknown_group_filter(monkeypatch):
    client = FakeUsersClient(group_info=[FakeGroupInfo({"name": "team"})])
    monkeypatch.setattr(users, "get_dss_client", lambda: client)
    monkeypatch.setattr(users, "require_admin", _deny_admin)

    with pytest.raises(ValueError, match="missing"):
        _load(users.list_users(FakeContext(), groups=["missing"]))

    assert client.list_groups_calls == 0
    assert client.list_groups_info_calls == 1
    assert client.list_users_info_calls == 0


def test_list_users_propagates_basic_info_failure(monkeypatch):
    client = FakeUsersClient(user_info=RuntimeError("basic info unavailable"))
    monkeypatch.setattr(users, "get_dss_client", lambda: client)
    monkeypatch.setattr(users, "require_admin", _deny_admin)

    with pytest.raises(RuntimeError, match="basic info unavailable"):
        _load(users.list_users(FakeContext()))
