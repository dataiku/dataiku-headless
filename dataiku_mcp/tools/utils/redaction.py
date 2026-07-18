"""Shared redaction of sensitive values in tool payloads.

A single key-name heuristic (:func:`is_sensitive_key`) plus a recursive
replacer (:func:`redact_sensitive_values`) used by every tool that can echo
secret-bearing data back to a caller — connection info/tests and project
variables. The redaction placeholder is a parameter so each surface keeps its
own marker (connections use ``__DATAIKU_REDACTED__``; variables use
``***REDACTED***``) while sharing one detection rule.
"""

from typing import Any

# Marker written into connection info/test payloads (unchanged from the original
# connections.py behavior).
CONNECTION_REDACTION = "__DATAIKU_REDACTED__"
# Marker written into project-variable payloads.
VARIABLE_REDACTION = "***REDACTED***"

_SENSITIVE_EXACT_KEYS = {
    "apikey",
    "accesskey",
    "credentials",
    "password",
    "privatekey",
    "secret",
    "secretkey",
    "sessiontoken",
    "token",
    "resolvedawscredential",
    "resolvedbasiccredential",
    "resolvedoauth2credential",
}
_SENSITIVE_SUFFIXES = (
    "password",
    "privatekey",
    "secretkey",
    "sessiontoken",
)


def is_sensitive_key(key: str) -> bool:
    """True if ``key`` names a password/secret/token/key/credential value."""
    normalized = key.replace("_", "").replace("-", "").lower()
    if normalized in _SENSITIVE_EXACT_KEYS:
        return True

    if any(normalized.endswith(suffix) for suffix in _SENSITIVE_SUFFIXES):
        return True

    if normalized.endswith("credential"):
        return True

    if normalized.endswith("token"):
        return True

    return False


def redact_sensitive_values(value: Any, placeholder: str = VARIABLE_REDACTION) -> Any:
    """Recursively replace values whose *key* looks sensitive with ``placeholder``.

    Redaction keys off the key name, never the value, so structure is preserved
    and non-sensitive data is untouched. Lists are walked element-wise; scalars
    pass through.
    """
    if isinstance(value, dict):
        redacted = {}
        for key, item in value.items():
            if is_sensitive_key(str(key)):
                redacted[key] = placeholder
            else:
                redacted[key] = redact_sensitive_values(item, placeholder)
        return redacted

    if isinstance(value, list):
        return [redact_sensitive_values(item, placeholder) for item in value]

    return value
