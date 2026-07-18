"""Dataset inspection plus uploaded-dataset creation tools."""

import csv
import os
import tempfile

from fastmcp import Context

from .. import mcp
from .utils.async_executor import run_blocking
from .utils.auth import get_dss_client
from .utils.metrics import parse_metric_ids as _parse_metric_ids
from .utils.metrics import select_metrics as _select_metrics
from .utils.serialization import columnar, compact_json, is_empty
from .utils.validation import (
    require_non_empty_string as _require_non_empty_string,
    require_positive_int as _require_positive_int,
)


def _serialize_upload_cell(value):
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
    if not columns:
        raise ValueError("'columns' must be a non-empty list")
    return [
        _require_non_empty_string(column_name, f"columns[{index}]")
        for index, column_name in enumerate(columns)
    ]


def _write_upload_rows_to_temp_csv(
    dataset_name: str,
    columns: list[str],
    rows: list[list[str | int | float | bool | None]],
) -> tuple[str, str]:
    cleaned_columns = _validate_upload_columns(columns)
    with tempfile.NamedTemporaryFile(
        mode="w", newline="", encoding="utf-8", suffix=".csv", delete=False
    ) as temp_file:
        writer = csv.writer(temp_file)
        writer.writerow(cleaned_columns)
        expected_row_length = len(cleaned_columns)
        for row_index, row in enumerate(rows):
            if len(row) != expected_row_length:
                raise ValueError(
                    f"'rows[{row_index}]' must contain exactly {expected_row_length} values"
                )
            writer.writerow([_serialize_upload_cell(value) for value in row])
        return temp_file.name, f"{dataset_name}.csv"


def _create_uploaded_dataset_from_file(
    project_key: str,
    dataset_name: str,
    filepath: str,
    connection: str,
    filename: str,
    overwrite: bool,
    include_schema: bool,
):
    effective_filename = filename or os.path.basename(filepath)
    project = get_dss_client().get_project(project_key)
    existing = {item.get("name") for item in project.list_datasets()}
    if dataset_name in existing:
        if not overwrite:
            raise ValueError(
                f"Dataset '{dataset_name}' already exists in project '{project_key}'. "
                "Set overwrite=true to replace it."
            )
        project.get_dataset(dataset_name).delete()

    dataset = project.create_upload_dataset(dataset_name, connection=connection)
    with open(filepath, "rb") as handle:
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
            serialized_item, item_truncated = _serialize_preview_value(item, max_value_length)
            output.append(serialized_item)
            truncated_count += item_truncated
        return output, truncated_count
    if isinstance(value, dict):
        truncated_count = 0
        output = {}
        for key, item in value.items():
            serialized_item, item_truncated = _serialize_preview_value(item, max_value_length)
            output[key] = serialized_item
            truncated_count += item_truncated
        return output, truncated_count
    return value, 0


@mcp.tool()
async def create_upload_dataset(
    project_key: str,
    dataset_name: str,
    filepath: str,
    ctx: Context,
    connection: str,
    filename: str = "",
    overwrite: bool = False,
    include_schema: bool = True,
) -> str:
    """Create an UploadedFiles dataset from a local file."""
    await ctx.info(f"Creating upload dataset '{dataset_name}' in {project_key}...")

    def _run():
        return _create_uploaded_dataset_from_file(
            project_key=project_key,
            dataset_name=dataset_name,
            filepath=filepath,
            connection=connection,
            filename=filename,
            overwrite=overwrite,
            include_schema=include_schema,
        )

    return compact_json(await run_blocking(_run))


@mcp.tool()
async def create_upload_dataset_from_rows(
    project_key: str,
    dataset_name: str,
    columns: list[str],
    rows: list[list[str | int | float | bool | None]],
    ctx: Context,
    connection: str,
    filename: str = "",
    overwrite: bool = False,
    include_schema: bool = True,
) -> str:
    """Create an UploadedFiles dataset from tabular row data."""
    await ctx.info(f"Creating upload dataset '{dataset_name}' from rows in {project_key}...")

    def _run():
        temp_filepath, default_filename = _write_upload_rows_to_temp_csv(
            dataset_name=dataset_name,
            columns=columns,
            rows=rows,
        )
        try:
            return _create_uploaded_dataset_from_file(
                project_key=project_key,
                dataset_name=dataset_name,
                filepath=temp_filepath,
                connection=connection,
                filename=filename or default_filename,
                overwrite=overwrite,
                include_schema=include_schema,
            )
        finally:
            try:
                os.unlink(temp_filepath)
            except FileNotFoundError:
                pass

    return compact_json(await run_blocking(_run))


@mcp.tool()
async def list_datasets(project_key: str, ctx: Context) -> str:
    """List the datasets in the project with their types and connections."""
    await ctx.info(f"Listing datasets in {project_key}...")

    def _run():
        project = get_dss_client().get_project(project_key)
        result = []
        for ds_info in project.list_datasets(include_shared=True):
            name = ds_info.get("name")
            foreign_project = ds_info.get("projectKey", project_key)
            is_shared = foreign_project != project_key
            row = {
                "name": ds_info.get("smartName", f"{foreign_project}.{name}") if is_shared else name,
                "type": ds_info.get("type", ""),
                "connection": ds_info.get("connection")
                or ds_info.get("params", {}).get("connection"),
            }
            if is_shared:
                row["shared"] = True
            result.append(row)
        return columnar(result, ["name", "type", "connection", "shared"])

    return compact_json(await run_blocking(_run))


@mcp.tool()
async def get_dataset_sample(
    project_key: str,
    dataset_name: str,
    ctx: Context,
    limit: int = 5,
    max_value_length: int | None = 200,
    columns: list[str] | None = None,
) -> str:
    """Sample rows from a dataset to inspect raw value formats."""
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
        kept = [(index, column) for index, column in enumerate(all_columns) if keep is None or column in keep]
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


@mcp.tool()
async def get_dataset_info(project_key: str, dataset_name: str, ctx: Context) -> str:
    """Get the dataset's type, connection, and column schema."""
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


@mcp.tool()
async def get_dataset_profile(
    project_key: str,
    dataset_name: str,
    ctx: Context,
    max_rows: int = 10000,
    max_distinct_values: int = 5,
    columns: list[str] | None = None,
) -> str:
    """Profile per-column nulls, value frequencies, and numeric stats."""
    max_rows = _require_positive_int(max_rows, "max_rows")
    max_distinct_values = _require_positive_int(max_distinct_values, "max_distinct_values")
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
        profiled_cols = [column for column in all_columns if keep is None or column in keep]
        col_indices = {column: index for index, column in enumerate(all_columns)}
        numeric_types = {"int", "bigint", "double", "float", "smallint", "tinyint", "decimal"}
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
                                if key in distinct_counts or len(distinct_counts) < max_distinct_values:
                                    distinct_counts[key] += 1
                                else:
                                    numeric_overflow[column] = True
                        except (ValueError, TypeError):
                            null_counts[column] += 1
        except Exception as exc:
            raise ValueError(f"Could not profile dataset: {str(exc)}") from exc

        if rows_scanned == 0:
            return {"dataset": dataset_name, "rows_scanned": 0, "truncated": False, "columns": {}}

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
                        for value, count in distinct_counts.most_common(max_distinct_values)
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


@mcp.tool()
async def get_dataset_metrics(
    project_key: str,
    dataset_name: str,
    ctx: Context,
    metric_ids: str | None = None,
) -> str:
    """Get the last computed metric values for a dataset."""
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
