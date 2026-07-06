"""Extracted enum groups — re-exported from ``dku_cli.enums``.

``dku_cli.enums`` remains the single public home for CLI enums (per
CLAUDE.md); always import from there (``from dku_cli.enums import ChartType``).
This module only hosts the definitions of the chart/dashboard group and the
newest config/agent enums so ``enums.py`` stays within the size ratchet.
The ``_StrEnum`` base lives here (and is re-imported by ``enums.py``) to
avoid a circular import.
"""

from __future__ import annotations

from enum import Enum


class _StrEnum(str, Enum):
    """str-mixin base. `str(member)` returns the value, not `Class.NAME`."""

    def __str__(self) -> str:  # keep f-strings / payloads emitting the raw value
        return self.value


# --- charts / dashboards ------------------------------------------------------
class ChartType(_StrEnum):
    lines = "lines"
    multi_columns_lines = "multi_columns_lines"
    stacked_bars = "stacked_bars"
    grouped_columns = "grouped_columns"
    pie = "pie"
    scatter = "scatter"
    boxplots = "boxplots"
    treemap = "treemap"
    pivot_table = "pivot_table"
    stacked_area = "stacked_area"


class MeasureAgg(_StrEnum):
    AVG = "AVG"
    SUM = "SUM"
    COUNT = "COUNT"
    MIN = "MIN"
    MAX = "MAX"
    COUNT_DISTINCT = "COUNT_DISTINCT"


class MeasureDisplayAs(_StrEnum):
    column = "column"
    line = "line"
    area = "area"


class DimensionDateMode(_StrEnum):
    YEAR = "YEAR"
    QUARTER = "QUARTER"
    MONTH = "MONTH"
    WEEK = "WEEK"
    DAY = "DAY"
    HOUR = "HOUR"


# --- agents -------------------------------------------------------------------
class AgentBlockMode(_StrEnum):
    SIMPLE = "SIMPLE"
    BLOCKS_GRAPH = "BLOCKS_GRAPH"


# --- config / connection / folders ------------------------------------------
class SafetyMode(_StrEnum):
    guarded = "guarded"
    dangerous = "dangerous"


class ConnectionUsableBy(_StrEnum):
    ALL = "ALL"
    ALLOWED = "ALLOWED"


class MergeFolderConflict(_StrEnum):
    OVERWRITE = "OVERWRITE"
    SKIP = "SKIP"
    FAIL = "FAIL"
