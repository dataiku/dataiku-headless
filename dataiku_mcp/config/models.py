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
    api_key: str
    no_check_certificate: bool
    source: str
    description: str = ""
    delegated_audience: str = ""
    delegated_scope: str = ""


@dataclass
class StdioConfig:
    """Persisted Dataiku instance profiles and their startup default."""

    default_instance: str | None = None
    dss_instances: dict[str, DSSInstance] = field(default_factory=dict)


NonEmptyString = Annotated[str, StringConstraints(min_length=1)]


class _StrictHTTPModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        hide_input_in_errors=True,
    )


class HTTPServerConfig(_StrictHTTPModel):
    host: NonEmptyString
    port: int
    path: NonEmptyString
    public_url: str = ""


class GenericOIDCInteractiveLoginConfig(_StrictHTTPModel):
    client_id: NonEmptyString
    client_secret: NonEmptyString = Field(repr=False)


class GenericOIDCDelegationConfig(_StrictHTTPModel):
    token_endpoint: NonEmptyString
    client_id: NonEmptyString
    client_secret: NonEmptyString = Field(repr=False)


class GenericOIDCAuthConfig(_StrictHTTPModel):
    provider: Literal["generic_oidc"]
    issuer: NonEmptyString
    jwks_uri: NonEmptyString
    required_audience: NonEmptyString
    required_scope: NonEmptyString
    interactive_login: GenericOIDCInteractiveLoginConfig | None = None
    delegation: GenericOIDCDelegationConfig


class EntraAuthConfig(_StrictHTTPModel):
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


class HTTPDSSInstanceConfig(_StrictHTTPModel):
    url: NonEmptyString
    delegated_scope: NonEmptyString
    delegated_audience: NonEmptyString | None = None
    no_check_certificate: bool = False
    description: str = ""


class HTTPConfig(_StrictHTTPModel):
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


class NoConfiguredInstancesError(ValueError):
    """Raised when no Dataiku instances are available."""


class NoActiveInstanceError(ValueError):
    """Raised when instances exist but none is selected."""
