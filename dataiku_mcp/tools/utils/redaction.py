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

# Plugin / structured-agent parameter entries carry the secret INLINE as a
# sibling of its own metadata, e.g. ``{"key": "api_key", "value": "sk-live-…",
# "secret": true}`` or a typed param ``{"name": "token", "value": "…",
# "type": "PASSWORD"}`` (plugin param reference:
# https://doc.dataiku.com/dss/latest/plugins/reference/params.html). The
# name-only heuristic gets these exactly backwards: it redacts the ``key`` and
# ``secret`` metadata NAMES while leaving ``value`` — the actual secret —
# exposed, and destroys the metadata a reviewer needs to verify wiring. So a
# dict recognized structurally as a param entry keeps its key/secret/type
# metadata verbatim, and its ``value`` sibling is masked only when the entry is
# actually secret (``secret: true`` or a password/credential type).
_SECRET_PARAM_TYPES = frozenset({"password", "credential_request", "credentials"})
# The value field masked on a secret param entry.
_PARAM_VALUE_KEY = "value"
# Metadata that must survive verbatim on a param entry so it stays verifiable
# (which parameter is set, whether it IS secret, its declared type/name).
_PRESERVED_PARAM_KEYS = frozenset({"key", "secret", "type", "name"})


def _is_param_entry(value: dict) -> bool:
    """True if ``value`` looks like a DSS param entry carrying its own value.

    The two shapes are ``{"key": …, "value": …, "secret": bool}`` (structured
    agent / plugin param) and ``{"name": …, "value": …, "type": str}`` (typed
    plugin param). Recognizing the entry by SHAPE lets redaction preserve the
    key/secret/type metadata instead of the name heuristic nuking it — for both
    secret and non-secret entries.
    """
    if _PARAM_VALUE_KEY not in value:
        return False
    return isinstance(value.get("secret"), bool) or isinstance(value.get("type"), str)


def _param_entry_is_secret(value: dict) -> bool:
    """True if a param entry's ``value`` field holds a secret to be masked."""
    if value.get("secret") is True:
        return True
    declared_type = value.get("type")
    if isinstance(declared_type, str):
        normalized = declared_type.strip().lower()
        if (
            normalized in _SECRET_PARAM_TYPES
            or "credential" in normalized
            or "password" in normalized
        ):
            return True
    return False


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

    Redaction is name-driven for ordinary keys but STRUCTURE-aware for inline
    secret param entries (``{key, value, secret: true}`` / typed password params):
    there the ``value`` sibling is masked and the key/secret/type metadata is
    preserved. Otherwise structure is preserved and non-sensitive data is
    untouched. Lists are walked element-wise; scalars pass through.
    """
    if isinstance(value, dict):
        param_entry = _is_param_entry(value)
        mask_value = param_entry and _param_entry_is_secret(value)
        redacted = {}
        for key, item in value.items():
            key_str = str(key)
            if param_entry and key_str == _PARAM_VALUE_KEY:
                redacted[key] = (
                    placeholder if mask_value else redact_sensitive_values(item, placeholder)
                )
            elif param_entry and key_str in _PRESERVED_PARAM_KEYS:
                redacted[key] = item
            elif is_sensitive_key(key_str):
                redacted[key] = placeholder
            else:
                redacted[key] = redact_sensitive_values(item, placeholder)
        return redacted

    if isinstance(value, list):
        return [redact_sensitive_values(item, placeholder) for item in value]

    return value
