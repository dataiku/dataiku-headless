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

"""Recursive credential redaction for backend operation results."""

from typing import Any
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

_CONNECTION_SECRET_REDACTION = "__DATAIKU_REDACTED__"
_SENSITIVE_SUFFIXES = (
    "apikey",
    "apikeys",
    "credential",
    "credentials",
    "password",
    "passwords",
    "secret",
    "secrets",
    "token",
    "tokens",
)
_SENSITIVE_EXACT_KEYS = (
    "key",
    "keypath",
    "authorization",
    "cookie",
    "setcookie",
)
_DIAGNOSTIC_KEYS = (
    "logs",
    "stacktrace",
    "traceback",
    "errordetails",
    "errormessage",
    "error",
    "errors",
)
_SENSITIVE_KEY_FRAGMENTS = (
    "accesskey",
    "appsecret",
    "keybase64data",
    "keyjsondata",
    "passphrase",
    "privatekey",
    "secretkey",
    "tokenkey",
)


def _is_sensitive_key(key: str, *, redact_diagnostics: bool = True) -> bool:
    normalized = key.replace("_", "").replace("-", "").lower()
    return (
        normalized in _SENSITIVE_EXACT_KEYS
        or (redact_diagnostics and normalized in _DIAGNOSTIC_KEYS)
        or normalized.endswith(_SENSITIVE_SUFFIXES)
        or any(fragment in normalized for fragment in _SENSITIVE_KEY_FRAGMENTS)
    )


def redact_sensitive_data(value: Any, *, redact_diagnostics: bool = True) -> Any:
    if isinstance(value, dict):
        # Header/property lists encode the sensitive name in a key/value pair.
        sensitive_pair = isinstance(value.get("key"), str) and _is_sensitive_key(
            value["key"], redact_diagnostics=False
        )
        redacted = {}
        for key, item in value.items():
            if _is_sensitive_key(str(key), redact_diagnostics=redact_diagnostics) or (
                key == "value" and sensitive_pair
            ):
                redacted[key] = _CONNECTION_SECRET_REDACTION
            else:
                redacted[key] = redact_sensitive_data(
                    item, redact_diagnostics=redact_diagnostics
                )
        return redacted

    if isinstance(value, list):
        return [
            redact_sensitive_data(item, redact_diagnostics=redact_diagnostics)
            for item in value
        ]

    if isinstance(value, str) and value.startswith(("https://", "http://")):
        try:
            parts = urlsplit(value)
            query = parse_qsl(parts.query, keep_blank_values=True)
            if "@" in parts.netloc or any(_is_sensitive_key(key) for key, _ in query):
                host = parts.netloc.rsplit("@", 1)[-1]
                query = [
                    (
                        key,
                        _CONNECTION_SECRET_REDACTION
                        if _is_sensitive_key(key)
                        else item,
                    )
                    for key, item in query
                ]
                return urlunsplit(
                    (parts.scheme, host, parts.path, urlencode(query), parts.fragment)
                )
        except ValueError:
            return _CONNECTION_SECRET_REDACTION
    return value


def redact_api_test_queries(test_queries: Any) -> Any:
    """Redact API test queries while retaining saved header names for inspection."""
    redacted = redact_sensitive_data(test_queries)
    if not isinstance(test_queries, list) or not isinstance(redacted, list):
        return redacted

    for query, redacted_query in zip(test_queries, redacted):
        if not isinstance(query, dict) or not isinstance(redacted_query, dict):
            continue
        headers = query.get("headers")
        if not isinstance(headers, list):
            continue
        redacted_query["headers"] = _redact_api_test_headers(headers)
    return redacted


def _redact_api_test_headers(headers: list[Any]) -> list[Any]:
    result = []
    for header in headers:
        redacted = redact_sensitive_data(header)
        if isinstance(header, dict) and isinstance(redacted, dict):
            if isinstance(header.get("key"), str):
                redacted["key"] = header["key"]
            if "value" in header:
                redacted["value"] = _CONNECTION_SECRET_REDACTION
        result.append(redacted)
    return result


def contains_redacted_values(value: Any) -> bool:
    """Detect result placeholders that must never become replacement credentials."""
    if isinstance(value, str):
        return _CONNECTION_SECRET_REDACTION in value
    if isinstance(value, dict):
        return any(contains_redacted_values(item) for item in value.values())
    if isinstance(value, list):
        return any(contains_redacted_values(item) for item in value)
    return False
