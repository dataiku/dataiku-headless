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

"""Dataset inspection, local export, and uploaded-dataset creation tools."""

import csv
import hashlib
import os
import tempfile
from typing import Annotated

from fastmcp import Context
from pydantic import Field

from ..config import request
from ..server import mcp
from ..auth import get_dss_client
from ..executors import run_blocking
from .utils.metrics import parse_metric_ids as _parse_metric_ids
from .utils.metrics import select_metrics as _select_metrics
from .utils.serialization import columnar, compact_json, is_empty
from .utils.validation import require_non_empty_string as _require_non_empty_string
from .utils.validation import require_positive_int as _require_positive_int

_MAX_EXPORT_ROWS = 1_000_000
_MAX_UPLOAD_ROWS = 10_000
_CSV_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")

UploadCell = str | int | float | bool | None

ColumnSubset = Annotated[
    list[str] | None, Field(description="Every column when omitted.")
]


def _serialize_upload_cell(value: UploadCell) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int | float):
        return str(value)
    raise ValueError(
        "Upload rows only support scalar values: string, number, boolean, or null."
    )


def _validate_upload_columns(columns: list[str]) -> list[str]:
    if not isinstance(columns, list) or not columns:
        raise ValueError("'columns' must be a non-empty list")
    return [
        _require_non_empty_string(column_name, f"columns[{index}]")
        for index, column_name in enumerate(columns)
    ]


def _write_upload_rows_to_temp_csv(
    dataset_name: str,
    columns: list[str],
    rows: list[list[UploadCell]],
) -> tuple[str, str]:
    if not isinstance(rows, list):
        raise ValueError("'rows' must be a list")
    if len(rows) > _MAX_UPLOAD_ROWS:
        raise ValueError(f"'rows' must contain at most {_MAX_UPLOAD_ROWS} rows")
    cleaned_columns = _validate_upload_columns(columns)
    temporary_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", newline="", encoding="utf-8", suffix=".csv", delete=False
        ) as temp_file:
            temporary_path = temp_file.name
            writer = csv.writer(temp_file)
            writer.writerow(cleaned_columns)
            expected_row_length = len(cleaned_columns)
            for row_index, row in enumerate(rows):
                if not isinstance(row, list) or len(row) != expected_row_length:
                    raise ValueError(
                        f"'rows[{row_index}]' must contain exactly {expected_row_length} values"
                    )
                writer.writerow([_serialize_upload_cell(value) for value in row])
    except BaseException:
        if temporary_path is not None:
            os.unlink(temporary_path)
        raise
    assert temporary_path is not None
    return temporary_path, f"{dataset_name}.csv"


def _create_uploaded_dataset_from_file(
    project_key: str,
    dataset_name: str,
    filepath: str,
    connection: str,
    filename: str,
    include_schema: bool,
):
    effective_filename = filename or os.path.basename(filepath)
    project = get_dss_client().get_project(project_key)
    with open(filepath, "rb") as handle:
        existing = {item.get("name") for item in project.list_datasets()}
        if dataset_name in existing:
            raise ValueError(
                f"Dataset '{dataset_name}' already exists in project '{project_key}'. "
                "Use a new dataset name or first delete existing dataset through Cobuild."
            )

        dataset = project.create_upload_dataset(dataset_name, connection=connection)
        dataset.uploaded_add_file(handle, effective_filename)

        settings = dataset.autodetect_settings()
        settings.save()
        schema = dataset.get_schema()
    result = {
        "filename": effective_filename,
        "column_count": len(schema.get("columns", [])),
    }
    if include_schema:
        result["columns"] = columnar(
            [
                {"name": column["name"], "type": column.get("type", "string")}
                for column in schema.get("columns", [])
            ],
            ["name", "type"],
        )
    return result


def _serialize_preview_value(value, max_value_length: int | None):
    if max_value_length is None:
        return value, 0
    if isinstance(value, str):
        if len(value) <= max_value_length:
            return value, 0
        return value[:max_value_length], 1
    if isinstance(value, list):
        truncated_count = 0
        output = []
        for item in value:
            serialized_item, item_truncated = _serialize_preview_value(
                item, max_value_length
            )
            output.append(serialized_item)
            truncated_count += item_truncated
        return output, truncated_count
    if isinstance(value, dict):
        truncated_count = 0
        output = {}
        for key, item in value.items():
            serialized_item, item_truncated = _serialize_preview_value(
                item, max_value_length
            )
            output[key] = serialized_item
            truncated_count += item_truncated
        return output, truncated_count
    return value, 0


