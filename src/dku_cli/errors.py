"""Error handling: dataikuapi exceptions to user-friendly messages + exit codes.

Exit codes:
  1 — General DSS API error
  2 — Authentication / authorization failure (401, 403)
  3 — Resource not found (404)
  4 — Connection failure (cannot reach DSS)
"""

from __future__ import annotations

import json
import sys

from dku_cli.output import error, get_error_format


class AuthError(Exception):
    """Raised when DSS credentials cannot be resolved."""


def exit_with_error(
    message: str,
    *,
    code: str = "cli_error",
    details: list[str] | None = None,
    status: int = 1,
) -> None:
    """Render a single error payload and exit."""
    details = details or []

    if get_error_format() == "json":
        payload = {
            "error": {
                "code": code,
                "message": message,
                "details": details,
                "exit_code": status,
            }
        }
        print(json.dumps(payload, indent=2), file=sys.stderr)
    else:
        error(message)
        for line in details:
            error(line)

    sys.exit(status)


def is_not_found_error(e: Exception) -> bool:
    """Return whether an exception represents a DSS not-found condition."""
    msg = str(e)
    return (
        "NotFoundException" in msg
        or "does not exist" in msg
        or "404" in msg
        or "not found" in msg.lower()
    )


def is_already_exists_error(e: Exception) -> bool:
    """Return whether an exception represents a DSS already-exists condition."""
    msg = str(e).lower()
    return "already exists" in msg or "409" in msg or "duplicate" in msg


def is_connection_required_error(e: Exception) -> bool:
    """Return whether an exception indicates a missing managed connection for output creation.

    DSS throws this when a code recipe tries to auto-create an output dataset
    but no default managed connection is configured at the project level.
    """
    msg = str(e)
    return "creationInfo" in msg or "Need to create output dataset" in msg


def _handle_govern_validation(msg: str) -> tuple[str, list[str]] | None:
    """Parse Govern ValidationException messages into prescriptive guidance.

    Returns (message, details) or None if not a Govern validation error.
    """
    if "ValidationException" not in msg:
        return None

    import re

    # "Field `X` is a list in artifact: ar.N"
    m = re.search(r"Field `(\w+)` is a list in artifact", msg)
    if m:
        field = m.group(1)
        return (
            f"Field '{field}' is a list field — value must be a JSON array.",
            [
                f'Use: "{field}": ["value1", "value2"] (array), not "{field}": "value1" (string).',
                'Even single values must be wrapped: ["value"].',
                "Run: dku govern-blueprint fields <BLUEPRINT_ID> to see which fields are lists (marked with * in LIST column).",
            ],
        )

    # "Invalid type for field value: double" (date field given a number)
    if "Invalid type for field value: double" in msg:
        return (
            "Invalid field value type — DATE fields require ISO 8601 strings, not numbers.",
            [
                'Use: "start_date": "2025-01-15T00:00:00.000Z" (ISO 8601 string).',
                'Do NOT use epoch milliseconds like "start_date": 1704067200000.',
            ],
        )

    # "Invalid type for field value: map" (field given a dict instead of a scalar)
    if "Invalid type for field value: map" in msg:
        return (
            "Invalid field value type — field values must be plain strings/numbers, not objects.",
            [
                'Use: "field_name": "value" (plain value), not "field_name": {"value": "..."}.',
                'REFERENCE fields accept artifact IDs: "business_initiative": "ar.123".',
            ],
        )

    # "'X' for field ID 'Y' is not a valid category"
    m = re.search(r"'(.+?)' for field ID '(\w+)' is not a valid category", msg)
    if m:
        value, field = m.group(1), m.group(2)
        return (
            f"'{value}' is not a valid category for field '{field}'.",
            [
                f"Run: dku govern-blueprint fields <BLUEPRINT_ID> to see valid categories for '{field}'.",
                "Category values are case-sensitive and must match exactly.",
            ],
        )

    # "Cannot modify a sign-off on a not active step"
    if "not active step" in msg:
        return (
            "Cannot modify sign-off — the workflow step is not active.",
            [
                "Sign-off steps must be configured with feedback groups and approvers in the blueprint",
                "before they can be activated. Ask a Govern Architect to configure the workflow.",
                "Run: dku govern-signoff list <ARTIFACT_ID> to see existing sign-offs.",
            ],
        )

    return None


def handle_api_error(e: Exception) -> None:
    """Convert dataikuapi exceptions to friendly messages and exit."""
    msg = str(e)

    status = 1
    code = "api_error"
    details: list[str] = []

    # Govern-specific validation errors — prescriptive guidance
    govern_result = _handle_govern_validation(msg)
    if govern_result:
        exit_with_error(
            govern_result[0],
            code="govern_validation",
            details=govern_result[1],
            status=1,
        )

    # dataikuapi raises generic Exceptions with HTTP status info
    # Check "not found" before "unauthorized" — DSS wraps NotFoundException in UnauthorizedException
    if "NotFoundException" in msg or "does not exist" in msg:
        status = 3
        code = "not_found"
        details = [f"Not found: {msg}"]
    elif "404" in msg or "Not found" in msg.lower():
        status = 3
        code = "not_found"
        details = [f"Not found: {msg}"]
    elif "401" in msg or "Unauthorized" in msg:
        status = 2
        code = "auth_error"
        details = [
            "Authentication failed — check your API key.",
            "Run 'dku auth login' to re-authenticate.",
        ]
    elif "403" in msg or "Forbidden" in msg:
        status = 2
        code = "permission_denied"
        details = ["Permission denied — your API key lacks access to this resource."]
    elif "Connection" in msg or "connect" in msg.lower():
        status = 4
        code = "connection_error"
        details = [
            f"Cannot connect to DSS: {msg}",
            "Check the URL and ensure DSS is running.",
        ]
    elif is_already_exists_error(e):
        status = 1
        code = "already_exists"
        details = [
            f"Resource already exists: {msg}",
            "Use --if-not-exists to skip creation when the resource exists.",
            "Or delete it first with --yes to skip confirmation.",
        ]
    else:
        details = [f"DSS API error: {msg}"]

    exit_with_error(details[0], code=code, details=details[1:], status=status)
