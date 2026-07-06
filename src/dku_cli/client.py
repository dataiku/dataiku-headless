"""Auth resolution and DSSClient / GovernClient factories."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import dataikuapi

from dku_cli.auth import KeyStatus, get_api_key_with_status
from dku_cli.config import (
    get_active_profile,
    get_profile_config,
    get_profile_node_type,
)
from dku_cli.errors import AuthError


def resolve_auth(
    url: str | None = None,
    api_key: str | None = None,
    profile: str | None = None,
) -> tuple[str, str]:
    """Resolve DSS URL and API key from flags > env > config.

    Returns (url, api_key).
    Raises AuthError if credentials cannot be resolved.
    """
    # 1. CLI flags
    resolved_url = url
    resolved_key = api_key

    # 2. Environment variables
    if not resolved_url:
        resolved_url = os.environ.get("DKU_URL")
    if not resolved_key:
        resolved_key = os.environ.get("DKU_API_KEY")

    # 3. Profile-based config
    key_status = KeyStatus.OK
    key_detail: str | None = None
    if not resolved_url or not resolved_key:
        active = profile or os.environ.get("DKU_PROFILE") or get_active_profile()
        profile_cfg = get_profile_config(active)
        if not resolved_url:
            resolved_url = profile_cfg.get("url")
        if not resolved_key:
            result = get_api_key_with_status(active)
            resolved_key = result.key
            key_status = result.status
            key_detail = result.detail

    if not resolved_url:
        raise AuthError("No DSS URL configured. Run 'dku auth login' or set DKU_URL.")
    if not resolved_key:
        if key_status == KeyStatus.DENIED:
            # The entry likely still exists — re-running `dku auth login` is
            # the WRONG advice. Tell the user to grant access instead.
            raise AuthError(
                "Keychain access denied for stored API key"
                + (f" ({key_detail})" if key_detail else "")
                + ". The credential is likely still present but the OS refused "
                "access (rate limit, ACL whitelist mismatch, or a prompt that "
                "timed out). Try again interactively from a real terminal and "
                "choose 'Always Allow' when prompted, or set DKU_API_KEY for "
                "this session. Do NOT re-run 'dku auth login' — it may "
                "overwrite a working entry."
            )
        if key_status == KeyStatus.BACKEND_ERROR:
            raise AuthError(
                "Keyring backend error"
                + (f" ({key_detail})" if key_detail else "")
                + ". Set DKU_API_KEY for this session, or re-run 'dku auth login'."
            )
        raise AuthError(
            "No API key configured. Run 'dku auth login' or set DKU_API_KEY."
        )

    # Normalize URL
    resolved_url = resolved_url.rstrip("/")

    return resolved_url, resolved_key


def resolve_node_type(profile: str | None = None) -> str | None:
    """Return the stored node type for the active (or given) profile.

    Returns one of: 'DESIGN', 'AUTOMATION', 'GOVERN', 'DEPLOYER', 'API', or None
    if not stored (legacy profile from before node-type was tracked).
    """
    active = profile or os.environ.get("DKU_PROFILE") or get_active_profile()
    nt = get_profile_node_type(active)
    if nt:
        return nt.upper()
    return None


# Profile config flag value that opts a profile into in-pod ticket auth.
# Used inside DSS-launched containers (Code Studios, recipe runtimes, scenario
# runtimes, …) where DSS injects DKU_API_TICKET + DKU_BACKEND_HOST/PORT and the
# backend trusts the X-DKU-APITicket header. No service-account API key has to
# sit in an image layer or env var — auth scopes to the visiting / launching
# user automatically.
AUTH_MODE_IN_POD_TICKET = "in_pod_ticket"


def _in_pod_ticket_client(profile: str) -> dataikuapi.DSSClient | None:
    """Return a DSSClient wired to the in-pod backend via X-DKU-APITicket.

    Returns None if the profile is not configured for ticket auth. Raises
    AuthError if the profile asks for ticket auth but the env vars DSS would
    inject are missing — that means the CLI is being run outside a
    DSS-launched container, where ticket mode can't work.
    """
    import dataikuapi

    cfg = get_profile_config(profile)
    if cfg.get("auth_mode") != AUTH_MODE_IN_POD_TICKET:
        return None
    ticket = os.environ.get("DKU_API_TICKET")
    host = os.environ.get("DKU_BACKEND_HOST")
    port = os.environ.get("DKU_BACKEND_PORT")
    if not (ticket and host and port):
        raise AuthError(
            f"Profile '{profile}' is configured with auth_mode = "
            f'"{AUTH_MODE_IN_POD_TICKET}" but DKU_API_TICKET / '
            f"DKU_BACKEND_HOST / DKU_BACKEND_PORT are not set in the "
            f"environment. This auth mode only works inside a DSS-launched "
            f"container (Code Studio, recipe runtime, scenario runtime). "
            f"Either run this command from such a container, or switch the "
            f"profile back to API-key auth via 'dku auth login --profile "
            f"{profile}'."
        )
    # DSS injects DKU_BACKEND_PROTOCOL = "https" when EncryptedRPC is enabled
    # on the instance (TLS), else "http". Hardcoding "http" here broke ticket
    # auth on every TLS instance: the backend port answered the plaintext
    # request with a TLS alert, surfacing as `BadStatusLine`. Mirror DSS's own
    # in-pod client (dataiku.core.intercom.get_location_data).
    proto = os.environ.get("DKU_BACKEND_PROTOCOL", "http")
    url = f"{proto}://{host}:{port}"
    no_check = proto == "https"
    kwargs: dict = {"internal_ticket": ticket}
    if no_check:
        kwargs["no_check_certificate"] = True
    client = dataikuapi.DSSClient(url, **kwargs)
    if no_check:
        # The backend uses a self-signed internal RPC cert and is reached over
        # the cluster-internal network; the short-lived, user-scoped
        # X-DKU-APITicket is the security boundary (DSS's own internal-RPC
        # clients verify nothing either). trust_env=False is required because
        # requests lets REQUESTS_CA_BUNDLE (which the Replicate Code Studio
        # startup script points at the *base* cert) override session.verify and
        # re-enable verification against the wrong CA.
        client._session.trust_env = False
        client._session.verify = False
    return client


def get_client(
    url: str | None = None,
    api_key: str | None = None,
    profile: str | None = None,
) -> dataikuapi.DSSClient:
    """Create an authenticated DSSClient.

    Honors auth_mode = "in_pod_ticket" on the resolved profile when neither
    --url nor --api-key are passed (an explicit override means the caller is
    pointing at a different DSS, where the in-pod ticket would not be valid).
    """
    import dataikuapi

    if not url and not api_key:
        active = profile or os.environ.get("DKU_PROFILE") or get_active_profile()
        ticket_client = _in_pod_ticket_client(active)
        if ticket_client is not None:
            return ticket_client
    resolved_url, resolved_key = resolve_auth(url, api_key, profile)
    return dataikuapi.DSSClient(resolved_url, api_key=resolved_key)


def get_govern_client(
    url: str | None = None,
    api_key: str | None = None,
    profile: str | None = None,
):
    """Create an authenticated GovernClient. Used by ``dku govern`` commands.

    Note: in-pod ticket auth does not apply to Govern profiles — DSS only
    injects a ticket valid against the local backend, and Govern always lives
    on a separate node from the studio that launched the pod.
    """
    import dataikuapi

    resolved_url, resolved_key = resolve_auth(url, api_key, profile)
    return dataikuapi.GovernClient(resolved_url, api_key=resolved_key)


def probe_node_type(url: str, api_key: str) -> str | None:
    """Call get_instance_info() and return the node type.

    Works for both DESIGN/AUTOMATION/DEPLOYER/API nodes (via DSSClient) and
    GOVERN nodes (via GovernClient). We try DSSClient first because
    get_instance_info() works on every node type — GovernClient also works but
    fails for non-govern auth edge cases. Returns None if both probes fail.
    """
    import dataikuapi

    # DSSClient.get_instance_info() succeeds against any node the API key
    # is valid on, including GOVERN (the endpoint /instance-info is shared).
    try:
        c = dataikuapi.DSSClient(url.rstrip("/"), api_key=api_key)
        info = c.get_instance_info().raw
        nt = info.get("nodeType") or info.get("rawNodeType")
        if nt:
            return nt.upper()
    except Exception:
        pass
    try:
        c = dataikuapi.GovernClient(url.rstrip("/"), api_key=api_key)
        info = c.get_instance_info().raw
        nt = info.get("nodeType") or info.get("rawNodeType")
        if nt:
            return nt.upper()
    except Exception:
        pass
    return None
