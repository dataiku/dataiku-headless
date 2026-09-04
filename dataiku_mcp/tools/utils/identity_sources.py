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

"""Validation for Dataiku identity source types."""

from .validation import require_allowed_value

IDENTITY_SOURCE_TYPES = {
    "LOCAL",
    "LDAP",
    "AZURE_AD",
    "LOCAL_NO_AUTH",
    "CUSTOM",
    "PAM",
}


def require_identity_source_type(value: str, field_name: str = "source_type") -> str:
    """Require a supported raw Dataiku identity source type."""
    return require_allowed_value(value, field_name, IDENTITY_SOURCE_TYPES)
