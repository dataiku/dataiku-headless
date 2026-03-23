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


def exit_with_error(message: str, *, code: str = "cli_error", details: list[str] | None = None, status: int = 1) -> None:
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


def handle_api_error(e: Exception) -> None:
    """Convert dataikuapi exceptions to friendly messages and exit."""
    msg = str(e)

    status = 1
    code = "api_error"
    details: list[str] = []

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
    else:
        details = [f"DSS API error: {msg}"]

    exit_with_error(details[0], code=code, details=details[1:], status=status)