def _serialize_csv_value(value, spreadsheet_safe: bool):
    """Serialize one CSV cell, optionally neutralizing spreadsheet formulas."""
    if value is None:
        return ""
    if (
        spreadsheet_safe
        and isinstance(value, str)
        and value.lstrip(" \t\r\n").startswith(_CSV_FORMULA_PREFIXES)
    ):
        return "'" + value
    return value


def _resolve_export_columns(
    schema_columns: list[dict],
    requested_columns: list[str] | None,
) -> tuple[list[str], list[int], list[str]]:
    available_columns = [column["name"] for column in schema_columns]
    columns_by_name = {
        column["name"]: (index, column) for index, column in enumerate(schema_columns)
    }
    if requested_columns is None:
        selected_columns = available_columns
    else:
        if not requested_columns:
            raise ValueError("'columns' must be a non-empty list")
        seen = set()
        duplicates = []
        for column_name in requested_columns:
            if column_name in seen and column_name not in duplicates:
                duplicates.append(column_name)
            seen.add(column_name)
        if duplicates:
            raise ValueError(f"Duplicate column(s): {duplicates}")
        unknown = [
            column_name
            for column_name in requested_columns
            if column_name not in columns_by_name
        ]
        if unknown:
            raise ValueError(
                f"Unknown column(s): {unknown}. Available columns: {available_columns}"
            )
        selected_columns = requested_columns

    selected_indices = [
        columns_by_name[column_name][0] for column_name in selected_columns
    ]
    selected_types = [
        columns_by_name[column_name][1].get("type", "string")
        for column_name in selected_columns
    ]
    return selected_columns, selected_indices, selected_types


