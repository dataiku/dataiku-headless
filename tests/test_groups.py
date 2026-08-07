"""Unit tests for the group administration tools."""

import asyncio
import json

import pytest

from dataiku_mcp.tools import groups

from tests.utils.fakes import FakeContext


class FakeGroupInfo:
    def __init__(self, raw: dict):
        self.raw = raw

    def get_raw(self) -> dict:
        return self.raw


class FakeGroupsClient:
    def __init__(self, *, admin_groups: list[dict] | None = None, group_info=None):
        self.admin_groups = admin_groups or []
        self.group_info = group_info if group_info is not None else []
        self.list_groups_calls = 0
        self.list_groups_info_calls = 0

    def list_groups(self) -> list[dict]:
        self.list_groups_calls += 1
        return self.admin_groups

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


def test_list_groups_uses_full_admin_result(monkeypatch):
    client = FakeGroupsClient(
        admin_groups=[
            {
                "name": "team",
                "description": "Team group",
                "sourceType": "LOCAL",
                "admin": False,
            }
        ]
    )
    monkeypatch.setattr(groups, "get_dss_client", lambda: client)
    monkeypatch.setattr(groups, "require_admin", _allow_admin)

    result = _load(groups.list_groups(FakeContext()))

    assert client.list_groups_calls == 1
    assert client.list_groups_info_calls == 0
    assert result["groups"] == {
        "columns": ["name", "description", "source_type", "is_admin"],
        "rows": [["team", "Team group", "LOCAL", False]],
    }


def test_list_groups_falls_back_to_basic_info_and_filters(monkeypatch):
    client = FakeGroupsClient(
        group_info=[
            FakeGroupInfo({"name": "zeta"}),
            FakeGroupInfo({"name": "alpha"}),
            FakeGroupInfo({"name": "other"}),
        ]
    )
    monkeypatch.setattr(groups, "get_dss_client", lambda: client)
    monkeypatch.setattr(groups, "require_admin", _deny_admin)

    result = _load(groups.list_groups(FakeContext(), search="a", limit=1))

    assert client.list_groups_calls == 0
    assert client.list_groups_info_calls == 1
    assert result == {
        "total_groups": 3,
        "matched_groups": 2,
        "returned_groups": 1,
        "next_offset": 1,
        "groups": {"columns": ["name"], "rows": [["alpha"]]},
    }


@pytest.mark.parametrize(
    ("kwargs", "option"),
    [
        ({"source_type": "LOCAL"}, "source_type"),
        ({"is_admin": True}, "is_admin"),
        ({"include_permissions": True}, "include_permissions"),
    ],
)
def test_list_groups_rejects_unavailable_non_admin_options(monkeypatch, kwargs, option):
    client = FakeGroupsClient()
    monkeypatch.setattr(groups, "get_dss_client", lambda: client)
    monkeypatch.setattr(groups, "require_admin", _deny_admin)

    with pytest.raises(PermissionError, match=option):
        _load(groups.list_groups(FakeContext(), **kwargs))

    assert client.list_groups_info_calls == 0


def test_list_groups_propagates_basic_info_failure(monkeypatch):
    client = FakeGroupsClient(group_info=RuntimeError("basic info unavailable"))
    monkeypatch.setattr(groups, "get_dss_client", lambda: client)
    monkeypatch.setattr(groups, "require_admin", _deny_admin)

    with pytest.raises(RuntimeError, match="basic info unavailable"):
        _load(groups.list_groups(FakeContext()))
