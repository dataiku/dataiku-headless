"""Tests for the project-scoped 401 (unknown / inaccessible project) handler.

Regression coverage for a live failure where `dku project inspect <NAME>` (the
display name instead of the project key) reported "Authentication failed — check
your API key", sending an agent into a 6-step re-auth loop on a perfectly valid
key. DSS returns 401/Unauthorized — never 404 — for an unknown or inaccessible
project and refuses to reveal which, so the fix must NOT blame the API key.
"""

from __future__ import annotations

from dku_cli.errors import _handle_project_access_denied

# The exact string DSS returns for an unknown OR inaccessible project. Verified
# live on DSS 14.6: get_project(<name>).get_metadata() and .list_datasets() both
# raise this when given the wrong identifier (e.g. the display name).
DSS_PERM_MSG = (
    "com.dataiku.dip.exceptions.UnauthorizedException: "
    "Failed to read project permissions"
)


def test_matches_exact_dss_permission_message_without_key():
    """Fires on the DSS message alone, so EVERY project-scoped command (dataset,
    recipe, scenario…) benefits — not only the ones that thread a project key."""
    result = _handle_project_access_denied(DSS_PERM_MSG)
    assert result is not None
    message, details = result
    joined = "\n".join(details)
    # Must NOT blame the API key or send the agent to re-authenticate.
    assert "check your API key" not in (message + joined)
    assert "NOT an API-key problem" in joined
    assert "Do NOT run" in joined
    # Must teach key-vs-name and point at the recovery command.
    assert "KEY" in joined and "NAME" in joined
    assert "dku project list" in joined


def test_names_the_project_when_key_supplied():
    """With the key threaded through, the message names the offending project
    and tells the agent exactly how to find the right key."""
    result = _handle_project_access_denied(DSS_PERM_MSG, project_key="AdvisorGPT")
    assert result is not None
    message, details = result
    assert "Project 'AdvisorGPT'" in message
    assert any("Find the row whose NAME is 'AdvisorGPT'" in d for d in details)


def test_named_project_401_matches_even_without_permission_phrase():
    """When the caller named a project, ANY 401/Unauthorized is the project-access
    case (a genuinely bad key is caught earlier as Unknown API Key). This
    future-proofs the wired commands against DSS rewording the permissions text."""
    for msg in (
        "com.dataiku.dip.exceptions.UnauthorizedException: something new",
        "HTTP 401: Unauthorized",
    ):
        assert _handle_project_access_denied(msg, project_key="PROJ") is not None, msg


def test_generic_401_without_key_does_not_match():
    """Without a project key we only claim project-not-found on the specific DSS
    signal — an unrelated 401 must fall through to normal auth handling so we
    don't mislabel a real instance-level authz failure."""
    assert _handle_project_access_denied("HTTP 401: Unauthorized") is None
    assert _handle_project_access_denied("Some 401 error") is None


def test_unrelated_error_returns_none():
    assert _handle_project_access_denied("ValueError: bad input") is None
    assert _handle_project_access_denied("NotFoundException: dataset x") is None


def test_does_not_claim_project_not_found_for_invalid_api_key():
    """A genuinely invalid key (NotAuthenticatedException / Unknown API Key) has
    neither '401' nor 'Unauthorized' in its message, so this handler stays out of
    the way and the dedicated invalid-key handler owns it — even if a project key
    happens to be in play."""
    msg = "com.dataiku.dip.exceptions.NotAuthenticatedException: Unknown API Key"
    assert _handle_project_access_denied(msg) is None
    assert _handle_project_access_denied(msg, project_key="PROJ") is None
