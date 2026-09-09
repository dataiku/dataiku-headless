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

"""Unit tests for managed Design-node code environment tools."""

import asyncio
import inspect
import json

import pytest

import dataiku_mcp
from dataiku_mcp.tools import code_environments as tools
from tests.utils.fakes import FakeContext


def _tool_schema(name: str) -> dict:
    tool = next(
        item for item in asyncio.run(dataiku_mcp.mcp.list_tools()) if item.name == name
    )
    return tool.parameters["properties"]


def _enum_values(schema: dict) -> list[str]:
    """Collect a parameter's advertised enum from any depth of its schema.

    Pydantic nests an optional annotated Literal one ``anyOf`` deeper on Python
    3.10 than on 3.12+, so a fixed-depth lookup passes on one and fails on the
    other.
    """
    if "enum" in schema:
        return schema["enum"]
    for branch in schema.get("anyOf", []):
        found = _enum_values(branch)
        if found:
            return found
    return []


def _raw(name: str, language: str = "PYTHON") -> dict:
    return {
        "envName": name,
        "envLang": language,
        "deploymentMode": "DESIGN_MANAGED",
        "owner": "owner",
        "usableByAll": True,
        "permissions": [
            {"group": "admins", "use": True, "update": True, "manageUsers": True}
        ],
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
        self.envs = {
            (env.settings.raw["envLang"], env.settings.raw["envName"]): env
            for env in envs
        }
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


def test_list_code_envs_returns_summary_owner(monkeypatch):
    raw = _raw("ALPHA")
    raw["owner"] = "alice"
    client = FakeClient([FakeCodeEnv(raw)])
    _patch_client(monkeypatch, client)

    result = _result(tools.list_code_envs(FakeContext()))

    columns = result["code_envs"]["columns"]
    row = dict(zip(columns, result["code_envs"]["rows"][0]))
    assert row == {
        "name": "ALPHA",
        "language": "PYTHON",
        "owner": "alice",
        "deployment_mode": "DESIGN_MANAGED",
    }


def test_list_code_envs_does_not_return_usage_data(monkeypatch):
    client = FakeClient([FakeCodeEnv(_raw("env"))])
    _patch_client(monkeypatch, client)

    result = _result(tools.list_code_envs(FakeContext(), include_details=True))

    columns = result["code_envs"]["columns"]
    assert "usages" not in columns


def test_list_code_envs_ignores_search_mode_without_a_search(monkeypatch):
    client = FakeClient([FakeCodeEnv(_raw("env"))])
    _patch_client(monkeypatch, client)

    result = _result(tools.list_code_envs(FakeContext(), search_mode="unexpected"))

    assert result["matched_code_envs"] == 1


def test_list_code_envs_filters_for_all_declared_packages_before_pagination(
    monkeypatch,
):
    alpha = _raw("ALPHA")
    alpha["specPackageList"] = "pandas==2.2\nnumpy\nscikit_learn"
    beta = _raw("beta")
    beta["specPackageList"] = "pandas\nnumpy"
    gamma = _raw("gamma", "R")
    gamma["specPackageList"] = '"pandas","2.2"\n"numpy","1.0"'
    client = FakeClient([FakeCodeEnv(alpha), FakeCodeEnv(beta), FakeCodeEnv(gamma)])
    _patch_client(monkeypatch, client)

    result = _result(
        tools.list_code_envs(
            FakeContext(),
            packages=["PANDAS", "numpy", "scikit-learn"],
            offset=0,
            limit=1,
        )
    )

    assert result["matched_code_envs"] == 1
    assert result["returned_code_envs"] == 1
    row = dict(zip(result["code_envs"]["columns"], result["code_envs"]["rows"][0]))
    assert row["name"] == "ALPHA"


def test_list_code_envs_package_filter_composes_with_language_and_details(monkeypatch):
    python_env = _raw("python")
    python_env["specPackageList"] = "requests"
    r_env = _raw("r", "R")
    r_env["specPackageList"] = '"RJSONIO","1.3"'
    client = FakeClient([FakeCodeEnv(python_env), FakeCodeEnv(r_env)])
    _patch_client(monkeypatch, client)

    result = _result(
        tools.list_code_envs(
            FakeContext(),
            language="R",
            packages=["rjsonio"],
            include_details=True,
        )
    )

    row = dict(zip(result["code_envs"]["columns"], result["code_envs"]["rows"][0]))
    assert row["name"] == "r"
    assert row["requested_packages"] == ['"RJSONIO","1.3"']


@pytest.mark.parametrize(
    "packages", [[], ["pandas>=2"], ["pandas[performance]"], [" "]]
)
def test_list_code_envs_rejects_non_name_package_filters(packages):
    with pytest.raises(ValueError, match="packages"):
        _result(tools.list_code_envs(FakeContext(), packages=packages))


def test_create_code_env_applies_baseline_and_builds_selected_images(monkeypatch):
    client = FakeClient([])
    _patch_client(monkeypatch, client)
    permission = tools.CodeEnvGroupPermission(
        group="scientists", use=True, update=False, manage_users=False
    )

    result = _result(
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
    assert client.create_calls == [
        ("PYTHON", "new-env", "DESIGN_MANAGED", {"pythonInterpreter": "PYTHON312"})
    ]
    assert env.settings.raw["desc"]["installCorePackages"] is True
    assert env.settings.raw["desc"]["installJupyterSupport"] is True
    assert env.settings.raw["desc"]["owner"] == "alice"
    assert env.settings.raw["specPackageList"] == "pandas==2.3"
    assert env.package_calls == [False]
    assert env.jupyter_calls == [True]
    assert env.image_calls == 1
    assert result["image_update"] == {"success": True}


def test_create_code_env_does_not_build_images_without_targets(monkeypatch):
    client = FakeClient([])
    _patch_client(monkeypatch, client)

    result = _result(tools.create_code_env("PYTHON", "new-env", FakeContext()))

    env = client.get_code_env("PYTHON", "new-env")
    assert env.image_calls == 0
    assert result["image_update"] is None


def test_create_code_env_rejects_unknown_python_interpreter():
    """The allowed interpreters ride in the schema, so Pydantic rejects the rest.

    Calling the handler directly bypasses that boundary, so assert on the
    advertised enum instead of on a runtime check the handler no longer makes.
    """
    allowed = _enum_values(_tool_schema("create_code_env")["python_interpreter"])
    assert allowed, "python_interpreter must advertise its allowed values"
    assert "PYTHON38" not in allowed
    assert "PYTHON311" in allowed


def test_update_code_env_does_not_accept_python_interpreter():
    assert (
        "python_interpreter" not in inspect.signature(tools.update_code_env).parameters
    )


def test_update_code_env_rebuilds_for_package_changes(monkeypatch):
    env = FakeCodeEnv(_raw("env"))
    client = FakeClient([env])
    _patch_client(monkeypatch, client)

    _result(
        tools.update_code_env(
            "PYTHON",
            "env",
            FakeContext(),
            requested_packages=["new-package"],
            force_rebuild=True,
        )
    )

    assert env.settings.raw["specPackageList"] == "new-package"
    assert env.package_calls == [True]
    assert env.image_calls == 1


def test_update_code_env_rejects_package_changes_for_non_managed_env(monkeypatch):
    raw = _raw("env")
    raw["deploymentMode"] = "EXTERNAL_CONDA_NAMED"
    env = FakeCodeEnv(raw)
    _patch_client(monkeypatch, FakeClient([env]))

    with pytest.raises(ValueError, match="requested_packages.*DESIGN_MANAGED"):
        asyncio.run(
            tools.update_code_env(
                "PYTHON",
                "env",
                FakeContext(),
                requested_packages=["new-package"],
            )
        )

    assert env.settings.raw["specPackageList"] == "requests\nrich"
    assert env.settings.save_calls == 0
    assert env.package_calls == []
    assert env.image_calls == 0


def test_update_code_env_allows_other_changes_for_non_managed_env(monkeypatch):
    raw = _raw("env")
    raw["deploymentMode"] = "EXTERNAL_CONDA_NAMED"
    env = FakeCodeEnv(raw)
    _patch_client(monkeypatch, FakeClient([env]))

    _result(
        tools.update_code_env(
            "PYTHON",
            "env",
            FakeContext(),
            usable_by_all=False,
            container_configurations=["gpu"],
            force_rebuild=True,
        )
    )

    assert env.settings.raw["usableByAll"] is False
    assert env.settings.raw["containerConfs"] == ["gpu"]
    assert env.settings.save_calls == 1
    assert env.package_calls == [True]
    assert env.image_calls == 1


def test_update_code_env_force_rebuilds_local_environment_only(monkeypatch):
    env = FakeCodeEnv(_raw("env"))
    _patch_client(monkeypatch, FakeClient([env]))

    result = _result(
        tools.update_code_env("PYTHON", "env", FakeContext(), force_rebuild=True)
    )

    assert env.package_calls == [True]
    assert env.image_calls == 0
    assert result["image_update"] is None


def test_update_code_env_rebuilds_images_for_target_changes(monkeypatch):
    env = FakeCodeEnv(_raw("env"))
    _patch_client(monkeypatch, FakeClient([env]))

    result = _result(
        tools.update_code_env(
            "PYTHON",
            "env",
            FakeContext(),
            all_container_configurations=True,
            container_configurations=["gpu"],
            all_spark_kubernetes_configurations=True,
            spark_kubernetes_configurations=["spark-gpu"],
        )
    )

    assert env.package_calls == []
    assert env.image_calls == 1
    assert result["package_update"] is None
    assert env.settings.raw["allContainerConfs"] is True
    assert env.settings.raw["containerConfs"] == ["gpu"]
    assert env.settings.raw["allSparkKubernetesConfs"] is True
    assert env.settings.raw["sparkKubernetesConfs"] == ["spark-gpu"]


def test_delete_code_env_delegates_to_dss_when_unused(monkeypatch):
    raw = _raw("env")
    raw["deploymentMode"] = "PLUGIN_MANAGED"
    env = FakeCodeEnv(raw)
    env.usages = []
    _patch_client(monkeypatch, FakeClient([env]))

    result = _result(tools.delete_code_env("PYTHON", "env", FakeContext()))

    assert result == {"name": "env", "language": "PYTHON", "deleted": True}
    assert env.deleted is True


def test_delete_code_env_returns_usages_without_deleting(monkeypatch):
    env = FakeCodeEnv(_raw("ALTERYX_ENV"))
    env.usages = [
        {
            "envUsage": "PROJECT",
            "projectKey": "ALTERYXCONVERSION_SQL_SPARK_PROTO",
            "envLang": "PYTHON",
            "envName": "ALTERYX_ENV",
            "accessible": True,
        },
        {
            "envUsage": "NOTEBOOK",
            "projectKey": "PAT",
            "objectId": "Extending the Convert Node Class - Example",
            "envLang": "PYTHON",
            "envName": "ALTERYX_ENV",
            "accessible": True,
        },
        {
            "envUsage": "SCENARIO_STEP",
            "projectKey": "PAT",
            "objectId": "CONVERT",
            "envLang": "PYTHON",
            "envName": "ALTERYX_ENV",
            "accessible": True,
        },
    ]
    _patch_client(monkeypatch, FakeClient([env]))

    result = _result(tools.delete_code_env("PYTHON", "ALTERYX_ENV", FakeContext()))

    assert result["deleted"] is False
    assert (
        result["error"]
        == "Code environment cannot be deleted because it has current usages."
    )
    assert result["usages"] == env.usages
    assert "Remove or replace" in result["hint"]
    assert env.deleted is False
