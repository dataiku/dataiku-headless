"""Safe exception-to-text helpers."""


def safe_error_text(exc: BaseException) -> str:
    """Render an exception as text without raising."""
    try:
        return str(exc)
    except Exception:
        pass
    try:
        return repr(exc)
    except Exception:
        pass
    return type(exc).__name__
