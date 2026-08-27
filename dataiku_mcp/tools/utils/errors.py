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


def dataiku_message(exc: BaseException) -> str:
    """Render a Dataiku SDK exception as its message, without the Java class name.

    ``handle_http_exception`` in the SDK composes every failed call's text as
    ``<java.fqn.Type>: <message>`` and discards the HTTP status, so stripping the
    leading type is a property of that client boundary rather than of any one caller.
    """
    text = safe_error_text(exc)
    head, separator, tail = text.partition(": ")
    if separator and "." in head and " " not in head:
        return tail.strip() or text
    return text
