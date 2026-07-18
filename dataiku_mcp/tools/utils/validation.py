"""Shared validation helpers for tool modules."""


def require_non_empty_string(value: str, field_name: str) -> str:
    try:
        cleaned = value.strip()
    except Exception as exc:
        raise ValueError(f"'{field_name}' must be a non-empty string") from exc
    if not cleaned:
        raise ValueError(f"'{field_name}' must be a non-empty string")
    return cleaned


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


def require_allowed_value(value: str, field_name: str, allowed_values: set[str]) -> str:
    if value not in allowed_values:
        allowed = sorted(allowed_values)
        raise ValueError(
            f"Invalid '{field_name}': '{value}'. Allowed values: {allowed}"
        )
    return value
