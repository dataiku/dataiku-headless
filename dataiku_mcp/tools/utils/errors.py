"""Defensive error-to-text rendering for structured failure payloads."""


def safe_error_text(exc: BaseException) -> str:
    """Render an exception as text without ever raising.

    Post-start failure payloads must always be built: an exception whose
    ``__str__`` (or ``__repr__``) raises must not escape the failure handler,
    because that would hand an unstructured error to the transport and lose the
    job/run identities the payload exists to preserve.
    """
    try:
        return str(exc)
    except Exception:
        pass
    try:
        return repr(exc)
    except Exception:
        pass
    return type(exc).__name__
