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

"""Compact plugin future receipts without settings, logs, or Git subprocess errors."""


def plugin_future_state(state: dict) -> dict:
    safe = {
        key: state[key]
        for key in ("jobId", "alive", "hasResult", "aborted")
        if key in state
    }
    result = state.get("result")
    if isinstance(result, dict):
        receipt = {
            key: result[key]
            for key in ("success", "needsReload", "needsRestart")
            if key in result
        }
        desc = (result.get("pluginDesc") or {}).get("desc") or {}
        if desc.get("id"):
            receipt["pluginDesc"] = {
                "desc": {key: desc[key] for key in ("id", "version") if key in desc}
            }
        if (
            result.get("success") is False
            or result.get("installationError")
            or result.get("errorMessage")
        ):
            receipt["error"] = (
                "Plugin operation failed. Inspect the plugin and Dataiku server logs before retrying; raw error details are omitted because they may contain credentials."
            )
        safe["result"] = receipt
    return safe
