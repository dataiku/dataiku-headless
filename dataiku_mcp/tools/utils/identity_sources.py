"""Validation for Dataiku DSS identity source types."""

from .validation import require_allowed_value

IDENTITY_SOURCE_TYPES = {
    "LOCAL",
    "LDAP",
    "AZURE_AD",
    "LOCAL_NO_AUTH",
    "CUSTOM",
    "PAM",
}


def require_identity_source_type(value: str, field_name: str = "source_type") -> str:
    """Require a supported raw DSS identity source type."""
    return require_allowed_value(value, field_name, IDENTITY_SOURCE_TYPES)
