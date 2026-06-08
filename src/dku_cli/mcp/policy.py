"""Command policy for the ``dku_exec`` tool.

In the multi-tenant server the *real* authorization boundary is the per-token
DSS API key's own permissions plus the bubblewrap sandbox — not these checks.
What lives here is accident prevention, NOT a security control:

- ``sanitize`` removes a literal ``--dangerous`` flag so an agent does not
  casually flip the CLI's tier-guard UX off. It is not a security boundary.
"""

from __future__ import annotations

import re

# Match ``--dangerous`` only as a standalone token (not ``--dangerousness``).
_DANGEROUS = re.compile(r"(?<!\S)--dangerous(?!\S)")


def sanitize(commands: str) -> str:
    """Remove the global ``--dangerous`` flag from any command in the script."""
    return _DANGEROUS.sub("", commands)
