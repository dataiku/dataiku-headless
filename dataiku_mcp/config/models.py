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

"""Shared configuration models."""

from dataclasses import dataclass, field
from typing import Annotated

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)


@dataclass(frozen=True)
class DSSInstance:
    name: str
    url: str
    no_check_certificate: bool
    source: str
    api_key: str | None = field(default=None, repr=False)
    api_ticket: str | None = field(default=None, repr=False)
    encrypted_rpc_cert_path: str | None = field(default=None, repr=False)
    description: str = ""


NonEmptyString = Annotated[str, StringConstraints(min_length=1)]


class _StrictConfigModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        hide_input_in_errors=True,
    )


class _DSSInstanceConfig(_StrictConfigModel):
    url: NonEmptyString
    no_check_certificate: bool = False
    description: str = ""


class StdioDSSInstanceConfig(_DSSInstanceConfig):
    api_key: NonEmptyString | None = Field(default=None, repr=False)
    api_ticket: NonEmptyString | None = Field(default=None, repr=False)

    @model_validator(mode="after")
    def validate_credentials(self) -> "StdioDSSInstanceConfig":
        if (self.api_key is None) == (self.api_ticket is None):
            raise ValueError("Exactly one of api_key or api_ticket must be provided")
        return self

    def to_instance(
        self,
        name: str,
        *,
        source: str = "config",
        encrypted_rpc_cert_path: str | None = None,
    ) -> DSSInstance:
        return DSSInstance(
            name=name,
            url=self.url,
            api_key=self.api_key,
            api_ticket=self.api_ticket,
            encrypted_rpc_cert_path=encrypted_rpc_cert_path,
            no_check_certificate=self.no_check_certificate,
            source=source,
            description=self.description,
        )


class StdioConfig(_StrictConfigModel):
    default_instance: str | None = None
    dss_instances: dict[NonEmptyString, StdioDSSInstanceConfig] = Field(
        default_factory=dict
    )

    @model_validator(mode="after")
    def validate_default_instance(self) -> "StdioConfig":
        if self.default_instance == "":
            self.default_instance = None
        if (
            self.default_instance is not None
            and self.default_instance not in self.dss_instances
        ):
            raise ValueError(
                f"Default instance '{self.default_instance}' was not found in "
                f"dss_instances. Available: {list(self.dss_instances)}"
            )
        return self
