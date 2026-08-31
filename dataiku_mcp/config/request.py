"""Request-scoped identity, delegated tokens, and instance selection."""

from contextvars import ContextVar, Token

from . import http, stdio
from .models import DSSInstance, NoActiveInstanceError, NoConfiguredInstancesError


_pinned_instance: ContextVar[DSSInstance | None] = ContextVar(
    "dataiku_mcp_pinned_instance", default=None
)
_http_identity: ContextVar[tuple[str, str] | None] = ContextVar(
    "dataiku_mcp_http_identity", default=None
)
_http_dss_token: ContextVar[str | None] = ContextVar(
    "dataiku_mcp_http_dss_token", default=None
)


def is_http_request() -> bool:
    """Whether the current tool call has an authenticated HTTP identity."""
    return _http_identity.get() is not None


def bind_http_identity(issuer: str, subject: str) -> Token:
    """Bind the verified OIDC identity for one HTTP tool request."""
    if not issuer or not subject:
        raise ValueError(
            "The HTTP access token must contain non-empty iss and sub claims."
        )
    return _http_identity.set((issuer, subject))


def reset_http_identity(token: Token) -> None:
    _http_identity.reset(token)


def bind_http_dss_token(token: str) -> Token:
    """Bind the Dataiku delegated access token for one HTTP tool request."""
    return _http_dss_token.set(token)


def reset_http_dss_token(token: Token) -> None:
    _http_dss_token.reset(token)


def get_http_dss_token() -> str:
    token = _http_dss_token.get()
    if not token:
        raise ValueError("No delegated DSS token is available for this HTTP request.")
    return token


def get_request_owner() -> tuple[str, ...]:
    """Return a stable, request-scoped owner identity for retained state."""
    identity = _http_identity.get()
    return ("local",) if identity is None else ("oidc", *identity)


def get_instances() -> dict[str, DSSInstance]:
    """Return the instances available to the current request."""
    if is_http_request():
        instances, _ = http.get_instances_and_defaults()
        return instances
    return stdio.get_instances()


def pin_current_instance() -> Token:
    """Snapshot the active instance for the current MCP request."""
    identity = _http_identity.get()
    if identity is None:
        return _pinned_instance.set(stdio.get_current_instance())

    issuer, subject = identity
    instances, defaults = http.get_instances_and_defaults()
    selected_name = defaults.get(issuer, {}).get(subject)
    return _pinned_instance.set(instances.get(selected_name))


def reset_pinned_instance(token: Token) -> None:
    _pinned_instance.reset(token)


def get_pinned_instance() -> DSSInstance:
    """Return the pinned instance in the request."""
    pinned_instance = _pinned_instance.get()
    if pinned_instance is not None:
        return pinned_instance

    if get_instances():
        raise NoActiveInstanceError("No active Dataiku instance is selected.")
    raise NoConfiguredInstancesError("No Dataiku instances are configured.")


def set_current_instance(name: str) -> dict:
    """Select an instance for the current request or local process."""
    instances = get_instances()
    if name not in instances:
        raise ValueError(f"Unknown instance '{name}'. Available: {list(instances)}")

    selected = instances[name]
    if is_http_request():
        identity = _http_identity.get()
        assert identity is not None
        http.set_user_default(identity[0], identity[1], name)
    else:
        stdio.set_current_instance(selected)
    return {
        "name": selected.name,
        "url": selected.url,
        "description": selected.description,
    }
