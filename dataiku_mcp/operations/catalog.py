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

"""Audited operation declarations for Deployer and Govern."""

from types import MappingProxyType
from typing import Callable

from .govern_schemas import govern_arguments
from .models import Operation, arguments_for
from .handlers import deployer, govern


def _deployer(
    operation_id: str,
    handler: Callable,
    example: dict,
    *,
    effect="read",
    destructive=False,
    idempotent=False,
):
    return Operation(
        operation_id=operation_id,
        domain="deployer",
        description=handler.__doc__,
        effect=effect,
        allowed_instance_types=("deployer",),
        arguments=arguments_for(handler),
        handler=handler,
        requirements="Selected node must expose Project/API Deployer. The configured type does not verify feature availability or permissions.",
        response_contract="Responses contain operation results; settings are backend-defined and credential fields are redacted.",
        example=example,
        destructive=destructive,
        idempotent=idempotent,
    )


_DEPLOYER_OPERATIONS = [
    _deployer(
        "deployer.list_stages",
        deployer.list_deployer_stages,
        {"deployer_type": "project"},
    ),
    _deployer(
        "deployer.list_infrastructures",
        deployer.list_deployer_infrastructures,
        {"deployer_type": "project"},
    ),
    _deployer(
        "deployer.get_infrastructure",
        deployer.get_deployer_infrastructure,
        {"deployer_type": "project", "infra_id": "discovered-infra"},
    ),
    _deployer(
        "deployer.list_published_items",
        deployer.list_deployer_published_items,
        {"deployer_type": "api"},
    ),
    _deployer(
        "deployer.get_published_item",
        deployer.get_deployer_published_item,
        {"deployer_type": "api", "source_id": "discovered-service"},
    ),
    _deployer(
        "deployer.list_deployments",
        deployer.list_deployer_deployments,
        {"deployer_type": "project"},
    ),
    _deployer(
        "deployer.get_deployment",
        deployer.get_deployer_deployment,
        {"deployer_type": "project", "deployment_id": "discovered-deployment"},
    ),
    _deployer(
        "deployer.list_updates",
        deployer.list_deployer_updates,
        {"deployer_type": "project", "deployment_id": "discovered-deployment"},
    ),
    _deployer(
        "deployer.get_update",
        deployer.get_deployer_update,
        {"deployer_type": "project", "deployment_id": "discovered-deployment"},
    ),
    _deployer(
        "deployer.create_deployment",
        deployer.create_deployer_deployment,
        {
            "deployer_type": "project",
            "deployment_id": "requested-deployment",
            "infra_id": "discovered-infra",
            "source_id": "discovered-project",
            "version": "discovered-bundle",
        },
        effect="write",
    ),
    _deployer(
        "deployer.update_deployment",
        deployer.update_deployer_deployment,
        {
            "deployer_type": "api",
            "deployment_id": "discovered-deployment",
            "version": "discovered-version",
        },
        effect="write",
        destructive=True,
        idempotent=True,
    ),
    _deployer(
        "deployer.start_update",
        deployer.start_deployer_update,
        {"deployer_type": "project", "deployment_id": "discovered-deployment"},
        effect="write",
        destructive=True,
    ),
    _deployer(
        "deployer.get_future_status",
        deployer.get_deployer_future_status,
        {"future_id": "returned-future"},
    ),
]


def _govern_operation(name, spec):
    arguments = govern_arguments(name, spec)
    example = {}
    for param in spec.params:
        if param.required:
            example[param.name] = {
                "string": "discovered-" + param.name.replace("_", "-"),
                "object": {},
                "list": [],
                "boolean": False,
                "integer": 1,
                "any": "value",
            }[param.kind]
    if name == "delete_time_series_values":
        example["delete_all"] = True
    if "status" in example and name in {
        "update_signoff_status",
        "add_signoff_feedback",
        "update_signoff_feedback",
        "add_signoff_approval",
        "update_signoff_approval",
    }:
        example["status"] = "APPROVED"
    if "users_container" in example:
        example["users_container"] = {"type": "user", "login": "discovered-user"}
    return Operation(
        operation_id="govern." + name,
        domain="govern",
        description=spec.description,
        effect="read" if spec.kind == "read" else "write",
        allowed_instance_types=("govern",),
        arguments=arguments,
        handler=govern.operation_handler(spec),
        transports=("stdio",),
        requirements="Requires a compatible Govern release and a configured Govern profile with stdio credentials. Govern HTTP authentication is unsupported. Blueprint-specific definitions remain backend-defined; inspect current definitions before replacing them.",
        response_contract="Public Govern SDK JSON with credential fields recursively redacted. Write and delete actions operate on Govern records, not DSS projects. Definition replacements require preserving unrelated fields; inspect and re-read after mutations. No retry on uncertain outcome.",
        example=example,
        destructive=spec.kind != "read" and not name.startswith("create_"),
    )


_GOVERN_OPERATIONS = [
    _govern_operation(name, spec) for name, spec in govern.GOVERN_OPERATIONS.items()
]


OPERATIONS = {op.operation_id: op for op in _DEPLOYER_OPERATIONS + _GOVERN_OPERATIONS}
OPERATIONS = MappingProxyType(OPERATIONS)


def get_operation(operation_id: str) -> Operation:
    try:
        return OPERATIONS[operation_id]
    except KeyError:
        raise ValueError("Unknown operation_id. Use search_operations.") from None
