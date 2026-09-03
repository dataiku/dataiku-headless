# Copyright 2026 Dataiku
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
