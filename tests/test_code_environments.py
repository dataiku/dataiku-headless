"""Unit tests for managed Design-node code environment tools."""

import asyncio
import json

import pytest

from dataiku_mcp.tools import code_environments as tools
from tests.utils.fakes import FakeContext


def _raw(name: str, language: str = "PYTHON") -> dict:
    return {
        "envName": name,
        "envLang": language,
        "deploymentMode": "DESIGN_MANAGED",
        "usableByAll": True,
        "permissions": [{"group": "admins", "use": True, "update": True, "manageUsers": True}],
        "desc": {
            "owner": "owner",
            "pythonInterpreter": "PYTHON311" if language == "PYTHON" else None,
            "installCorePackages": True,
            "installJupyterSupport": True,
        },
        "specPackageList": "requests\nrich",
        "actualPackageList": "requests==2.0\nrich==1.0",
        "allContainerConfs": False,
        "containerConfs": ["cpu"],
        "allSparkKubernetesConfs": False,
        "sparkKubernetesConfs": ["spark"],
    }


class FakeSettings:
    def __init__(self, raw: dict):
        self.raw = raw
        self.save_calls = 0

    def get_raw(self):
        return self.raw

    def save(self):
        self.save_calls += 1

    def set_required_packages(self, *packages):
        self.raw["specPackageList"] = "\n".join(packages)

    def set_built_container_confs(self, *configs, **kwargs):
        self.raw["allContainerConfs"] = kwargs.get("all", False)
        if not self.raw["allContainerConfs"]:
            self.raw["containerConfs"] = list(configs)

    def set_built_spark_kubernetes_confs(self, *configs, **kwargs):
        self.raw["allSparkKubernetesConfs"] = kwargs.get("all", False)
        if not self.raw["allSparkKubernetesConfs"]:
            self.raw["sparkKubernetesConfs"] = list(configs)


class FakeCodeEnv:
    def __init__(self, raw: dict):
        self.settings = FakeSettings(raw)
        self.package_calls: list[bool] = []
        self.jupyter_calls: list[bool] = []
        self.image_calls = 0
        self.deleted = False
        self.usages = [{"envUsage": "RECIPE", "projectKey": "P", "objectId": "r"}]

    def get_settings(self):
        return self.settings

    def update_packages(self, force_rebuild_env=False):
        self.package_calls.append(force_rebuild_env)
        return {"success": True}

    def set_jupyter_support(self, active):
        self.jupyter_calls.append(active)
        return {"success": True}

    def update_images(self):
        self.image_calls += 1
        return {"success": True}

    def list_usages(self):
        return self.usages

    def delete(self):
        self.deleted = True


class FakeClient:
    def __init__(self, envs: list[FakeCodeEnv]):
        self.envs = {(env.settings.raw["envLang"], env.settings.raw["envName"]): env for env in envs}
        self.create_calls = []

    def list_code_envs(self):
        return [env.settings.raw for env in self.envs.values()]

    def get_code_env(self, language, name):
        return self.envs[(language, name)]

    def create_code_env(self, language, name, deployment_mode, params=None):
        self.create_calls.append((language, name, deployment_mode, params))
        env = FakeCodeEnv(_raw(name, language))
        self.envs[(language, name)] = env
        return env


def _result(coro):
    return json.loads(asyncio.run(coro))


def _patch_client(monkeypatch, client):
    monkeypatch.setattr(tools, "get_dss_client", lambda: client)


def test_list_code_envs_filters_exact_and_returns_details(monkeypatch):
    client = FakeClient([FakeCodeEnv(_raw("ALPHA")), FakeCodeEnv(_raw("beta", "R"))])
    _patch_client(monkeypatch, client)

    result = _result(
        tools.list_code_envs(
            FakeContext(), search="ALPHA", search_mode="exact", include_details=True
        )
    )

    assert result["matched_code_envs"] == 1
    columns = result["code_envs"]["columns"]
    row = dict(zip(columns, result["code_envs"]["rows"][0]))
    assert row["owner"] == "owner"
    assert row["requested_packages"] == ["requests", "rich"]
    assert row["actual_packages"] == ["requests==2.0", "rich==1.0"]


def test_list_code_env_usages_is_bounded_by_complete_match_set(monkeypatch):
    client = FakeClient([FakeCodeEnv(_raw(f"env-{index}")) for index in range(6)])
    _patch_client(monkeypatch, client)

    with pytest.raises(ValueError, match="at most five"):
        asyncio.run(tools.list_code_envs(FakeContext(), include_usages=True, limit=1))


def test_list_code_env_usages_implies_details(monkeypatch):
    client = FakeClient([FakeCodeEnv(_raw("env"))])
    _patch_client(monkeypatch, client)

    result = _result(tools.list_code_envs(FakeContext(), include_usages=True))

    columns = result["code_envs"]["columns"]
    row = dict(zip(columns, result["code_envs"]["rows"][0]))
    assert row["usages"] == client.get_code_env("PYTHON", "env").usages
    assert result["warning"]


def test_create_code_env_applies_baseline_and_never_builds_images(monkeypatch):
    client = FakeClient([])
    _patch_client(monkeypatch, client)
    permission = tools.CodeEnvGroupPermission(
        group="scientists", use=True, update=False, manage_users=False
    )

    _result(
        tools.create_code_env(
            "PYTHON",
            "new-env",
            FakeContext(),
            requested_packages=["pandas==2.3"],
            python_interpreter="PYTHON312",
            owner="alice",
            group_permissions=[permission],
            container_configurations=["cpu"],
        )
    )

    env = client.get_code_env("PYTHON", "new-env")
    assert client.create_calls == [("PYTHON", "new-env", "DESIGN_MANAGED", {"pythonInterpreter": "PYTHON312"})]
    assert env.settings.raw["desc"]["installCorePackages"] is True
    assert env.settings.raw["desc"]["installJupyterSupport"] is True
    assert env.settings.raw["desc"]["owner"] == "alice"
    assert env.settings.raw["specPackageList"] == "pandas==2.3"
    assert env.package_calls == [False]
    assert env.jupyter_calls == [True]
    assert env.image_calls == 0


def test_update_code_env_only_runs_explicit_build_actions(monkeypatch):
    env = FakeCodeEnv(_raw("env"))
    client = FakeClient([env])
    _patch_client(monkeypatch, client)

    _result(
        tools.update_code_env(
            "PYTHON",
            "env",
            FakeContext(),
            requested_packages=["new-package"],
            update_packages=True,
            force_rebuild=True,
            rebuild_images=True,
        )
    )

    assert env.settings.raw["specPackageList"] == "new-package"
    assert env.package_calls == [True]
    assert env.image_calls == 1


def test_update_code_env_rejects_force_rebuild_without_package_update(monkeypatch):
    _patch_client(monkeypatch, FakeClient([FakeCodeEnv(_raw("env"))]))

    with pytest.raises(ValueError, match="requires update_packages"):
        asyncio.run(
            tools.update_code_env(
                "PYTHON", "env", FakeContext(), force_rebuild=True
            )
        )


def test_delete_code_env_delegates_to_dss(monkeypatch):
    env = FakeCodeEnv(_raw("env"))
    _patch_client(monkeypatch, FakeClient([env]))

    result = _result(tools.delete_code_env("PYTHON", "env", FakeContext()))

    assert result == {"name": "env", "language": "PYTHON", "deleted": True}
    assert env.deleted is True
