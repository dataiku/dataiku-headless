"""Canonical CLI enums — closed value sets exposed as `click.Choice`.

Each is a ``str``-mixin Enum whose member name equals its value, so:

* Typer renders it as a ``click.Choice`` (the value list shows up in
  the machine-readable spec from `dku <cmd> --help`);
* members compare equal to their string value and expose ``str`` methods, so
  existing command bodies that did ``x.upper()`` or ``x in {...}`` keep working;
* an invalid value fails fast at parse time with the valid set shown.

The choice match is **case-insensitive at the CLI boundary**: every option/
argument wiring one of these enums passes ``case_sensitive=False`` to Typer, so
mixed-case input the CLI accepted before (e.g. ``--engine sql``,
``--flavor tabular``, ``--distance-unit KM``) still parses. The enum **value**
remains the canonical case (e.g. ``SQL``, ``TABULAR``, ``km``), so payloads sent
to DSS stay in the exact case DSS expects regardless of how the user typed it.
"""

from __future__ import annotations

from enum import Enum


class _StrEnum(str, Enum):
    """str-mixin base. `str(member)` returns the value, not `Class.NAME`."""

    def __str__(self) -> str:  # keep f-strings / payloads emitting the raw value
        return self.value


# --- recipes: engine & run config -------------------------------------------
class EngineType(_StrEnum):
    DSS = "DSS"
    SQL = "SQL"
    SPARK_SQL = "SPARK_SQL"
    IMPALA = "IMPALA"
    HIVE = "HIVE"


class ContainerMode(_StrEnum):
    INHERIT = "INHERIT"
    NONE = "NONE"
    EXPLICIT_CONTAINER = "EXPLICIT_CONTAINER"
    EXPLICIT_K8S = "EXPLICIT_K8S"
    KUBERNETES = "KUBERNETES"


class EnvMode(_StrEnum):
    INHERIT = "INHERIT"
    USE_BUILTIN_MODE = "USE_BUILTIN_MODE"
    EXPLICIT_ENV = "EXPLICIT_ENV"


# --- recipes: prepare steps --------------------------------------------------
class ReorderMode(_StrEnum):
    AT_THE_BEGINNING = "AT_THE_BEGINNING"
    AT_THE_END = "AT_THE_END"
    BEFORE_COLUMN = "BEFORE_COLUMN"
    AFTER_COLUMN = "AFTER_COLUMN"


class GeoDistanceUnitMiles(_StrEnum):
    """add-geodistance --unit."""

    MILES = "MILES"
    KILOMETERS = "KILOMETERS"


# --- recipes: join / geojoin / fuzzy-join ------------------------------------
class JoinType(_StrEnum):
    LEFT = "LEFT"
    INNER = "INNER"
    RIGHT = "RIGHT"
    FULL = "FULL"
    CROSS = "CROSS"
    LEFT_ANTI = "LEFT_ANTI"
    RIGHT_ANTI = "RIGHT_ANTI"
    ADVANCED = "ADVANCED"


class GeoJoinType(_StrEnum):
    """create-geojoin supports only these four."""

    LEFT = "LEFT"
    INNER = "INNER"
    RIGHT = "RIGHT"
    FULL = "FULL"


class RightLimitKeep(_StrEnum):
    """Shared by create-join --right-limit-keep and geojoin --right-limit-strategy."""

    KEEP_LARGEST = "KEEP_LARGEST"
    KEEP_SMALLEST = "KEEP_SMALLEST"
    KEEP_FIRST = "KEEP_FIRST"
    KEEP_LAST = "KEEP_LAST"


class ConditionsMode(_StrEnum):
    AND = "AND"
    OR = "OR"


class GeoOperator(_StrEnum):
    WITHIN_DISTANCE = "WITHIN_DISTANCE"
    BEYOND_DISTANCE = "BEYOND_DISTANCE"
    INTERSECTS = "INTERSECTS"
    CONTAINS = "CONTAINS"


class GeoDistanceUnit(_StrEnum):
    """create-geojoin --distance-unit (lowercase canonical set)."""

    meter = "meter"
    km = "km"
    foot = "foot"
    yard = "yard"
    mile = "mile"
    nautical_mile = "nautical_mile"


