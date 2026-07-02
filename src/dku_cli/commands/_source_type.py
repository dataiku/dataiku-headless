from __future__ import annotations

from enum import Enum


class SourceType(str, Enum):
    LOCAL = "LOCAL"
    LDAP = "LDAP"

    def __str__(self) -> str:
        return self.value
