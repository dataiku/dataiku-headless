# Copyright 2026 Dataiku SAS
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

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
        "awsAccessKeyId",
        "userCredentials",
        "privateKeyB64",
        "sshPrivateKeyB64",
        "awsSecretKeyB64",
        "keyPassphrase",
        "appSecretContent",
        "keyJsonData",
        "keyPath",
        "keyBase64Data",
        "sessionToken",
        "token_key",
        "resolvedOAuth2Credential",
        "key",
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


@pytest.mark.parametrize(
    "key", ["authorizationEndpoint", "encryptionKeyId", "tokenEndpoint"]
)
def test_preserves_non_sensitive_connection_fields(key):
    assert connections._redact_sensitive_data({key: "https://example.com"}) == {
        key: "https://example.com"
    }


def test_diagnostics_can_be_preserved_without_exposing_credentials():
    value = {
        "error": True,
        "errors": [{"message": "Import failed", "password": "sensitive"}],
        "logs": {"lines": ["Import failed"], "apiKey": "sensitive"},
    }
    assert connections._redact_sensitive_data(value, redact_diagnostics=False) == {
        "error": True,
        "errors": [{"message": "Import failed", "password": "__DATAIKU_REDACTED__"}],
        "logs": {
            "lines": ["Import failed"],
            "apiKey": "__DATAIKU_REDACTED__",
        },
    }
    assert connections._redact_sensitive_data(value) == {
        key: "__DATAIKU_REDACTED__" for key in value
    }
