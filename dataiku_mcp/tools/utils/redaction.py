"""The single field-name redaction helper for secret-bearing tool payloads.

One recursive function masks values whose *field name* conventionally carries a
credential. This is the only redaction implementation in the server: connection
info/tests, webapp settings, and project variables all consume it. Detection is
field-name only — no payload-shape heuristics — so it never false-positives on
ordinary ``{value, type}`` dictionaries.
"""

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


def redact_sensitive_values(value: Any, placeholder: str = VARIABLE_REDACTION) -> Any:
    """Recursively mask values whose field name signals a credential.

    Field-name detection only. Returns a new structure; the input is never mutated.
    """
    if isinstance(value, dict):
        return {
            key: (
                placeholder
                if is_sensitive_key(str(key))
                else redact_sensitive_values(item, placeholder)
            )
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_sensitive_values(item, placeholder) for item in value]
    return value
