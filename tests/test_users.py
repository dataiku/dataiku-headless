"""Unit tests for DSS user administration tools."""

import asyncio
import json

import pytest

from dataiku_mcp.tools import users
from tests.utils.fakes import FakeContext


def _raw_user(
    login: str,
    *,
    display_name: str = "",
    email: str | None = None,
    source_type: str = "LOCAL",
    groups: list[str] | None = None,
    profile: str = "FULL_DESIGNER",
    enabled: bool = True,
) -> dict:
    return {
        "login": login,
        "displayName": display_name,
        "email": email,
        "sourceType": source_type,
        "groups": groups or [],
        "userProfile": profile,
        "enabled": enabled,
        "credentials": {"warehouse": {"password": "secret"}},
        "secrets": [{"name": "token", "value": "secret"}],
    }


class FakeUserSettings:
    def __init__(self, raw: dict):
        self.raw = raw
        self.save_calls = 0

    def get_raw(self) -> dict:
        return self.raw

    def save(self) -> None:
        self.save_calls += 1


class FakeUser:
    def __init__(self, raw: dict):
        self.settings = FakeUserSettings(raw)
        self.delete_calls: list[bool] = []

    def get_settings(self) -> FakeUserSettings:
        return self.settings

    def delete(self, allow_self_deletion: bool = False) -> None:
        self.delete_calls.append(allow_self_deletion)


class FakeUserClient:
    def __init__(self, raw_users: list[dict] | None = None):
        self.users = {
            raw_user["login"]: FakeUser(raw_user) for raw_user in (raw_users or [])
        }
        self.create_calls: list[dict] = []

    def list_users(self) -> list[dict]:
        return [user.settings.raw for user in self.users.values()]

    def get_user(self, login: str) -> FakeUser:
        if login not in self.users:
            raise KeyError(login)
        return self.users[login]

    def create_user(
        self,
        login: str,
        password: str | None,
        *,
        display_name: str,
        source_type: str,
        groups: list[str],
        profile: str,
        email: str | None,
    ) -> FakeUser:
        call = {
            "login": login,
            "password": password,
            "display_name": display_name,
            "source_type": source_type,
            "groups": groups,
            "profile": profile,
            "email": email,
        }
        self.create_calls.append(call)
        raw = _raw_user(
            login,
            display_name=display_name,
            email=email,
            source_type=source_type,
            groups=groups,
            profile=profile,
        )
        self.users[login] = FakeUser(raw)
        return self.users[login]


def _install_client(monkeypatch, raw_users: list[dict] | None = None) -> FakeUserClient:
    client = FakeUserClient(raw_users)
    monkeypatch.setattr(users, "get_dss_client", lambda: client)
    return client


def _run(tool, *args, **kwargs) -> dict:
    return json.loads(asyncio.run(tool(*args, **kwargs)))


def test_list_users_searches_sorts_and_paginates(monkeypatch):
    _install_client(
        monkeypatch,
        [
            _raw_user("zoe", display_name="Zoe", email="zoe@example.com"),
            _raw_user("alice", display_name="Alice Smith", email="a@example.com"),
            _raw_user("bob", display_name="Bob", email="smith@example.com"),
        ],
    )

    result = _run(
        users.list_users,
        FakeContext(),
        search="SMITH",
        offset=0,
        limit=1,
    )

    assert result == {
        "total_users": 3,
        "matched_users": 2,
        "returned_users": 1,
        "next_offset": 1,
        "users": {
            "columns": users._USER_COLUMNS,
            "rows": [
                [
                    "alice",
                    "Alice Smith",
                    "a@example.com",
                    "LOCAL",
                    [],
                    "FULL_DESIGNER",
                    True,
                ]
            ],
        },
    }


