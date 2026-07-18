"""Shared, structure-aware redaction for secret-bearing tool payloads."""

import re
from typing import Any

CONNECTION_REDACTION = "__DATAIKU_REDACTED__"
VARIABLE_REDACTION = "***REDACTED***"

_SEPARATORS = str.maketrans("", "", "_-. ")
_SENSITIVE_SUBSTRINGS = (
    "password",
    "passwd",
    "secret",
    "credential",
    "apikey",
    "accesskey",
    "privatekey",
    "keystore",
    "authorization",
    "bearer",
)
_SENSITIVE_EXACT_KEYS = frozenset({"auth", "key", "token"})
_SECRET_PARAM_TYPES = frozenset({"password", "credential_request", "credentials"})
_PRESERVED_PARAM_KEYS = frozenset({"key", "secret", "type", "name"})


def _normalize_key(key: str) -> str:
    return key.translate(_SEPARATORS).lower()


def _camel_words(key: str) -> list[str]:
    """Split a key without treating ordinary token metadata as a credential.

    ``accessToken`` and ``refresh_token`` end in the singular word ``token``;
    ``maxTokens``, ``tokenBudget``, ``tokenCount`` and ``tokenizer`` do not.
    """
    separated = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", key)
    return [word.lower() for word in re.split(r"[^A-Za-z0-9]+", separated) if word]


def is_sensitive_key(key: str) -> bool:
    """Return whether a field name conventionally carries credential material."""
    normalized = _normalize_key(key)
    if normalized in _SENSITIVE_EXACT_KEYS:
        return True
    if any(fragment in normalized for fragment in _SENSITIVE_SUBSTRINGS):
        return True
    words = _camel_words(key)
    return bool(words and words[-1] == "token")


def _is_param_entry(value: dict) -> bool:
    if "value" not in value:
        return False
    return isinstance(value.get("secret"), bool) or isinstance(value.get("type"), str)


def _param_entry_is_secret(value: dict) -> bool:
    if value.get("secret") is True:
        return True
    declared_type = value.get("type")
    if not isinstance(declared_type, str):
        return False
    normalized = declared_type.strip().lower()
    return (
        normalized in _SECRET_PARAM_TYPES
        or "credential" in normalized
        or "password" in normalized
    )


def redact_sensitive_values(value: Any, placeholder: str = VARIABLE_REDACTION) -> Any:
    """Recursively mask secrets while preserving useful parameter metadata.

    Ordinary dictionaries use field-name detection. DSS plugin parameter entries
    carry secrecy metadata beside ``value``; for those shapes, this masks the value
    and retains ``key``/``name``/``type``/``secret`` so reviewers can verify wiring.
    """
    if isinstance(value, dict):
        param_entry = _is_param_entry(value)
        mask_value = param_entry and _param_entry_is_secret(value)
        redacted = {}
        for key, item in value.items():
            key_text = str(key)
            if param_entry and key_text == "value":
                redacted[key] = (
                    placeholder
                    if mask_value
                    else redact_sensitive_values(item, placeholder)
                )
            elif param_entry and key_text in _PRESERVED_PARAM_KEYS:
                redacted[key] = item
            elif is_sensitive_key(key_text):
                redacted[key] = placeholder
            else:
                redacted[key] = redact_sensitive_values(item, placeholder)
        return redacted
    if isinstance(value, list):
        return [redact_sensitive_values(item, placeholder) for item in value]
    return value
