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

"""Unit tests for General Settings configuration listing tools."""

import asyncio
import json

from dataiku_mcp.tools import general_settings

from tests.utils.fakes import FakeContext


class _FakeGeneralSettings:
    def __init__(self, raw: dict):
        self.raw = raw

    def get_raw(self) -> dict:
        return self.raw


class _FakeClient:
    def __init__(self, raw: dict):
        self.raw = raw

    def get_general_settings(self) -> _FakeGeneralSettings:
        return _FakeGeneralSettings(self.raw)


def _rows(table: dict) -> list[dict]:
    return [dict(zip(table["columns"], row, strict=True)) for row in table["rows"]]


def _install_client(monkeypatch, raw: dict) -> list[bool]:
    admin_calls: list[bool] = []

    async def require_admin() -> None:
        admin_calls.append(True)

    monkeypatch.setattr(general_settings, "get_dss_client", lambda: _FakeClient(raw))
    monkeypatch.setattr(general_settings, "require_admin", require_admin)
    return admin_calls


def _settings() -> dict:
    return {
        "containerSettings": {
            "executionConfigs": [
                {
                    "name": "compute-cpu",
                    "type": "KUBERNETES",
                    "workloadType": "ANY",
                    "usableBy": "GROUPS",
                    "allowedGroups": ["data-science"],
                    "imageBuildConfig": "compute-image",
                    "isFinal": False,
                    "properties": [
                        {"key": "visible", "value": "value", "isFinal": True},
                        {"key": "hidden", "value": "secret", "secret": True},
                    ],
                    "DKU_TMPDIR": "/tmp/dku",
                    "kubernetesRuntimeConfig": {
                        "kubeConfigPath": "/secret/config",
                        "kubernetesNamespace": "dss-${dssUserLogin}",
                        "createNamespace": True,
                        "kubernetesResources": {"memLimitMB": 4096, "cpuLimit": 2},
                    },
                }
            ]
        },
        "sparkSettings": {
            "executionConfigs": [
                {
                    "name": "spark-yarn",
                    "conf": [],
                },
                {
                    "name": "spark-k8s",
                    "imageBuildConfig": "spark-image",
                    "conf": [
                        {"key": "spark.executor.memory", "value": "3g"},
                        {
                            "key": "spark.hadoop.token",
                            "value": "secret",
                            "secret": True,
                        },
                    ],
                    "kubernetesSettings": {
                        "managedKubernetes": True,
                        "kubeConfigPath": "/secret/spark-config",
                        "managedNamespace": "spark-${dssUserLogin}",
                        "authenticationMode": "DYNAMIC_SERVICE_ACCOUNT",
                        "kubernetesResources": {"cpuRequest": 0.5},
                    },
                    "cloudCredentialsSettings": {
                        "enabled": True,
                        "aws": {"mode": "CONNECTION", "connections": ["aws-main"]},
                    },
                },
            ]
        },
    }


def test_list_container_exec_configs_returns_minimal_summary(monkeypatch):
    admin_calls = _install_client(monkeypatch, _settings())

    result = json.loads(
        asyncio.run(general_settings.list_container_exec_configs(FakeContext()))
    )

    assert admin_calls == [True]
    assert _rows(result["container_exec_configs"]) == [
        {
            "name": "compute-cpu",
            "type": "KUBERNETES",
            "workload_type": "ANY",
            "usable_by": "GROUPS",
            "allowed_groups": ["data-science"],
        }
    ]


def test_list_container_exec_configs_redacts_detailed_settings(monkeypatch):
    _install_client(monkeypatch, _settings())

    result = json.loads(
        asyncio.run(general_settings.list_container_exec_configs(FakeContext(), True))
    )
    row = _rows(result["container_exec_configs"])[0]

    assert row["image_build_config"] == "compute-image"
    assert row["properties"][1]["value"] is None
    assert row["properties"][1]["secret"] is True
    assert row["kubernetes_runtime"]["namespace"] == "dss-${dssUserLogin}"
    assert row["kubernetes_runtime"]["resources"]["memory_limit_mb"] == 4096
    assert "kubeConfigPath" not in json.dumps(row)


def test_list_spark_configs_returns_all_configs_including_non_kubernetes(monkeypatch):
    _install_client(monkeypatch, _settings())

    result = json.loads(asyncio.run(general_settings.list_spark_configs(FakeContext())))

    assert _rows(result["spark_configs"]) == [
        {"name": "spark-yarn", "managed_kubernetes": False},
        {"name": "spark-k8s", "managed_kubernetes": True},
    ]


def test_list_spark_configs_returns_curated_redacted_details(monkeypatch):
    _install_client(monkeypatch, _settings())

    result = json.loads(
        asyncio.run(general_settings.list_spark_configs(FakeContext(), True))
    )
    row = _rows(result["spark_configs"])[1]

    assert row["image_build_config"] == "spark-image"
    assert row["spark_properties"] == [
        {
            "key": "spark.executor.memory",
            "value": "3g",
            "is_final": False,
            "secret": False,
        },
        {
            "key": "spark.hadoop.token",
            "value": None,
            "is_final": False,
            "secret": True,
        },
    ]
    assert row["kubernetes_runtime"]["authentication_mode"] == "DYNAMIC_SERVICE_ACCOUNT"
    assert row["cloud_credentials"]["aws"] == {
        "mode": "CONNECTION",
        "connections": ["aws-main"],
    }
    assert "kubeConfigPath" not in json.dumps(row)


def test_list_configuration_tools_handle_missing_settings(monkeypatch):
    _install_client(monkeypatch, {})

    container_result = json.loads(
        asyncio.run(general_settings.list_container_exec_configs(FakeContext()))
    )
    spark_result = json.loads(
        asyncio.run(general_settings.list_spark_configs(FakeContext()))
    )

    assert container_result["container_exec_configs"]["rows"] == []
    assert spark_result["spark_configs"]["rows"] == []
