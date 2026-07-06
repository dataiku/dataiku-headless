# Security Policy

## Supported versions

Security fixes land on the latest released version. Older versions do not
receive backports — upgrade to the latest release before reporting.

## Reporting a vulnerability

Please report vulnerabilities **privately** through GitHub Security Advisories:

- Open [a new advisory](https://github.com/dataiku/dku-headless/security/advisories/new)
  on `dataiku/dku-headless`.

Do **not** open a public issue or PR for a suspected vulnerability.

We aim to acknowledge a report within **5 business days** and to agree on a
disclosure timeline once the issue is confirmed. Please give us a reasonable
window to ship a fix before any public disclosure.

## Scope

This project is a headless control plane for Dataiku DSS. The primary trust
boundary is the DSS instance itself: `dku` acts with the permissions of the API
key it is given, and it never elevates beyond them.

The **MCP server** (`dku-mcp serve`) has its own threat model — in the
multi-tenant configuration the real authorization boundary is the per-token DSS
API key's own permissions plus the bubblewrap sandbox, not any application-level
allowlist. That model, and why command sanitization is accident-prevention
rather than a security control, is documented in code: see the module docstring
in [`src/dku_cli/mcp/policy.py`](src/dku_cli/mcp/policy.py).

Out of scope: issues that require an already-compromised DSS instance or a valid
API key that itself grants the demonstrated access.
