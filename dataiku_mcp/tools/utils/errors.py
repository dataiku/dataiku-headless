# Copyright 2026 Dataiku SAS
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

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
