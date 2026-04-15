"""Tests for Govern-specific prescriptive error messages."""

from __future__ import annotations

from dku_cli.errors import _handle_govern_validation, _handle_invalid_api_key


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
    import dku_cli.errors as errors_mod

    monkeypatch.setattr(errors_mod, "_resolve_auth_context", lambda: (None, None))
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
