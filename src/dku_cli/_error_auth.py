"""Auth-guidance branch of the error mapper — extracted from ``errors.py``.

``dku_cli.errors`` remains the public error-handling surface
(``handle_api_error`` / ``handle_errors`` / ``exit_with_error`` / ``AuthError``);
this module only hosts the invalid-API-key and project-access-denied
detectors so ``errors.py`` stays within the size ratchet.
"""

from __future__ import annotations


def _resolve_auth_context() -> tuple[str | None, str | None]:
    """Best-effort resolution of (url, profile) for prescriptive auth errors.

    Reads from env vars first (so explicit overrides win), then falls back to
    the CLI's TOML config (active profile + its url). Returns ``(None, None)``
    if neither source is available — callers should handle the missing case.
    """
    import os

    env_url = os.environ.get("DKU_URL") or os.environ.get("DKU_DSS_URL")
    env_profile = os.environ.get("DKU_PROFILE")

    config_url: str | None = None
    config_profile: str | None = None
    try:
        from dku_cli.config import get_active_profile, get_profile_config

        config_profile = get_active_profile()
        config_url = (get_profile_config(config_profile) or {}).get("url")
    except Exception:  # quality-ratchet: allow-broad-exception
        # Config read can fail for many benign reasons (no config file, malformed
        # TOML, platformdirs path issue). Don't let auth-error reporting cascade.
        pass

    return env_url or config_url, env_profile or config_profile


def _handle_invalid_api_key(msg: str) -> tuple[str, list[str]] | None:
    """Detect an invalid/unknown API key error and return prescriptive guidance.

    DSS rejects unknown or rotated API keys with messages like
    ``com.dataiku.dip.exceptions.NotAuthenticatedException: Unknown API Key``.
    The base 401/Unauthorized branch in ``handle_api_error`` doesn't catch this
    because the message contains neither ``401`` nor ``Unauthorized`` — so
    without this helper the user just sees the raw Java exception.

    Returns (message, details) or None if the input doesn't match.
    """
    if "NotAuthenticatedException" not in msg and "Unknown API Key" not in msg:
        return None

    url, profile = _resolve_auth_context()
    url_display = url or (
        "<unknown URL — set DKU_URL or run `dku auth login --url ...`>"
    )
    profile_display = profile or "default"

    recover_args = []
    if url:
        recover_args.append(f"--url {url}")
    recover_args.append("--api-key <new-key>")
    recover_cmd = "dku auth login " + " ".join(recover_args)

    return (
        f"DSS rejected the stored API key "
        f"(URL: {url_display}, profile: {profile_display}).",
        [
            "The stored credentials are no longer valid — the key may have been",
            "rotated, deleted, or never had access to this DSS instance.",
            "",
            "Recover with:",
            f"  {recover_cmd}",
            "",
            "Or for an interactive prompt that asks for the key:",
            f"  dku auth login{' --url ' + url if url else ''}",
        ],
    )


def _handle_project_access_denied(
    msg: str, project_key: str | None = None
) -> tuple[str, list[str]] | None:
    """Detect a project-scoped 401 and prescribe key-vs-name, NOT re-auth.

    DSS returns ``UnauthorizedException: Failed to read project permissions`` for
    a project the caller cannot access — and it does NOT distinguish "project
    does not exist" from "exists but you lack permission" (it refuses to reveal
    existence). The generic 401/Unauthorized branch in ``handle_api_error`` then
    blames the API key, sending agents into a pointless re-auth loop even though
    their key is perfectly valid (``dku whoami`` works fine). This is the exact
    failure mode that wasted 6 agent steps in a live benchmark run.

    A genuinely invalid key surfaces earlier as ``NotAuthenticatedException`` /
    ``Unknown API Key`` (handled by ``_handle_invalid_api_key``), so by the time
    we reach this project-permissions failure the instance credentials are sound.

    Fires on either of two signals:
      * The exact DSS message ``Failed to read project permissions`` — catches
        ANY project-scoped command (dataset, recipe, scenario…), even when the
        caller did not thread a project key.
      * A 401/Unauthorized when the caller DID name a project (``project_key``
        set) — broader, and future-proofs the wired commands against DSS
        rewording the permissions message.

    Returns (message, details) or None if the error isn't this case.
    """
    perm_failure = "Failed to read project permissions" in msg
    named_project_401 = project_key is not None and (
        "Unauthorized" in msg or "401" in msg
    )
    if not (perm_failure or named_project_401):
        return None

    subject = f"Project '{project_key}'" if project_key else "That project key"
    details = [
        "DSS returns the same error whether the project does not exist or you",
        "lack permission on it — it will not say which.",
        "",
        "This is NOT an API-key problem: your instance credentials work",
        "(`dku whoami` confirms them). Do NOT run `dku auth login` again.",
        "",
        "Most likely cause: project KEY vs display NAME. A key is UPPERCASE with",
        "no spaces (e.g. ADVISORGPT) and differs from the display name (e.g.",
        "'AdvisorGPT'). Project-scoped commands require the KEY, not the name.",
        "",
        "List projects and read the KEY column (not NAME):",
        "  dku project list",
    ]
    if project_key:
        details.append(
            f"Find the row whose NAME is '{project_key}' and retry with its KEY."
        )
    return (
        f"{subject} was not found, or your account cannot access it.",
        details,
    )
