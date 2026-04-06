"""Tests for Govern-specific prescriptive error messages."""

from __future__ import annotations

from dku_cli.errors import _handle_govern_validation


def test_list_field_error():
    msg = "ValidationException: Field `countries` is a list in artifact: ar.42"
    result = _handle_govern_validation(msg)
    assert result is not None
    assert "countries" in result[0]
    assert "array" in result[0].lower()
    assert any("govern-blueprint fields" in d for d in result[1])


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
    assert any("govern-blueprint fields" in d for d in result[1])


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
