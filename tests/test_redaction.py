"""Contract tests for the single field-name secret redactor."""

from dataiku_mcp.tools.utils.redaction import (
    CONNECTION_REDACTION,
    VARIABLE_REDACTION,
    is_sensitive_key,
    redact_sensitive_values,
)


def test_common_credential_keys_are_sensitive():
    keys = (
        "clientSecret",
        "myApiKey",
        "AWS_ACCESS_KEY_ID",
        "authorization",
        "Bearer_Token",
        "db_password",
        "privateKey",
        "credentials",
        "sessionToken",
        "refresh_token",
        "auth",
        "key",
        "token",
    )
    assert all(is_sensitive_key(key) for key in keys)


def test_token_metadata_is_not_mistaken_for_a_credential():
    for key in ("maxTokens", "tokenizer", "tokenBudget", "tokenCount", "tokens"):
        assert not is_sensitive_key(key), key


def test_other_innocent_lookalikes_survive():
    for key in ("author", "keyspace", "monkey", "authority_name", "description"):
        assert not is_sensitive_key(key), key


def test_recursive_redaction_preserves_structure_and_marker_choice():
    payload = {
        "env": "prod",
        "clientSecret": "shhh",
        "nested": {"access_token": "abc", "tokenBudget": 1000},
        "list": [{"password": "p"}, {"keyspace": "public"}],
    }
    out = redact_sensitive_values(payload)
    assert out == {
        "env": "prod",
        "clientSecret": VARIABLE_REDACTION,
        "nested": {"access_token": VARIABLE_REDACTION, "tokenBudget": 1000},
        "list": [{"password": VARIABLE_REDACTION}, {"keyspace": "public"}],
    }
    assert redact_sensitive_values(
        {"password": "p"}, CONNECTION_REDACTION
    ) == {"password": CONNECTION_REDACTION}


def test_ordinary_value_type_dicts_are_not_treated_as_secret_params():
    # A plain {value, type} pair (e.g. a project variable) has no credential-shaped
    # field name, so nothing is masked — the field-name-only heuristic never
    # false-positives on this common shape.
    ordinary = {"value": "0.2", "type": "STRING"}
    assert redact_sensitive_values(ordinary) == ordinary
