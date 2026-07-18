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

# Separators that hide the shape of a credential key (``AWS_ACCESS_KEY_ID``,
# ``client-secret``, ``api.key``) are stripped before matching so the heuristic
# sees one contiguous lowercase token.
_SEPARATORS = str.maketrans("", "", "_-.")

# A normalized key is sensitive if it CONTAINS any of these fragments. Chosen so
# that real-world credential keys — ``clientSecret``, ``myApiKey``,
# ``AWS_ACCESS_KEY_ID``, ``authorization``, ``Bearer_Token`` — all match, and so
# that the old connections.py pattern set (apikey/accesskey/credential(s)/
# password/privatekey/secret(key)/(session)token exact + *password/*privatekey/
# *secretkey/*sessiontoken/*credential/*token suffixes) is a strict subset.
_SENSITIVE_SUBSTRINGS = (
    "password",
    "passwd",
    "secret",
    "token",
    "credential",
    "apikey",
    "accesskey",
    "privatekey",
    "keystore",
    "authorization",
    "bearer",
)

# Fragments too short to use as a substring without nuking innocent keys: ``key``
# would flag ``keyspace``/``monkey`` and ``auth`` would flag ``author``. They
# redact only on an EXACT normalized match.
_SENSITIVE_EXACT_KEYS = frozenset({"auth", "key"})


def _normalize_key(key: str) -> str:
    """Lowercase and drop ``_ - .`` separators so key shape survives spelling."""
    return key.translate(_SEPARATORS).lower()


def is_sensitive_key(key: str) -> bool:
    """True if ``key`` names a password/secret/token/key/credential value."""
    normalized = _normalize_key(key)
    if normalized in _SENSITIVE_EXACT_KEYS:
        return True
    return any(fragment in normalized for fragment in _SENSITIVE_SUBSTRINGS)


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