@mcp.tool(
    title="Create Uploaded Files Dataset",
    annotations={
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
async def create_upload_dataset(
    project_key: str,
    dataset_name: str,
    ctx: Context,
    connection: Annotated[
        str, Field(description="Dataiku connection that accepts uploaded files.")
    ],
    filepath: Annotated[
        str | None,
        Field(description="Stdio-only path on the machine running this server."),
    ] = None,
    columns: Annotated[
        list[str] | None,
        Field(description="Column names for a bounded row upload."),
    ] = None,
    rows: Annotated[
        list[list[UploadCell]] | None,
        Field(description=f"Rows to upload; capped at {_MAX_UPLOAD_ROWS}."),
    ] = None,
    filename: Annotated[
        str, Field(description="Name recorded in Dataiku; defaults to the file's own.")
    ] = "",
    include_schema: bool = True,
) -> str:
    """Create a dataset from a stdio-local file or bounded tabular rows."""
    project_key = _require_non_empty_string(project_key, "project_key")
    dataset_name = _require_non_empty_string(dataset_name, "dataset_name")
    connection = _require_non_empty_string(connection, "connection")
    if filename:
        filename = _require_non_empty_string(filename, "filename")

    has_filepath = filepath is not None
    has_rows = rows is not None or columns is not None
    if has_filepath and has_rows:
        raise ValueError("Provide either 'filepath' or 'columns' and 'rows', not both.")
    if not has_filepath and not has_rows:
        raise ValueError("Provide either 'filepath' or both 'columns' and 'rows'.")
    if has_rows and (columns is None or rows is None):
        raise ValueError("'columns' and 'rows' must be provided together.")
    if request.is_http_request() and has_filepath:
        raise ValueError(
            "'filepath' is unavailable in HTTP mode. Provide 'columns' and 'rows'."
        )
    if has_filepath:
        filepath = _require_non_empty_string(filepath, "filepath")

    source = "rows" if has_rows else "local file"
    await ctx.info(
        f"Creating upload dataset '{dataset_name}' from {source} in {project_key}..."
    )

    def _run():
        temporary_path = None
        if has_rows:
            temporary_path, default_filename = _write_upload_rows_to_temp_csv(
                dataset_name=dataset_name,
                columns=columns,
                rows=rows,
            )
            source_path = temporary_path
            effective_filename = filename or default_filename
        else:
            source_path = filepath
            effective_filename = filename
        try:
            return _create_uploaded_dataset_from_file(
                project_key=project_key,
                dataset_name=dataset_name,
                filepath=source_path,
                connection=connection,
                filename=effective_filename,
                include_schema=include_schema,
            )
        finally:
            if temporary_path is not None:
                try:
                    os.unlink(temporary_path)
                except FileNotFoundError:
                    pass

    return compact_json(await run_blocking(_run))


@mcp.tool(
    title="List Datasets",
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "openWorldHint": False,
    },
)
async def list_datasets(project_key: str, ctx: Context) -> str:
    """Find a project's datasets and their exact names, types, and connections."""
    await ctx.info(f"Listing datasets in {project_key}...")

    def _run():
        project = get_dss_client().get_project(project_key)
        result = []
        for ds_info in project.list_datasets(include_shared=True):
            name = ds_info.get("name")
            foreign_project = ds_info.get("projectKey", project_key)
            is_shared = foreign_project != project_key
            row = {
                "name": ds_info.get("smartName", f"{foreign_project}.{name}")
                if is_shared
                else name,
                "type": ds_info.get("type", ""),
                "connection": ds_info.get("connection")
                or ds_info.get("params", {}).get("connection"),
            }
            if is_shared:
                row["shared"] = True
            result.append(row)
        return columnar(result, ["name", "type", "connection", "shared"])

    return compact_json(await run_blocking(_run))


@mcp.tool(
    title="Get Dataset Sample",
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "openWorldHint": False,
    },
)
async def get_dataset_sample(
    project_key: str,
    dataset_name: str,
    ctx: Context,
    limit: Annotated[int, Field(description="Capped at 100.")] = 5,
    max_value_length: Annotated[
        int | None, Field(description="Null returns values untruncated.")
    ] = 200,
    columns: ColumnSubset = None,
) -> str:
    """Read a few rows of a dataset to see raw values, formats, and encodings."""
    limit = min(_require_positive_int(limit, "limit"), 100)
    if max_value_length is not None:
        max_value_length = _require_positive_int(max_value_length, "max_value_length")
    await ctx.info(
        f"Sampling {limit} rows from {dataset_name} "
        f"(max_value_length={max_value_length}, columns={columns})..."
    )

    def _run():
        project = get_dss_client().get_project(project_key)
        dataset = project.get_dataset(dataset_name)
        schema = dataset.get_schema()
        all_columns = [column["name"] for column in schema.get("columns", [])]
        col_types = {
            column["name"]: column.get("type", "string")
            for column in schema.get("columns", [])
        }
        keep = set(columns) if columns else None
        kept = [
            (index, column)
            for index, column in enumerate(all_columns)
            if keep is None or column in keep
        ]
        kept_indices = [index for index, _ in kept]
        kept_columns = [column for _, column in kept]
        rows = []
        truncated_string_values = 0
        try:
            for row in dataset.iter_rows():
                output_row = []
                for index in kept_indices:
                    serialized_value, value_truncated = _serialize_preview_value(
                        row[index], max_value_length
                    )
                    output_row.append(serialized_value)
                    truncated_string_values += value_truncated
                rows.append(output_row)
                if len(rows) >= limit:
                    break
        except Exception as exc:
            raise ValueError(f"Could not sample dataset: {str(exc)}") from exc

        result = {
            "dataset": dataset_name,
            "columns": kept_columns,
            "types": [col_types[column] for column in kept_columns],
            "limit_sampled": len(rows),
            "rows": rows,
        }
        if max_value_length is not None:
            result["max_value_length_applied"] = max_value_length
            if truncated_string_values > 0:
                result["truncated_string_values"] = truncated_string_values
        return result

    return compact_json(await run_blocking(_run))


