"""Tests for Govern-specific prescriptive error messages."""

from __future__ import annotations

from dku_cli.errors import (
    _handle_govern_field_save_npe,
    _handle_govern_field_type_enum,
    _handle_govern_validation,
    _handle_invalid_api_key,
)


def test_list_field_error():
    msg = "ValidationException: Field `countries` is a list in artifact: ar.42"
    result = _handle_govern_validation(msg)
    assert result is not None
    assert "countries" in result[0]
    assert "array" in result[0].lower()
    assert any("govern blueprint fields" in d for d in result[1])


def test_double_type_error():
    msg = "ValidationException: Invalid type for field value: double in artifact: ar.42"
    result = _handle_govern_validation(msg)
    assert result is not None
    assert "ISO 8601" in result[0]


def test_map_type_error():
    msg = "ValidationException: Invalid type for field value: map in artifact: ar.42"
    result = _handle_govern_validation(msg)
    assert result is not None
    assert "plain" in result[0].lower()


def test_invalid_category_error():
    msg = "ValidationException: 'United States' for field ID 'countries' is not a valid category for artifact `ar.42`"
    result = _handle_govern_validation(msg)
    assert result is not None
    assert "United States" in result[0]
    assert "countries" in result[0]
    assert any("govern blueprint fields" in d for d in result[1])


def test_not_active_step_error():
    msg = "ValidationException: Cannot modify a sign-off `SignoffId{artifactId='ar.5', stepId='ideation'}` on a not active step"
    result = _handle_govern_validation(msg)
    assert result is not None
    assert "not active" in result[0].lower()
    assert any("Architect" in d for d in result[1])


def test_non_govern_error_returns_none():
    msg = "NotFoundException: Project does not exist"
    result = _handle_govern_validation(msg)
    assert result is None


def test_invalid_api_key_with_unknown_key_message(monkeypatch):
    monkeypatch.setenv("DKU_URL", "http://example:8082")
    monkeypatch.setenv("DKU_PROFILE", "staging")
    msg = "com.dataiku.dip.exceptions.NotAuthenticatedException: Unknown API Key"
    result = _handle_invalid_api_key(msg)
    assert result is not None
    message, details = result
    assert "DSS rejected" in message
    assert "http://example:8082" in message
    assert "staging" in message
    # Recovery line should include the URL the user tried so the agent can
    # copy-paste it without re-typing.
    joined = "\n".join(details)
    assert "dku auth login --url http://example:8082" in joined
    assert "<new-key>" in joined


def test_invalid_api_key_falls_back_when_no_url(monkeypatch):
    monkeypatch.delenv("DKU_URL", raising=False)
    monkeypatch.delenv("DKU_DSS_URL", raising=False)
    monkeypatch.delenv("DKU_PROFILE", raising=False)
    # Force config lookup to fail so we exercise the fallback path.
    # (_handle_invalid_api_key lives in _error_auth; errors re-exports it.)
    import dku_cli._error_auth as error_auth_mod

    monkeypatch.setattr(error_auth_mod, "_resolve_auth_context", lambda: (None, None))
    msg = "NotAuthenticatedException: Unknown API Key"
    result = _handle_invalid_api_key(msg)
    assert result is not None
    message, details = result
    # When no URL is known, the message should call that out instead of
    # printing 'None' or crashing.
    assert "<unknown URL" in message
    assert any("dku auth login" in d for d in details)


def test_invalid_api_key_returns_none_for_other_errors():
    assert _handle_invalid_api_key("NotFoundException: Project does not exist") is None
    assert _handle_invalid_api_key("ValidationException: bad field") is None
    assert _handle_invalid_api_key("403 Forbidden") is None


def test_govern_field_type_enum_string():
    msg = (
        "java.lang.IllegalArgumentException: No enum constant "
        "com.dataiku.gh.core.models.fields.FieldType.STRING"
    )
    result = _handle_govern_field_type_enum(msg)
    assert result is not None
    message, details = result
    assert "'STRING'" in message
    joined = "\n".join(details)
    assert "TEXT" in joined
    assert "CATEGORY" in joined
    assert "JSON" in joined
    assert "STRING' → use 'TEXT'" in joined
    assert "govern-field-types.md" in joined


def test_govern_field_type_enum_other_value():
    msg = "IllegalArgumentException: No enum constant FieldType.MARKDOWN"
    result = _handle_govern_field_type_enum(msg)
    assert result is not None
    assert "'MARKDOWN'" in result[0]


def test_govern_field_type_enum_returns_none_for_other_errors():
    assert _handle_govern_field_type_enum("NotFoundException: nope") is None
    assert _handle_govern_field_type_enum("ValidationException: bad") is None


def test_govern_field_save_npe_matches():
    msg = (
        "java.lang.NullPointerException: Cannot invoke "
        '"com.google.gson.JsonObject.get(String).getAsString()" '
        "because the return value of "
        '"com.google.gson.JsonObject.get(String)" is null'
    )
    result = _handle_govern_field_save_npe(msg)
    assert result is not None
    message, details = result
    assert "fieldDefinitions" in message
    joined = "\n".join(details)
    assert "id" in joined
    assert "fieldType" in joined
    assert "sourceType" in joined
    assert "label" in joined
    assert "'name' instead of 'id'" in joined


def test_govern_field_save_npe_returns_none_for_other_errors():
    assert _handle_govern_field_save_npe("NotFoundException: nope") is None
    assert _handle_govern_field_save_npe("NullPointerException: something else") is None
