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

"""One schema and policy contract for discovery, middleware and dispatch."""

import inspect
from dataclasses import dataclass
from types import MappingProxyType
from typing import Awaitable, Callable, Literal, get_type_hints

from pydantic import BaseModel, ConfigDict, ValidationError, create_model

from .config.models import InstanceType
from .tools.utils.redaction import contains_redacted_values

Effect = Literal["read", "write"]


class OperationArguments(BaseModel):
    model_config = ConfigDict(
        extra="forbid", strict=True, hide_input_in_errors=True, allow_inf_nan=False
    )


@dataclass(frozen=True)
class Operation:
    operation_id: str
    domain: str
    description: str
    effect: Effect
    allowed_instance_types: tuple[InstanceType, ...]
    arguments: type[BaseModel]
    handler: Callable[..., Awaitable[str]]
    requirements: str
    response_contract: str
    example: dict
    destructive: bool = False
    idempotent: bool = False
    category: str = ""
    backend: Literal["dss", "govern"] = "dss"
    transports: tuple[str, ...] = ("stdio", "http")
    local_file_fields: tuple[str, ...] = ()

    def validate(self, arguments: dict) -> dict:
        if self.effect == "write" and contains_redacted_values(arguments):
            raise ValueError(
                "Do not submit redacted result placeholders as write values. Use a scoped update that preserves hidden fields, or report the coverage gap."
            )
        try:
            value = self.arguments.model_validate(arguments)
        except ValidationError as exc:
            # Pydantic errors otherwise echo potentially sensitive input payloads.
            problems = [
                ".".join(map(str, item["loc"])) + ": " + item["type"]
                for item in exc.errors(include_input=False)
            ]
            raise ValueError(
                "Invalid operation arguments: " + "; ".join(problems)
            ) from None
        # Keep nested models intact for typed handlers and retain default values.
        return {name: getattr(value, name) for name in value.model_fields_set}

    def summary(self) -> dict:
        return {
            "operation_id": self.operation_id,
            "domain": self.domain,
            "category": self.category,
            "description": self.description,
            "effect": self.effect,
            "allowed_instance_types": list(self.allowed_instance_types),
            "destructive": self.destructive,
            "idempotent": self.idempotent,
            "transports": list(self.transports),
        }

    def describe(self) -> dict:
        return {
            **self.summary(),
            "input_schema": self.arguments.model_json_schema(),
            "example_arguments": self.example,
            "requirements": self.requirements,
            "server_support": "unknown",
            "response_contract": self.response_contract,
            "transports": list(self.transports),
            "backend": self.backend,
            "local_file_fields": list(self.local_file_fields),
        }


def arguments_for(
    handler: Callable, *, exclude: tuple[str, ...] = ()
) -> type[BaseModel]:
    hints = get_type_hints(handler, include_extras=True)
    return create_model(
        handler.__name__ + "Arguments",
        __base__=OperationArguments,
        **{
            name: (
                hints[name],
                parameter.default
                if parameter.default is not inspect.Parameter.empty
                else ...,
            )
            for name, parameter in inspect.signature(handler).parameters.items()
            if name not in exclude
        },
    )


def get_operations():
    # Lazy import keeps server construction independent of tool registration.
    from .operations_catalog import OPERATIONS

    return OPERATIONS


def get_operation(operation_id: str) -> Operation:
    try:
        return get_operations()[operation_id]
    except (KeyError, TypeError):
        raise ValueError("Unknown operation_id. Use search_operations.") from None


def require_operation(
    operation_id: str, effect: Effect, instance_type: InstanceType
) -> Operation:
    operation = get_operation(operation_id)
    if operation.effect != effect:
        raise ValueError(
            f"Operation '{operation_id}' requires the {operation.effect} dispatcher."
        )
    if instance_type not in operation.allowed_instance_types:
        raise ValueError(
            f"Operation '{operation_id}' is unavailable for instance type '{instance_type}'. Use switch_instance."
        )
    return operation


def make_catalog(operations: list[Operation]):
    result = {operation.operation_id: operation for operation in operations}
    if len(result) != len(operations):
        raise ValueError("Duplicate operation_id")
    return MappingProxyType(result)


def require_transport(operation: Operation, arguments: dict, is_http: bool) -> None:
    transport = "http" if is_http else "stdio"
    if transport not in operation.transports:
        raise ValueError(
            f"Operation '{operation.operation_id}' requires local stdio authentication; HTTP delegated tokens are not supported."
        )
    if is_http and any(arguments.get(field) for field in operation.local_file_fields):
        raise ValueError(
            "Local-file upload/download is unavailable in HTTP mode because it accesses the MCP host filesystem. Use stdio."
        )
