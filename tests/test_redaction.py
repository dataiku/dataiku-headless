"""Tests for the shared secret-redaction heuristic.

The redaction rule keys off the *name* of a field, never its value, and is used
by both the connection tools and the project-variable tools. These tests pin the
common credential keys that must always be redacted, the innocent-but-similar
keys that must survive, and the backward-compatibility contract with the old
connections.py pattern set (its previous behavior must be a strict subset).
"""

from dataiku_mcp.tools.utils import redaction as r
from dataiku_mcp.tools.utils.redaction import (
    CONNECTION_REDACTION,
    VARIABLE_REDACTION,
    is_sensitive_key,
    redact_sensitive_values,
)


# --------------------------------------------------------------------------- #
# Keys that MUST be flagged as sensitive
# --------------------------------------------------------------------------- #
REDACTS = [
    # The regression cases from the finding: previously passed straight through.
    "clientSecret",
    "myApiKey",
    "AWS_ACCESS_KEY_ID",
    "authorization",
    "Bearer_Token",
    # A spread of separators / casings the normalizer must collapse.
    "client_secret",
    "client-secret",
    "api.key",
    "PASSWORD",
    "passwd",
    "db_passwd",
    "privateKey",
    "keystorePassword",
    "keystore",
    "sessionToken",
    "refresh_token",
    "credentials",
    "aws_secret_access_key",
    # Short exact-only fragments.
    "auth",
    "key",
]

# Keys that MUST survive untouched (substring collisions the exact-only rule
# and the fragment choice deliberately avoid).
KEEPS = [
    "author",
    "keyspace",
    "monkey",
    "description",
    "host",
    "region",
    "env",
    "name",
    "database",
    "authority_name",  # contains 'author', not a credential
]


def test_common_credential_keys_are_flagged():
    for key in REDACTS:
        assert is_sensitive_key(key), f"expected {key!r} to be sensitive"


def test_innocent_lookalike_keys_survive():
    for key in KEEPS:
        assert not is_sensitive_key(key), f"expected {key!r} to NOT be sensitive"


def test_normalizer_strips_dot_dash_underscore_and_lowercases():
    assert r._normalize_key("AWS_ACCESS-KEY.ID") == "awsaccesskeyid"


# --------------------------------------------------------------------------- #
# Backward-compat: the OLD connections.py pattern set is a strict subset
# --------------------------------------------------------------------------- #
def test_old_connections_pattern_set_is_a_subset():
    # The exact-normalized keys the old connections.py redactor flagged.
    old_exact = {
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
    for key in old_exact:
        assert is_sensitive_key(key), f"old exact key {key!r} regressed"
    # The old suffix rules: *password, *privatekey, *secretkey, *sessiontoken,
    # *credential, *token all redacted.
    for key in (
        "smtpPassword",
        "sshPrivateKey",
        "myClientSecretKey",
        "oauthSessionToken",
        "resolvedCredential",
        "accessToken",
    ):
        assert is_sensitive_key(key), f"old suffix key {key!r} regressed"


# --------------------------------------------------------------------------- #
# redact_sensitive_values: markers + structure
# --------------------------------------------------------------------------- #
def test_variable_marker_is_default_and_applied_recursively():
    payload = {
        "env": "prod",
        "clientSecret": "shhh",
        "nested": {"myApiKey": "abc", "region": "eu"},
        "list": [{"password": "p"}, {"keyspace": "public"}],
    }
    out = redact_sensitive_values(payload)
    assert out["env"] == "prod"
    assert out["clientSecret"] == VARIABLE_REDACTION
    assert out["nested"]["myApiKey"] == VARIABLE_REDACTION
    assert out["nested"]["region"] == "eu"
    assert out["list"][0]["password"] == VARIABLE_REDACTION
    assert out["list"][1]["keyspace"] == "public"  # innocent, survives


def test_connection_marker_is_preserved():
    payload = {"AWS_ACCESS_KEY_ID": "AKIA...", "host": "db.internal"}
    out = redact_sensitive_values(payload, CONNECTION_REDACTION)
    assert out["AWS_ACCESS_KEY_ID"] == CONNECTION_REDACTION
    assert out["host"] == "db.internal"
    # The two markers are distinct and unchanged.
    assert CONNECTION_REDACTION == "__DATAIKU_REDACTED__"
    assert VARIABLE_REDACTION == "***REDACTED***"


def test_scalars_and_non_dict_values_pass_through():
    assert redact_sensitive_values("plain") == "plain"
    assert redact_sensitive_values(42) == 42
    assert redact_sensitive_values(["a", "b"]) == ["a", "b"]
