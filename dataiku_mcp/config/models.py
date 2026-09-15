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
from typing import Annotated, Literal

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
    api_key: str = field(repr=False)
    no_check_certificate: bool
    source: str
    description: str = ""
    delegated_audience: str = ""
    delegated_scope: str = ""


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
    api_key: NonEmptyString = Field(repr=False)

    def to_instance(
        self,
        name: str,
        *,
        source: str = "config",
    ) -> DSSInstance:
        return DSSInstance(
            name=name,
            url=self.url,
            api_key=self.api_key,
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


class HTTPServerConfig(_StrictConfigModel):
    host: NonEmptyString
    port: int
    path: NonEmptyString
    public_url: str = ""


class GenericOIDCInteractiveLoginConfig(_StrictConfigModel):
    client_id: NonEmptyString
    client_secret: NonEmptyString = Field(repr=False)


class GenericOIDCDelegationConfig(_StrictConfigModel):
    token_endpoint: NonEmptyString
    client_id: NonEmptyString
    client_secret: NonEmptyString = Field(repr=False)


class GenericOIDCAuthConfig(_StrictConfigModel):
    provider: Literal["generic_oidc"]
    issuer: NonEmptyString
    jwks_uri: NonEmptyString
    required_audience: NonEmptyString
    required_scope: NonEmptyString
    interactive_login: GenericOIDCInteractiveLoginConfig | None = None
    delegation: GenericOIDCDelegationConfig


class EntraAuthConfig(_StrictConfigModel):
    provider: Literal["entra"]
    tenant_id: NonEmptyString
    client_id: NonEmptyString
    client_secret: NonEmptyString = Field(repr=False)
    required_scope: NonEmptyString
    interactive_login: bool = False

    @property
    def issuer(self) -> str:
        return f"https://login.microsoftonline.com/{self.tenant_id}/v2.0"

    @property
    def jwks_uri(self) -> str:
        return f"https://login.microsoftonline.com/{self.tenant_id}/discovery/v2.0/keys"

    @property
    def required_audience(self) -> str:
        return self.client_id

    @property
    def token_endpoint(self) -> str:
        return f"https://login.microsoftonline.com/{self.tenant_id}/oauth2/v2.0/token"


HTTPAuthConfig = Annotated[
    EntraAuthConfig | GenericOIDCAuthConfig,
    Field(discriminator="provider"),
]


class HTTPDSSInstanceConfig(_DSSInstanceConfig):
    delegated_scope: NonEmptyString
    delegated_audience: NonEmptyString | None = None

    def to_instance(self, name: str) -> DSSInstance:
        return DSSInstance(
            name=name,
            url=self.url,
            api_key="",
            no_check_certificate=self.no_check_certificate,
            source="http",
            description=self.description,
            delegated_audience=self.delegated_audience or "",
            delegated_scope=self.delegated_scope,
        )


class HTTPConfig(_StrictConfigModel):
    server: HTTPServerConfig
    auth: HTTPAuthConfig
    dss_instances: dict[NonEmptyString, HTTPDSSInstanceConfig] = Field(min_length=1)
    user_selections: dict[
        NonEmptyString,
        dict[NonEmptyString, NonEmptyString],
    ] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_provider_configuration(self) -> "HTTPConfig":
        interactive_login_enabled = (
            self.auth.interactive_login
            if self.auth.provider == "entra"
            else self.auth.interactive_login is not None
        )
        if interactive_login_enabled and not self.server.public_url:
            raise ValueError(
                "server.public_url is required when auth.interactive_login is enabled"
            )

        if self.auth.provider == "entra":
            invalid_instances = [
                name
                for name, instance in self.dss_instances.items()
                if "delegated_audience" in instance.model_fields_set
            ]
            if invalid_instances:
                raise ValueError(
                    "delegated_audience must be omitted for Entra DSS instances: "
                    f"{sorted(invalid_instances)}"
                )
        else:
            missing_instances = [
                name
                for name, instance in self.dss_instances.items()
                if instance.delegated_audience is None
            ]
            if missing_instances:
                raise ValueError(
                    "delegated_audience is required for generic OIDC DSS instances: "
                    f"{sorted(missing_instances)}"
                )
        return self
