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
class DSSConfig:
    """Persisted Dataiku instance profiles and their startup default."""

    default_instance: str | None = None
    dss_instances: dict[str, DSSInstance] = field(default_factory=dict)


class NoConfiguredInstancesError(ValueError):
    """Raised when no Dataiku instances are available."""


class NoActiveInstanceError(ValueError):
    """Raised when instances exist but none is selected."""