@mcp.tool(
    title="Export Dataset to CSV",
    annotations={
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
async def export_dataset(
    project_key: str,
    dataset_name: str,
    output_path: Annotated[
        str,
        Field(
            description="CSV path on the machine running this server; "
            "its parent directory must exist."
        ),
    ],
    ctx: Context,
    limit: Annotated[
        int, Field(description=f"Rows to export. Capped at {_MAX_EXPORT_ROWS}.")
    ] = _MAX_EXPORT_ROWS,
    columns: ColumnSubset = None,
    overwrite: Annotated[
        bool, Field(description="Replaces any existing file at output_path.")
    ] = False,
    spreadsheet_safe: Annotated[
        bool,
        Field(description="Escapes text a spreadsheet would evaluate as a formula."),
    ] = False,
) -> str:
    """Write a dataset's rows to a local CSV file, when every row is needed offline."""
    if request.is_http_request():
        raise ValueError(
            "export_dataset is unavailable in HTTP mode because it writes to the MCP host filesystem."
        )
    project_key = _require_non_empty_string(project_key, "project_key")
    dataset_name = _require_non_empty_string(dataset_name, "dataset_name")
    output_path = _require_non_empty_string(output_path, "output_path")
    limit = _require_positive_int(limit, "limit")
    if limit > _MAX_EXPORT_ROWS:
        raise ValueError(f"'limit' must be <= {_MAX_EXPORT_ROWS}")
    absolute_output_path = os.path.realpath(os.path.expanduser(output_path))
    requested_columns = None if columns is None else list(columns)
    await ctx.info(
        f"Exporting up to {limit} rows from {dataset_name} in {project_key} "
        f"to '{absolute_output_path}'..."
    )

    def _run():
        parent_directory = os.path.dirname(absolute_output_path)
        if not os.path.isdir(parent_directory):
            raise FileNotFoundError(
                f"Destination directory does not exist: {parent_directory}"
            )
        if os.path.lexists(absolute_output_path) and not overwrite:
            raise FileExistsError(
                f"Destination already exists: {absolute_output_path}. "
                "Set overwrite=true to replace it."
            )

        dataset = get_dss_client().get_project(project_key).get_dataset(dataset_name)
        schema_columns = dataset.get_schema().get("columns", [])
        selected_columns, selected_indices, selected_types = _resolve_export_columns(
            schema_columns, requested_columns
        )

        temporary_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                newline="",
                prefix=".dku-export-",
                suffix=".tmp",
                dir=parent_directory,
                delete=False,
            ) as output_file:
                temporary_path = output_file.name
                writer = csv.writer(output_file, lineterminator="\n")
                writer.writerow(
                    [
                        _serialize_csv_value(column, spreadsheet_safe)
                        for column in selected_columns
                    ]
                )
                row_count = 0
                has_more_rows = False
                for row in dataset.iter_rows():
                    if row_count >= limit:
                        has_more_rows = True
                        break
                    writer.writerow(
                        [
                            _serialize_csv_value(row[index], spreadsheet_safe)
                            for index in selected_indices
                        ]
                    )
                    row_count += 1

            digest = hashlib.sha256()
            with open(temporary_path, "rb") as completed_file:
                for chunk in iter(
                    lambda: completed_file.read(1024 * 1024),
                    b"",
                ):
                    digest.update(chunk)
            size_bytes = os.path.getsize(temporary_path)

            if os.path.lexists(absolute_output_path) and not overwrite:
                raise FileExistsError(
                    f"Destination already exists: {absolute_output_path}. "
                    "Set overwrite=true to replace it."
                )
            os.replace(temporary_path, absolute_output_path)
            temporary_path = None
        finally:
            if temporary_path is not None:
                try:
                    os.unlink(temporary_path)
                except FileNotFoundError:
                    pass

        return {
            "project_key": project_key,
            "dataset_name": dataset_name,
            "output_path": absolute_output_path,
            "format": "csv",
            "row_count": row_count,
            "column_count": len(selected_columns),
            "columns": selected_columns,
            "types": selected_types,
            "size_bytes": size_bytes,
            "sha256": digest.hexdigest(),
            "limit": limit,
            "has_more_rows": has_more_rows,
            "spreadsheet_safe": spreadsheet_safe,
        }

    return compact_json(await run_blocking(_run))


@mcp.tool(
    title="Get Dataset Info",
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "openWorldHint": False,
    },
)
async def get_dataset_info(project_key: str, dataset_name: str, ctx: Context) -> str:
    """Inspect where a dataset's data lives and what its columns mean."""
    await ctx.info(f"Loading dataset info for {dataset_name} in {project_key}...")

    def _run():
        project = get_dss_client().get_project(project_key)
        dataset = project.get_dataset(dataset_name)
        schema = dataset.get_schema()
        settings = dataset.get_settings().get_raw()
        dataset_type = None
        for ds_info in project.list_datasets():
            if ds_info.get("name") == dataset_name:
                dataset_type = ds_info.get("type")
                break
        result = {
            "type": dataset_type,
            "connection": settings.get("params", {}).get("connection"),
            "columns": columnar(
                [
                    {
                        "name": column["name"],
                        "type": column.get("type", "string"),
                        "meaning": column.get("meaning", ""),
                        "comment": column.get("comment", ""),
                    }
                    for column in schema.get("columns", [])
                ],
                ["name", "type", "meaning", "comment"],
            ),
        }
        for key in ("type", "connection"):
            if is_empty(result[key]):
                del result[key]
        return result

    return compact_json(await run_blocking(_run))


