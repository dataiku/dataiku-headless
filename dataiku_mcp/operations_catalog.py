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

"""Audited operation declarations for the Project and API Deployer."""

from .operation_registry import Operation, arguments_for, make_catalog
from .tools import deployer


def _deployer(
    name: str, example: dict, *, effect="read", destructive=False, idempotent=False
):
    handler = getattr(deployer, name)
    return Operation(
        operation_id="deployer." + name.replace("_deployer", ""),
        domain="deployer",
        description=handler.__doc__,
        effect=effect,
        allowed_instance_types=("deployer",),
        arguments=arguments_for(handler),
        handler=handler,
        requirements="Selected node must expose Project/API Deployer. The configured type does not verify feature availability or permissions.",
        response_contract="Selected operational fields; credentials, raw settings, free-text diagnostics and update logs are omitted. Configuration saves do not apply deployments; start_update returns a future_id for deployer.get_future_status on the same instance.",
        example=example,
        destructive=destructive,
        idempotent=idempotent,
    )


_DEPLOYER_OPERATIONS = list(
    [
        _deployer("list_deployer_stages", {"deployer_type": "project"}),
        _deployer("list_deployer_infrastructures", {"deployer_type": "project"}),
        _deployer(
            "get_deployer_infrastructure",
            {"deployer_type": "project", "infra_id": "discovered-infra"},
        ),
        _deployer("list_deployer_published_items", {"deployer_type": "api"}),
        _deployer(
            "get_deployer_published_item",
            {"deployer_type": "api", "source_id": "discovered-service"},
        ),
        _deployer("list_deployer_deployments", {"deployer_type": "project"}),
        _deployer(
            "get_deployer_deployment",
            {"deployer_type": "project", "deployment_id": "discovered-deployment"},
        ),
        _deployer(
            "list_deployer_updates",
            {"deployer_type": "project", "deployment_id": "discovered-deployment"},
        ),
        _deployer(
            "get_deployer_update",
            {"deployer_type": "project", "deployment_id": "discovered-deployment"},
        ),
        _deployer(
            "create_deployer_deployment",
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
            "update_deployer_deployment",
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
            "start_deployer_update",
            {"deployer_type": "project", "deployment_id": "discovered-deployment"},
            effect="write",
            destructive=True,
        ),
        _deployer("get_deployer_future_status", {"future_id": "returned-future"}),
    ]
)


OPERATIONS = make_catalog(_DEPLOYER_OPERATIONS)