def test_list_users_caps_limit_and_marks_last_page(monkeypatch):
    _install_client(monkeypatch, [_raw_user("alice"), _raw_user("bob")])

    result = _run(users.list_users, FakeContext(), offset=1, limit=500)

    assert result["total_users"] == 2
    assert result["matched_users"] == 2
    assert result["returned_users"] == 1
    assert result["next_offset"] is None
    assert result["users"]["rows"][0][0] == "bob"


@pytest.mark.parametrize(
    ("offset", "limit", "field"),
    [(-1, 20, "offset"), (0, 0, "limit")],
)
def test_list_users_rejects_invalid_pagination(offset, limit, field):
    with pytest.raises(ValueError, match=field):
        asyncio.run(users.list_users(FakeContext(), offset=offset, limit=limit))


def test_create_local_user_requires_password_and_sanitizes_result(monkeypatch):
    client = _install_client(monkeypatch)

    result = _run(
        users.create_user,
        "alice",
        "LOCAL",
        "FULL_DESIGNER",
        FakeContext(),
        password="temporary-password",
        display_name="Alice",
        email="alice@example.com",
        groups=["designers"],
    )

    assert client.create_calls[0]["password"] == "temporary-password"
    assert result["user"]["login"] == "alice"
    assert "password" not in result["user"]
    assert "credentials" not in result["user"]
    assert "secrets" not in result["user"]


def test_create_local_user_rejects_missing_password():
    with pytest.raises(ValueError, match="password"):
        asyncio.run(
            users.create_user(
                "alice", "LOCAL", "FULL_DESIGNER", FakeContext()
            )
        )


@pytest.mark.parametrize("source_type", ["LDAP", "LOCAL_NO_AUTH", "AZURE_AD"])
def test_create_external_user_omits_password(monkeypatch, source_type):
    client = _install_client(monkeypatch)

    _run(
        users.create_user,
        "alice",
        source_type,
        "AI_CONSUMER",
        FakeContext(),
    )

    assert client.create_calls[0]["password"] is None


def test_create_external_user_rejects_password():
    with pytest.raises(ValueError, match="LOCAL users"):
        asyncio.run(
            users.create_user(
                "alice",
                "LDAP",
                "FULL_DESIGNER",
                FakeContext(),
                password="ignored",
            )
        )


def test_update_user_patches_only_supplied_fields(monkeypatch):
    original = _raw_user(
        "alice",
        display_name="Alice",
        email="old@example.com",
        groups=["designers"],
    )
    client = _install_client(monkeypatch, [original])

    result = _run(
        users.update_user,
        "alice",
        FakeContext(),
        email="",
        groups=[],
        enabled=False,
    )

    settings = client.get_user("alice").settings
    assert settings.save_calls == 1
    assert settings.raw["displayName"] == "Alice"
    assert settings.raw["email"] == ""
    assert settings.raw["groups"] == []
    assert settings.raw["enabled"] is False
    assert result["user"]["email"] == ""
    assert "credentials" not in result["user"]


def test_update_user_requires_a_change():
    with pytest.raises(ValueError, match="at least one"):
        asyncio.run(users.update_user("alice", FakeContext()))


def test_update_user_requires_password_when_changing_to_local(monkeypatch):
    _install_client(monkeypatch, [_raw_user("alice", source_type="LDAP")])

    with pytest.raises(ValueError, match="password.*required"):
        asyncio.run(
            users.update_user(
                "alice", FakeContext(), source_type="LOCAL"
            )
        )


def test_update_user_rejects_password_for_external_source(monkeypatch):
    _install_client(monkeypatch, [_raw_user("alice", source_type="AZURE_AD")])

    with pytest.raises(ValueError, match="LOCAL users"):
        asyncio.run(
            users.update_user(
                "alice", FakeContext(), password="temporary-password"
            )
        )


def test_delete_user_keeps_self_deletion_protection(monkeypatch):
    client = _install_client(monkeypatch, [_raw_user("alice")])

    result = _run(users.delete_user, "alice", FakeContext())

    assert result == {"login": "alice", "deleted": True}
    assert client.get_user("alice").delete_calls == [False]
