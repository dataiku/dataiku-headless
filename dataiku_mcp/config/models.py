"""Shared configuration models."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class DSSInstance:
    name: str
    url: str
    api_key: str
    no_check_certificate: bool
    source: str
    description: str = ""
    jwt_audience: str = ""
    jwt_scope: str = ""


@dataclass
class StdioConfig:
    """Persisted Dataiku instance profiles and their startup default."""

    default_instance: str | None = None
    dss_instances: dict[str, DSSInstance] = field(default_factory=dict)


@dataclass(frozen=True)
class HTTPServerConfig:
    host: str
    port: int
    path: str
    public_url: str = ""


@dataclass(frozen=True)
class HTTPInteractiveAuthConfig:
    client_id: str
    client_secret: str = field(repr=False)
    tenant_id: str = ""


@dataclass(frozen=True)
class HTTPAuthConfig:
    provider: str
    issuer: str
    jwks_uri: str
    audience: str
    scope: str
    interactive: HTTPInteractiveAuthConfig | None = None


@dataclass(frozen=True)
class HTTPTokenExchangeConfig:
    url: str
    client_id: str
    client_secret: str = field(repr=False)


@dataclass
class HTTPConfig:
    server: HTTPServerConfig
    auth: HTTPAuthConfig
    token_exchange: HTTPTokenExchangeConfig
    dss_instances: dict[str, DSSInstance]
    user_selections: dict[str, dict[str, str]] = field(default_factory=dict)


class NoConfiguredInstancesError(ValueError):
    """Raised when no Dataiku instances are available."""


class NoActiveInstanceError(ValueError):
    """Raised when instances exist but none is selected."""
