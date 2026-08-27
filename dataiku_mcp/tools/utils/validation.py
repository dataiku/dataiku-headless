"""Shared validation helpers for tool modules."""

import re

_HEX_COLOR_PATTERN = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")


def require_non_empty_string(value: str, field_name: str) -> str:
    try:
        cleaned = value.strip()
    except Exception as exc:
        raise ValueError(f"'{field_name}' must be a non-empty string") from exc
    if not cleaned:
        raise ValueError(f"'{field_name}' must be a non-empty string")
    return cleaned


def require_non_empty_strings(values: list[str], field_name: str) -> list[str]:
    return [
        require_non_empty_string(value, f"{field_name}[{index}]")
        for index, value in enumerate(values)
    ]


def require_positive_int(value: int, field_name: str) -> int:
    if value is True or value is False:
        raise ValueError(f"'{field_name}' must be >= 1")
    try:
        if value < 1:
            raise ValueError(f"'{field_name}' must be >= 1")
    except TypeError as exc:
        raise ValueError(f"'{field_name}' must be >= 1") from exc
    return value


def require_non_negative_int(value: int, field_name: str) -> int:
    if value is True or value is False:
        raise ValueError(f"'{field_name}' must be >= 0")
    try:
        if value < 0:
            raise ValueError(f"'{field_name}' must be >= 0")
    except TypeError as exc:
        raise ValueError(f"'{field_name}' must be >= 0") from exc
    return value


def require_int_at_least(value: int, field_name: str, minimum: int) -> int:
    cleaned = require_positive_int(value, field_name)
    if cleaned < minimum:
        raise ValueError(f"'{field_name}' must be >= {minimum}")
    return cleaned


def require_int_in_range(
    value: int, field_name: str, minimum: int, maximum: int
) -> int:
    """Require an int within an inclusive range, for bounded inline waits and caps."""
    cleaned = require_int_at_least(value, field_name, minimum)
    if cleaned > maximum:
        raise ValueError(f"'{field_name}' must be <= {maximum}")
    return cleaned


def require_non_empty_list(values: list, field_name: str) -> list:
    if len(values) < 1:
        raise ValueError(f"'{field_name}' must be a non-empty list")
    return values


def require_allowed_value(value: str, field_name: str, allowed_values: set[str]) -> str:
    if value not in allowed_values:
        allowed = sorted(allowed_values)
        raise ValueError(
            f"Invalid '{field_name}': '{value}'. Allowed values: {allowed}"
        )
    return value


def require_fraction(value: float, field_name: str) -> float:
    if value is True or value is False:
        raise ValueError(f"'{field_name}' must be > 0 and < 1")
    try:
        cleaned = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"'{field_name}' must be > 0 and < 1") from exc
    if cleaned <= 0 or cleaned >= 1:
        raise ValueError(f"'{field_name}' must be > 0 and < 1")
    return cleaned


def require_hex_color(value: str, field_name: str) -> str:
    cleaned = require_non_empty_string(value, field_name)
    if not _HEX_COLOR_PATTERN.match(cleaned):
        raise ValueError(
            f"'{field_name}' must be a hex color in '#RGB' or '#RRGGBB' format"
        )
    return cleaned
