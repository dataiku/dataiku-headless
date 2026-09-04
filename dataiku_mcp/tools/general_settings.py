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

"""Dataiku General Settings inspection tools."""

from fastmcp import Context

from .. import mcp
from .utils.async_executor import run_blocking
from .utils.auth import get_dss_client, require_admin
from .utils.serialization import columnar, compact_json

_CONTAINER_SUMMARY_COLUMNS = [
    "name",
    "type",
    "workload_type",
    "usable_by",
    "allowed_groups",
]
_CONTAINER_DETAIL_COLUMNS = [
    *_CONTAINER_SUMMARY_COLUMNS,
    "image_build_config",
    "is_final",
    "properties",
    "temporary_directory",
    "docker_runtime",
    "kubernetes_runtime",
]
_SPARK_SUMMARY_COLUMNS = ["name", "managed_kubernetes"]
_SPARK_DETAIL_COLUMNS = [
    *_SPARK_SUMMARY_COLUMNS,
    "image_build_config",
    "spark_properties",
    "kubernetes_runtime",
    "cloud_credentials",
]


def _redact_properties(properties: list[dict]) -> list[dict]:
    """Return settings properties while withholding values marked as secret."""
    return [
        {
            "key": property_.get("key", ""),
            "value": None if property_.get("secret", False) else property_.get("value"),
            "is_final": property_.get("isFinal", False),
            "secret": property_.get("secret", False),
        }
        for property_ in properties
    ]


def _serialize_resources(raw: dict) -> dict:
    return {
        "memory_request_mb": raw.get("memRequestMB"),
        "memory_limit_mb": raw.get("memLimitMB"),
        "cpu_request": raw.get("cpuRequest"),
        "cpu_limit": raw.get("cpuLimit"),
        "custom_limits": raw.get("customLimits", []),
        "custom_requests": raw.get("customRequests", []),
    }


def _serialize_kubernetes_runtime(raw: dict) -> dict:
    return {
        "uses_default_cluster": not raw.get(
            "noImplicitK8sClusterAndNoDefaultClusterId", False
        ),
        "namespace": raw.get("managedNamespace", raw.get("kubernetesNamespace")),
        "authentication_mode": raw.get("authenticationMode"),
        "ensure_namespace_compliance": raw.get("ensureNamespaceCompliance", False),
        "create_namespace": raw.get("createNamespace", False),
        "namespace_labels": raw.get("namespaceLabels", []),
        "resources": _serialize_resources(raw.get("kubernetesResources") or {}),
        "host_path_volumes": raw.get("hostPathVolumes", []),
        "shared_memory_enabled": raw.get("enableCustomSHM", False),
        "shared_memory_size_mb": raw.get("customSHMValueMB"),
    }


def _serialize_container_config(raw: dict, include_details: bool) -> dict:
    result = {
        "name": raw.get("name", ""),
        "type": raw.get("type", ""),
        "workload_type": raw.get("workloadType", ""),
        "usable_by": raw.get("usableBy", ""),
        "allowed_groups": raw.get("allowedGroups", []),
    }
    if not include_details:
        return result

    docker = raw.get("dockerRuntimeConfig") or {}
    return {
        **result,
        "image_build_config": raw.get("imageBuildConfig", ""),
        "is_final": raw.get("isFinal", False),
        "properties": _redact_properties(raw.get("properties") or []),
        "temporary_directory": raw.get("DKU_TMPDIR"),
        "docker_runtime": {
            "tls_verify": docker.get("dockerTLSVerify", False),
            "network": docker.get("dockerNetwork"),
            "resources": docker.get("dockerResources", []),
        },
        "kubernetes_runtime": _serialize_kubernetes_runtime(
            raw.get("kubernetesRuntimeConfig") or {}
        ),
    }


def _serialize_cloud_credentials(raw: dict) -> dict:
    def provider(name: str) -> dict:
        settings = raw.get(name) or {}
        return {
            "mode": settings.get("mode"),
            "connections": settings.get("connections", []),
        }

    return {
        "enabled": raw.get("enabled", False),
        "aws": provider("aws"),
        "azure": provider("azure"),
        "gcp": provider("gcp"),
    }


def _serialize_spark_config(raw: dict, include_details: bool) -> dict:
    kubernetes = raw.get("kubernetesSettings") or {}
    result = {
        "name": raw.get("name", ""),
        "managed_kubernetes": kubernetes.get("managedKubernetes", False),
    }
    if not include_details:
        return result

    return {
        **result,
        "image_build_config": raw.get("imageBuildConfig", ""),
        "spark_properties": _redact_properties(raw.get("conf") or []),
        "kubernetes_runtime": _serialize_kubernetes_runtime(kubernetes),
        "cloud_credentials": _serialize_cloud_credentials(
            raw.get("cloudCredentialsSettings") or {}
        ),
    }


@mcp.tool()
async def list_container_exec_configs(
    ctx: Context, include_details: bool = False
) -> str:
    """List Dataiku container execution configurations.
    Requires global administrator rights on the target Dataiku instance.

    Args:
        include_details: Include runtime, image-build, and resource settings.
    """
    await require_admin()
    await ctx.info("Listing Dataiku container execution configurations...")
    settings = await run_blocking(
        lambda: get_dss_client().get_general_settings().get_raw()
    )
    configs = settings.get("containerSettings", {}).get("executionConfigs", []) or []
    rows = [_serialize_container_config(config, include_details) for config in configs]
    return compact_json(
        {
            "container_exec_configs": columnar(
                rows,
                _CONTAINER_DETAIL_COLUMNS
                if include_details
                else _CONTAINER_SUMMARY_COLUMNS,
            )
        }
    )


@mcp.tool()
async def list_spark_configs(ctx: Context, include_details: bool = False) -> str:
    """List Dataiku Spark configurations.
    Requires global administrator rights on the target Dataiku instance.

    Args:
        include_details: Include Spark, Kubernetes, image-build, and credential settings.
    """
    await require_admin()
    await ctx.info("Listing Dataiku Spark configurations...")
    settings = await run_blocking(
        lambda: get_dss_client().get_general_settings().get_raw()
    )
    configs = settings.get("sparkSettings", {}).get("executionConfigs", []) or []
    rows = [_serialize_spark_config(config, include_details) for config in configs]
    return compact_json(
        {
            "spark_configs": columnar(
                rows,
                _SPARK_DETAIL_COLUMNS if include_details else _SPARK_SUMMARY_COLUMNS,
            )
        }
    )