@mcp.tool(
    title="Get Dataset Column Descriptions",
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "openWorldHint": False,
    },
)
async def get_dataset_column_descriptions(
    project_key: str,
    dataset_name: str,
    ctx: Context,
    columns: ColumnSubset = None,
) -> str:
    """Read the documented business intent recorded against a dataset's columns."""
    await ctx.info(
        f"Loading column descriptions for {dataset_name} in {project_key}..."
    )

    def _run():
        dataset = get_dss_client().get_project(project_key).get_dataset(dataset_name)
        schema = dataset.get_schema()
        columns_by_name = {
            column["name"]: column for column in schema.get("columns", [])
        }
        requested_columns = list(columns) if columns else list(columns_by_name)
        missing = [
            column_name
            for column_name in requested_columns
            if column_name not in columns_by_name
        ]
        if missing:
            raise ValueError(
                f"Unknown column(s): {missing}. Available columns: {sorted(columns_by_name)}"
            )
        return {
            "columns": columnar(
                [
                    {
                        "name": column_name,
                        "description": columns_by_name[column_name].get("comment", ""),
                    }
                    for column_name in requested_columns
                ],
                ["name", "description"],
            )
        }

    return compact_json(await run_blocking(_run))


@mcp.tool(
    title="Profile Dataset Columns",
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "openWorldHint": False,
    },
)
async def get_dataset_profile(
    project_key: str,
    dataset_name: str,
    ctx: Context,
    max_rows: Annotated[
        int, Field(description="Rows scanned; the result flags a truncated scan.")
    ] = 10000,
    max_distinct_values: Annotated[
        int, Field(description="Most frequent values kept per column.")
    ] = 5,
    columns: ColumnSubset = None,
) -> str:
    """Judge a dataset's quality from null rates, value frequencies, and numeric ranges."""
    max_rows = _require_positive_int(max_rows, "max_rows")
    max_distinct_values = _require_positive_int(
        max_distinct_values, "max_distinct_values"
    )
    await ctx.info(
        f"Profiling {dataset_name} in {project_key} "
        f"(max_rows={max_rows}, columns={columns})..."
    )

    def _run():
        from collections import Counter

        project = get_dss_client().get_project(project_key)
        dataset = project.get_dataset(dataset_name)
        schema = dataset.get_schema()
        all_columns = [column["name"] for column in schema.get("columns", [])]
        col_types = {
            column["name"]: column.get("type", "string")
            for column in schema.get("columns", [])
        }
        keep = set(columns) if columns else None
        profiled_cols = [
            column for column in all_columns if keep is None or column in keep
        ]
        col_indices = {column: index for index, column in enumerate(all_columns)}
        numeric_types = {
            "int",
            "bigint",
            "double",
            "float",
            "smallint",
            "tinyint",
            "decimal",
        }
        null_counts = {column: 0 for column in profiled_cols}
        value_counts = {
            column: Counter()
            for column in profiled_cols
            if col_types.get(column, "string") not in numeric_types
        }
        numeric_stats = {
            column: {"min": None, "max": None, "sum": 0.0, "count": 0}
            for column in profiled_cols
            if col_types.get(column, "string") in numeric_types
        }
        numeric_distinct = {column: Counter() for column in numeric_stats}
        numeric_overflow = {column: False for column in numeric_stats}
        rows_scanned = 0
        truncated = False
        try:
            for row in dataset.iter_rows():
                if rows_scanned >= max_rows:
                    truncated = True
                    break
                rows_scanned += 1
                for column in profiled_cols:
                    value = row[col_indices[column]]
                    if value is None or value == "":
                        null_counts[column] += 1
                        continue
                    if column in value_counts:
                        value_counts[column][str(value)] += 1
                    elif column in numeric_stats:
                        try:
                            num = float(value)
                            stats = numeric_stats[column]
                            stats["sum"] += num
                            stats["count"] += 1
                            if stats["min"] is None or num < stats["min"]:
                                stats["min"] = num
                            if stats["max"] is None or num > stats["max"]:
                                stats["max"] = num
                            if not numeric_overflow[column]:
                                distinct_counts = numeric_distinct[column]
                                key = str(value)
                                if (
                                    key in distinct_counts
                                    or len(distinct_counts) < max_distinct_values
                                ):
                                    distinct_counts[key] += 1
                                else:
                                    numeric_overflow[column] = True
                        except (ValueError, TypeError):
                            null_counts[column] += 1
        except Exception as exc:
            raise ValueError(f"Could not profile dataset: {str(exc)}") from exc

        if rows_scanned == 0:
            return {
                "dataset": dataset_name,
                "rows_scanned": 0,
                "truncated": False,
                "columns": {},
            }

        column_profiles: dict[str, dict] = {}
        for column in profiled_cols:
            col_type = col_types.get(column, "string")
            null_rate = round(null_counts[column] / rows_scanned, 4)
            if column in numeric_stats:
                stats = numeric_stats[column]
                valid_count = stats["count"]
                mean = round(stats["sum"] / valid_count, 4) if valid_count > 0 else None
                col_profile = {
                    "type": col_type,
                    "null_rate": null_rate,
                    "min": stats["min"],
                    "max": stats["max"],
                    "mean": mean,
                }
                if not numeric_overflow[column]:
                    distinct_counts = numeric_distinct[column]
                    col_profile["distinct_count"] = len(distinct_counts)
                    col_profile["top"] = [
                        [value, count]
                        for value, count in distinct_counts.most_common(
                            max_distinct_values
                        )
                    ]
                column_profiles[column] = col_profile
            else:
                counts = value_counts[column]
                distinct_count = len(counts)
                col_profile = {
                    "type": col_type,
                    "null_rate": null_rate,
                    "distinct_count": distinct_count,
                    "top": [
                        [value, count]
                        for value, count in counts.most_common(max_distinct_values)
                    ],
                }
                if distinct_count > max_distinct_values:
                    col_profile["truncated"] = True
                column_profiles[column] = col_profile

        return {
            "dataset": dataset_name,
            "rows_scanned": rows_scanned,
            "truncated": truncated,
            "columns": column_profiles,
        }

    return compact_json(await run_blocking(_run))


@mcp.tool(
    title="Get Dataset Metrics",
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "openWorldHint": False,
    },
)
async def get_dataset_metrics(
    project_key: str,
    dataset_name: str,
    ctx: Context,
    metric_ids: Annotated[
        str | None,
        Field(
            description="JSON array of ids, e.g. '[\"records:COUNT_RECORDS\"]'. Every metric when omitted."
        ),
    ] = None,
) -> str:
    """Read the metric values Dataiku last computed for a dataset."""
    await ctx.info(f"Loading dataset metrics for {dataset_name} in {project_key}...")
    metric_ids_list = _parse_metric_ids(metric_ids)

    def _run():
        dataset = get_dss_client().get_project(project_key).get_dataset(dataset_name)
        result: dict = {}
        try:
            raw_metrics = dataset.get_last_metric_values().get_raw().get("metrics", [])
            result.update(_select_metrics(raw_metrics, metric_ids_list))
        except Exception as exc:
            result["metrics_warning"] = str(exc)
        return result

    return compact_json(await run_blocking(_run))