class FuzzyMethod(_StrEnum):
    LEVENSHTEIN = "LEVENSHTEIN"
    JARO_WINKLER = "JARO_WINKLER"
    NORMALIZED_LEVENSHTEIN = "NORMALIZED_LEVENSHTEIN"


# --- recipes: export / filter / split / window / sampling --------------------
class ExportFormat(_StrEnum):
    csv = "csv"
    excel = "excel"
    json = "json"
    parquet = "parquet"
    avro = "avro"
    tsv = "tsv"


class FilterAction(_StrEnum):
    KEEP_ROW = "KEEP_ROW"
    REMOVE_ROW = "REMOVE_ROW"


class FrameMode(_StrEnum):
    ROWS = "ROWS"
    RANGE = "RANGE"


class LagDateUnit(_StrEnum):
    YEAR = "YEAR"
    QUARTER = "QUARTER"
    MONTH = "MONTH"
    WEEK = "WEEK"
    DAY = "DAY"
    HOUR = "HOUR"
    MINUTE = "MINUTE"
    SECOND = "SECOND"
    MILLISECOND = "MILLISECOND"


class SplitMode(_StrEnum):
    VALUES = "VALUES"
    RANDOM = "RANDOM"
    RANGE = "RANGE"
    FILTER = "FILTER"
    CENTILE = "CENTILE"


class SamplingMethod(_StrEnum):
    RANDOM_FIXED_NB = "RANDOM_FIXED_NB"
    RANDOM_FIXED_RATIO = "RANDOM_FIXED_RATIO"
    HEAD_SEQUENTIAL = "HEAD_SEQUENTIAL"
    STRATIFIED = "STRATIFIED"
    CLASS_REBALANCE = "CLASS_REBALANCE"
    FULL = "FULL"


class PartitionSelection(_StrEnum):
    ALL = "ALL"
    LATEST_N = "LATEST_N"
    EXPLICIT = "EXPLICIT"


class StatementsMode(_StrEnum):
    SPLIT = "SPLIT"
    UNIFIED = "UNIFIED"
    RAW = "RAW"


# --- recipes: pivot ----------------------------------------------------------
class PivotAgg(_StrEnum):
    SUM = "SUM"
    AVG = "AVG"
    MIN = "MIN"
    MAX = "MAX"
    COUNT = "COUNT"
    COUNT_DISTINCT = "COUNT_DISTINCT"
    CONCAT = "CONCAT"
    CONCAT_DISTINCT = "CONCAT_DISTINCT"
    STDDEV = "STDDEV"
    FIRST = "FIRST"
    LAST = "LAST"
    FIRST_LAST_NOT_NULL = "FIRST_LAST_NOT_NULL"


class ValueLimit(_StrEnum):
    TOP_N = "TOP_N"
    NO_LIMIT = "NO_LIMIT"
    AT_LEAST_N_OCC = "AT_LEAST_N_OCC"
    EXPLICIT = "EXPLICIT"


class Slugification(_StrEnum):
    NONE = "NONE"
    SOFT_SLUGIFY = "SOFT_SLUGIFY"
    HARD_SLUGIFY = "HARD_SLUGIFY"


class IdentifierMode(_StrEnum):
    EXPLICIT = "EXPLICIT"
    AUTO = "AUTO"
    ALL = "ALL"


# --- flow --------------------------------------------------------------------
class MoveItemType(_StrEnum):
    DATASET = "DATASET"
    RECIPE = "RECIPE"
    MANAGED_FOLDER = "MANAGED_FOLDER"
    SAVED_MODEL = "SAVED_MODEL"
    KNOWLEDGE_BANK = "KNOWLEDGE_BANK"
    MODEL_EVALUATION_STORE = "MODEL_EVALUATION_STORE"
    AUTO = "AUTO"


# --- datasets ----------------------------------------------------------------
class JobsDbView(_StrEnum):
    METRICS_HISTORY = "METRICS_HISTORY"
    CHECK_HISTORY = "CHECK_HISTORY"
    JOBS_HISTORY = "JOBS_HISTORY"


