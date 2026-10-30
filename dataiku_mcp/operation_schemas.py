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

"""Structural schemas for Govern operation adapters."""

from typing import Annotated, Any, Literal

from pydantic import Field, create_model, model_validator

from .operation_registry import OperationArguments
from .tools.utils.validation import PathSegment

NonEmpty = Annotated[str, Field(min_length=1)]


class UserContainer(OperationArguments):
    type: Literal["user"]
    login: PathSegment


class DeleteTimeSeriesArguments(OperationArguments):
    time_series_id: PathSegment
    min_timestamp: int | None = None
    max_timestamp: int | None = None
    delete_all: bool = False

    @model_validator(mode="after")
    def explicit_range(self):
        unbounded = self.min_timestamp is None and self.max_timestamp is None
        if unbounded != self.delete_all:
            raise ValueError("Use a timestamp range or delete_all=true, not both")
        if (
            self.min_timestamp is not None
            and self.max_timestamp is not None
            and self.min_timestamp > self.max_timestamp
        ):
            raise ValueError("min_timestamp must not exceed max_timestamp")
        return self


def govern_arguments(name, spec):
    if name == "delete_time_series_values":
        return DeleteTimeSeriesArguments
    kinds = {
        "string": str,
        "boolean": bool,
        "integer": int,
        "object": dict[str, Any],
        "list": list[Any],
        "any": Any,
    }
    fields = {}
    for param in spec.params:
        kind = PathSegment if param.path else kinds[param.kind]
        if param.kind == "string" and param.required and not param.path:
            kind = NonEmpty
        if param.name == "users_container":
            kind = UserContainer
        if param.name == "status":
            if name == "update_signoff_status":
                kind = Literal[
                    "NOT_STARTED",
                    "WAITING_FOR_FEEDBACK",
                    "WAITING_FOR_APPROVAL",
                    "APPROVED",
                    "REJECTED",
                    "ABANDONED",
                ]
            elif name in {"add_signoff_feedback", "update_signoff_feedback"}:
                kind = Literal["APPROVED", "MINOR_ISSUE", "MAJOR_ISSUE"]
            elif name in {"add_signoff_approval", "update_signoff_approval"}:
                kind = Literal["APPROVED", "REJECTED", "ABANDONED"]
        if not param.required:
            kind = kind | None
        description = param.description
        if param.kind in {"object", "list"}:
            description += " Backend-defined contents; inspect current definitions before mutation."
        constraints = {"ge": 1} if param.name in {"page_size", "max_results"} else {}
        fields[param.name] = (
            kind,
            Field(
                default=... if param.required else None,
                description=description,
                **constraints,
            ),
        )
    return create_model(name + "Arguments", __base__=OperationArguments, **fields)
