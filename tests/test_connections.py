"""Tests for redacting sensitive connection details."""

import pytest

from dataiku_mcp.tools import connections


@pytest.mark.parametrize(
    "key",
    [
        "password",
        "clientPassword",
        "clientSecret",
        "openaiApiKey",
        "awsAccessKey",
        "userCredentials",
        "sshPrivateKey",
        "awsSecretKey",
        "sessionToken",
        "resolvedOAuth2Credential",
    ],
)
def test_redacts_sensitive_connection_fields(key):
    value = {
        "params": {key: "sensitive"},
        "resolvedParams": {key: "sensitive"},
    }

    assert connections._redact_sensitive_data(value) == {
        "params": {key: "__DATAIKU_REDACTED__"},
        "resolvedParams": {key: "__DATAIKU_REDACTED__"},
    }


@pytest.mark.parametrize("key", ["authorizationEndpoint", "tokenEndpoint"])
def test_preserves_non_sensitive_connection_fields(key):
    assert connections._redact_sensitive_data({key: "https://example.com"}) == {
        key: "https://example.com"
    }