class InlineImportSource(_StrEnum):
    NONE = "NONE"
    CLIPBOARD = "CLIPBOARD"
    CSV = "CSV"
    FILE = "FILE"


# --- ML / models -------------------------------------------------------------
class FeatureRole(_StrEnum):
    INPUT = "INPUT"
    REJECT = "REJECT"
    REJECTED = "REJECTED"  # accepted alias; body remaps to REJECT
    TARGET = "TARGET"
    WEIGHT = "WEIGHT"


class RebuildBehavior(_StrEnum):
    NORMAL = "NORMAL"
    WRITE_PROTECT = "WRITE_PROTECT"
    EXPLICIT_REBUILD = "EXPLICIT_REBUILD"


class CrossProjectBuildBehavior(_StrEnum):
    DEFAULT = "DEFAULT"
    AUTO_BUILD = "AUTO_BUILD"
    DO_NOT_BUILD = "DO_NOT_BUILD"
    EXPLICIT_REBUILD = "EXPLICIT_REBUILD"


class PublishPolicy(_StrEnum):
    UNCONDITIONAL = "UNCONDITIONAL"
    CONDITIONAL = "CONDITIONAL"
    EXPLICIT = "EXPLICIT"


class PredictionType(_StrEnum):
    BINARY_CLASSIFICATION = "BINARY_CLASSIFICATION"
    MULTICLASS = "MULTICLASS"
    REGRESSION = "REGRESSION"


class EvalFlavor(_StrEnum):
    TABULAR = "TABULAR"
    LLM = "LLM"
    AGENT = "AGENT"


# --- govern ------------------------------------------------------------------
class SignoffStatus(_StrEnum):
    NOT_STARTED = "NOT_STARTED"
    WAITING_FOR_FEEDBACK = "WAITING_FOR_FEEDBACK"
    WAITING_FOR_APPROVAL = "WAITING_FOR_APPROVAL"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    ABANDONED = "ABANDONED"


class SignoffFeedbackStatus(_StrEnum):
    APPROVED = "APPROVED"
    MINOR_ISSUE = "MINOR_ISSUE"
    MAJOR_ISSUE = "MAJOR_ISSUE"


class SignoffApprovalStatus(_StrEnum):
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    ABANDONED = "ABANDONED"


class BlueprintStatus(_StrEnum):
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    ARCHIVED = "ARCHIVED"


class SignoffImportRole(_StrEnum):
    ALL = "ALL"
    EXISTING = "EXISTING"
    NONE = "NONE"


class MigrationBehavior(_StrEnum):
    FAIL_IMPORT_ON_EXISTING_MIGRATION_OR_MISSING_VERSION = (
        "FAIL_IMPORT_ON_EXISTING_MIGRATION_OR_MISSING_VERSION"
    )
    IGNORE_MIGRATION_ON_EXISTING_MIGRATION_OR_MISSING_VERSION = (
        "IGNORE_MIGRATION_ON_EXISTING_MIGRATION_OR_MISSING_VERSION"
    )
    IMPORT_WITHOUT_MIGRATIONS = "IMPORT_WITHOUT_MIGRATIONS"


# --- app designer / insight / job -------------------------------------------
class AppEnableMode(_StrEnum):
    setup = "setup"
    template = "template"


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


class JobType(_StrEnum):
    NON_RECURSIVE_FORCED_BUILD = "NON_RECURSIVE_FORCED_BUILD"
    RECURSIVE_BUILD = "RECURSIVE_BUILD"
    RECURSIVE_FORCED_BUILD = "RECURSIVE_FORCED_BUILD"
    RECURSIVE_MISSING_ONLY_BUILD = "RECURSIVE_MISSING_ONLY_BUILD"


class AgentType(_StrEnum):
    TOOLS_USING_AGENT = "TOOLS_USING_AGENT"
    PYTHON_AGENT = "PYTHON_AGENT"
    PLUGIN_AGENT = "PLUGIN_AGENT"
    STRUCTURED_AGENT = "STRUCTURED_AGENT"
