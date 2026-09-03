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

"""Shared parsing/coercion helpers for tool modules."""

from __future__ import annotations

import json
from typing import Any

from .validation import require_non_empty_strings


def parse_json_object(raw_json: str, field_name: str) -> dict:
    try:
        parsed = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON for '{field_name}': {exc}") from exc
    if not isinstance(parsed, dict):
        raise ValueError(f"'{field_name}' must be a JSON object")
    return parsed


def coerce_json_object(value: Any, field_name: str) -> dict:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        return parse_json_object(value, field_name)
    raise ValueError(f"'{field_name}' must be a JSON object or JSON string object")


def parse_json_array(raw_json: str, field_name: str) -> list:
    try:
        parsed = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON for '{field_name}': {exc}") from exc
    if not isinstance(parsed, list):
        raise ValueError(f"'{field_name}' must be a JSON array")
    return parsed


def coerce_json_array(value: Any, field_name: str) -> list:
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        return parse_json_array(value, field_name)
    raise ValueError(f"'{field_name}' must be a JSON array or JSON string array")


def get_bool_value(value: Any, field_name: str, default: bool) -> bool:
    if value is None:
        return default
    if value is not True and value is not False:
        raise ValueError(f"'{field_name}' must be a boolean")
    return value


def parse_non_empty_string_list(raw_json: str, field_name: str) -> list[str]:
    parsed = parse_json_array(raw_json, field_name)
    if len(parsed) < 1:
        raise ValueError(f"'{field_name}' must be a non-empty JSON array")

    return require_non_empty_strings(parsed, field_name)
