"""Error handling: dataikuapi exceptions to user-friendly messages + exit codes.

Exit codes:
  1 — General DSS API error
  2 — Authentication / authorization failure (401, 403)
  3 — Resource not found (404)
  4 — Connection failure (cannot reach DSS)
"""

from __future__ import annotations

import sys

from dku_cli.output import error


class AuthError(Exception):
    """Raised when DSS credentials cannot be resolved."""


def handle_api_error(e: Exception) -> None:
    """Convert dataikuapi exceptions to friendly messages and exit."""
    msg = str(e)

    # dataikuapi raises generic Exceptions with HTTP status info
    # Check "not found" before "unauthorized" — DSS wraps NotFoundException in UnauthorizedException
    if "NotFoundException" in msg or "does not exist" in msg:
        error(f"Not found: {msg}")
        sys.exit(3)
    elif "404" in msg or "Not found" in msg.lower():
        error(f"Not found: {msg}")
        sys.exit(3)
    elif "401" in msg or "Unauthorized" in msg:
        error("Authentication failed — check your API key.")
        error("Run 'dku auth login' to re-authenticate.")
        sys.exit(2)
    elif "403" in msg or "Forbidden" in msg:
        error("Permission denied — your API key lacks access to this resource.")
        sys.exit(2)
    elif "Connection" in msg or "connect" in msg.lower():
        error(f"Cannot connect to DSS: {msg}")
        error("Check the URL and ensure DSS is running.")
        sys.exit(4)
    else:
        error(f"DSS API error: {msg}")
        sys.exit(1)
