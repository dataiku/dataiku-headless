"""Dataset operations for exploring and sampling data."""

import csv
import os
import tempfile

from fastmcp import Context

from .. import config, mcp
from .utils.async_executor import run_blocking
from .utils.serialization import columnar, compact_json, is_empty
from .utils.auth import get_dss_client
from .utils.metrics import (
    parse_metric_ids as _parse_metric_ids,
)
from .utils.metrics import (
    select_metrics as _select_metrics,
)
from .utils.parsing import (
    coerce_json_object as _coerce_json_object,
)
from .utils.validation import (
    require_allowed_value as _require_allowed_value,
    require_non_empty_string as _require_non_empty_string,
    require_positive_int as _require_positive_int,
)

_SUPPORTED_METADATA_GENERATION_LANGUAGES = {
    "dutch",
    "english",
    "french",
    "german",
    "japanese",
    "portuguese",
    "spanish",
}


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

    client = get_dss_client()
    project = client.get_project(project_key)

    existing = {item.get("name") for item in project.list_datasets()}
    if dataset_name in existing:
        if not overwrite:
            raise ValueError(
                f"Dataset '{dataset_name}' already exists in project '{project_key}'. "
                "Set overwrite=true to replace it."
            )
        project.get_dataset(dataset_name).delete()

    dataset = project.create_upload_dataset(dataset_name, connection=connection)
    with open(filepath, "rb") as f:
        dataset.uploaded_add_file(f, effective_filename)

    settings = dataset.autodetect_settings()
    settings.save()

    schema = dataset.get_schema()
    column_count = len(schema.get("columns", []))

    result = {
        "filename": effective_filename,
        "column_count": column_count,
    }
    if include_schema:
        result["columns"] = columnar(
            [
                {
                    "name": column["name"],
                    "type": column.get("type", "string"),
                }
                for column in schema.get("columns", [])
            ],
            ["name", "type"],
        )
    return result

def _serialize_preview_value(value, max_value_length: int | None):
    """Serialize a value for preview output with optional recursive string truncation."""
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


@mcp.tool()
async def create_managed_dataset(
    project_key: str,
    dataset_name: str,
    ctx: Context,
    connection: str | None = None,
    overwrite: bool = False,
) -> str:
    """Create an empty managed dataset stored on the given connection.

    Args:
        connection: Managed connection to store the dataset into
        overwrite: Replace any existing dataset of the same name
    """
    connection = connection or config.get_current_instance().default_connection
    connection = _require_non_empty_string(connection, "connection")

    await ctx.info(
        f"Creating managed dataset '{dataset_name}' in {project_key} on connection '{connection}'..."
    )

    def _run():
        project = get_dss_client().get_project(project_key)
        existing = {item.get("name") for item in project.list_datasets()}
        if dataset_name in existing and not overwrite:
            raise ValueError(
                f"Dataset '{dataset_name}' already exists in project '{project_key}'. "
                "Set overwrite=true to replace it."
            )

        builder = project.new_managed_dataset(dataset_name)
        builder.with_store_into(connection)
        dataset = builder.create(overwrite=overwrite)

        result = {
            "connection": connection,
            "overwrite": overwrite,
        }
        try:
            schema = dataset.get_schema()
            result["column_count"] = len(schema.get("columns", []))
        except Exception as exc:
            result["schema_warning"] = str(exc)
        return result

    return compact_json(await run_blocking(_run))


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
    """Create an UploadedFiles dataset from a local file (CSV, TSV, JSON, etc.).

    Args:
        filepath: Path to the local file to upload
        filename: Filename to use in DSS (defaults to the basename of filepath)
        connection: Upload connection name (required; no fallback to instance default).
        overwrite: Delete and recreate any existing dataset of the same name
        include_schema: When True, the response includes a `columns` array with name and type for every column. When False, only `column_count` is returned.
    """
    await ctx.info(
        f"Creating upload dataset '{dataset_name}' in {project_key}..."
    )

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
    """Create an UploadedFiles dataset from tabular row data.

    In ``streamable-http`` mode, this is the intended path for raw tabular
    uploads. Upload all rows in one call via ``columns`` + ``rows``.

    Args:
        columns: Ordered column names for the uploaded tabular file
        rows: Positional row values aligned to `columns`
        filename: Filename to use in DSS (defaults to `<dataset_name>.csv`)
        connection: Upload connection name (required; no fallback to instance default).
        overwrite: Delete and recreate any existing dataset of the same name
        include_schema: When True, the response includes a `columns` array with name and type for every column. When False, only `column_count` is returned.
    """
    await ctx.info(
        f"Creating upload dataset '{dataset_name}' from rows in {project_key}..."
    )

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
                "name": (
                    ds_info.get("smartName", f"{foreign_project}.{name}")
                    if is_shared
                    else name
                ),
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
async def delete_dataset(
    project_key: str,
    dataset_name: str,
    ctx: Context,
    drop_data: bool = False,
) -> str:
    """Delete the dataset.

    Args:
        drop_data: Also drop the underlying data storage
    """
    await run_blocking(
        lambda: (
            get_dss_client().get_project(project_key)
            .get_dataset(dataset_name)
            .delete(drop_data=drop_data)
        )
    )
    return compact_json(
        {
            "drop_data": drop_data,
        }
    )


@mcp.tool()
async def get_dataset_sample(
    project_key: str,
    dataset_name: str,
    ctx: Context,
    limit: int = 5,
    max_value_length: int | None = 200,
    columns: list[str] | None = None,
) -> str:
    """Sample rows from a dataset to inspect raw value formats.

    Returns a columnar payload: `columns` and `types` list each column once, and
    every entry in `rows` is a positional array whose j-th value aligns to
    `columns[j]` / `types[j]` (CSV-like; values are not labeled per row).

    Args:
        limit: Number of rows to return (1-100)
        max_value_length: Truncate string values longer than this; pass null for no truncation
        columns: Subset of columns to include; all columns if omitted
    """
    limit = _require_positive_int(limit, "limit")
    limit = min(limit, 100)
    if max_value_length is not None:
        max_value_length = _require_positive_int(max_value_length, "max_value_length")

    await ctx.info(
        f"Sampling {limit} rows from {dataset_name} (max_value_length={max_value_length}, columns={columns})..."
    )

    def _run():
        project = get_dss_client().get_project(project_key)
        ds = project.get_dataset(dataset_name)
        schema = ds.get_schema()
        all_columns = [c["name"] for c in schema.get("columns", [])]
        col_types = {
            c["name"]: c.get("type", "string") for c in schema.get("columns", [])
        }

        keep = set(columns) if columns else None
        kept = [(i, c) for i, c in enumerate(all_columns) if keep is None or c in keep]
        kept_indices = [i for i, _ in kept]
        kept_columns = [c for _, c in kept]

        rows = []
        truncated_string_values = 0
        try:
            for row in ds.iter_rows():
                output_row = []
                for idx in kept_indices:
                    serialized_value, value_truncated = _serialize_preview_value(
                        row[idx], max_value_length
                    )
                    output_row.append(serialized_value)
                    truncated_string_values += value_truncated

                rows.append(output_row)
                if len(rows) >= limit:
                    break
        except Exception as e:
            raise ValueError(f"Could not sample dataset: {str(e)}") from e

        result = {
            "dataset": dataset_name,
            "columns": kept_columns,
            "types": [col_types[c] for c in kept_columns],
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
async def get_dataset_info(
    project_key: str,
    dataset_name: str,
    ctx: Context,
) -> str:
    """Get the dataset's type, connection, and column schema (name, type, meaning, comment)."""
    await ctx.info(f"Loading dataset info for {dataset_name} in {project_key}...")

    def _run():
        project = get_dss_client().get_project(project_key)
        ds = project.get_dataset(dataset_name)
        schema = ds.get_schema()
        settings = ds.get_settings().get_raw()

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
                        "name": c["name"],
                        "type": c.get("type", "string"),
                        "meaning": c.get("meaning", ""),
                        "comment": c.get("comment", ""),
                    }
                    for c in schema.get("columns", [])
                ],
                ["name", "type", "meaning", "comment"],
            ),
        }
        # Lever 4: omit no-information scalars (type/connection may be None).
        # columns is columnar and always kept.
        for key in ("type", "connection"):
            if is_empty(result[key]):
                del result[key]
        return result

    return compact_json(await run_blocking(_run))


@mcp.tool()
async def set_dataset_column_storage_types(
    project_key: str,
    dataset_name: str,
    columns,
    ctx: Context,
) -> str:
    """Patch dataset column storage types for selected columns.

    The tool reads the full schema, updates only requested column storage
    types, and writes the full schema back. Only use for UploadedFiles
    datasets and outputs of Prepare (`shaker`) recipes when autodetection leaves
    important columns with the wrong storage type.

    Args:
        columns: JSON object mapping column names to storage types,
            e.g. {"lat": "double"}.
    """
    columns_obj = _coerce_json_object(columns, "columns")
    await ctx.info(
        f"Updating storage types for {len(columns_obj)} column(s) on {dataset_name} in {project_key}..."
    )

    def _run():
        if not columns_obj:
            raise ValueError("'columns' must contain at least one column update")

        ds = get_dss_client().get_project(project_key).get_dataset(dataset_name)
        schema = ds.get_schema()
        columns_by_name = {
            column["name"]: column for column in schema.get("columns", [])
        }
        for raw_column_name, raw_type in columns_obj.items():
            column_name = _require_non_empty_string(
                raw_column_name, "columns column name"
            )
            if column_name not in columns_by_name:
                raise ValueError(
                    f"Unknown column '{column_name}'. Available columns: {sorted(columns_by_name)}"
                )
            columns_by_name[column_name]["type"] = _require_non_empty_string(
                raw_type, f"columns.{column_name}"
            )

        ds.set_schema(schema)
        return {
            "status": "updated",
            "updated_column_count": len(columns_obj),
            "columns": columnar(
                [
                    {
                        "name": column_name,
                        "type": columns_by_name[column_name].get("type", "string"),
                    }
                    for column_name in columns_obj
                ],
                ["name", "type"],
            ),
        }

    return compact_json(await run_blocking(_run))


@mcp.tool()
async def get_dataset_column_descriptions(
    project_key: str,
    dataset_name: str,
    ctx: Context,
    columns: list[str] | None = None,
) -> str:
    """Get per-column descriptions from the dataset schema.

    Args:
        columns: Optional subset of column names to return; all columns if omitted
    """
    await ctx.info(f"Loading column descriptions for {dataset_name} in {project_key}...")

    def _run():
        ds = get_dss_client().get_project(project_key).get_dataset(dataset_name)
        schema = ds.get_schema()
        columns_by_name = {c["name"]: c for c in schema.get("columns", [])}

        requested_columns = list(columns) if columns else list(columns_by_name)
        missing_columns = [
            column_name
            for column_name in requested_columns
            if column_name not in columns_by_name
        ]
        if missing_columns:
            raise ValueError(
                f"Unknown column(s): {missing_columns}. "
                f"Available columns: {sorted(columns_by_name)}"
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
            ),
        }

    return compact_json(await run_blocking(_run))


@mcp.tool()
async def set_dataset_column_descriptions(
    project_key: str,
    dataset_name: str,
    descriptions_by_column,
    ctx: Context,
) -> str:
    """Set per-column descriptions in the dataset schema.

    The tool reads the full schema, updates only the requested column comments,
    writes the full schema back, then re-reads the schema to validate.

    Args:
        descriptions_by_column: JSON object mapping column names to description strings.
            Use an empty string to clear a column description.
    """
    descriptions_obj = _coerce_json_object(
        descriptions_by_column,
        "descriptions_by_column",
    )

    await ctx.info(
        f"Updating {len(descriptions_obj)} column description(s) for {dataset_name} in {project_key}..."
    )

    def _run():
        ds = get_dss_client().get_project(project_key).get_dataset(dataset_name)
        schema = ds.get_schema()
        columns_by_name = {c["name"]: c for c in schema.get("columns", [])}

        if not descriptions_obj:
            raise ValueError("'descriptions_by_column' must contain at least one column")

        descriptions: dict[str, str] = {}
        for raw_column_name, raw_description in descriptions_obj.items():
            column_name = _require_non_empty_string(
                raw_column_name, "descriptions_by_column column name"
            )
            if raw_description is None:
                raise ValueError(
                    f"Description for column '{column_name}' must be a string, not null"
                )
            if not isinstance(raw_description, str):
                raise ValueError(
                    f"Description for column '{column_name}' must be a string"
                )
            descriptions[column_name] = raw_description

        unknown_columns = [
            column_name
            for column_name in descriptions
            if column_name not in columns_by_name
        ]
        if unknown_columns:
            raise ValueError(
                f"Unknown column(s): {unknown_columns}. "
                f"Available columns: {sorted(columns_by_name)}"
            )

        for column_name, description in descriptions.items():
            columns_by_name[column_name]["comment"] = description

        ds.set_schema(schema)

        updated_schema = ds.get_schema()
        updated_columns = {c["name"]: c for c in updated_schema.get("columns", [])}
        validation_errors = []
        for column_name, expected_comment in descriptions.items():
            actual_comment = updated_columns[column_name].get("comment", "")
            if actual_comment != expected_comment:
                validation_errors.append(
                    {
                        "column": column_name,
                        "expected": expected_comment,
                        "actual": actual_comment,
                    }
                )

        if validation_errors:
            return {
                "status": "validation_failed",
                "updated_column_count": len(descriptions),
                "validation_errors": columnar(
                    validation_errors,
                    ["column", "expected", "actual"],
                ),
            }

        return {
            "status": "updated",
            "updated_column_count": len(descriptions),
            "columns": columnar(
                [
                    {"name": column_name, "description": descriptions[column_name]}
                    for column_name in descriptions
                ],
                ["name", "description"],
            ),
        }

    return compact_json(await run_blocking(_run))


@mcp.tool()
async def generate_dataset_metadata(
    project_key: str,
    dataset_name: str,
    ctx: Context,
    language: str = "english",
    save_description: bool = False,
) -> str:
    """Generate AI-powered dataset and column descriptions.

    Args:
        language: One of dutch, english, french, german, japanese, portuguese, spanish
        save_description: If true, save all generated descriptions to the dataset
    """
    language = _require_allowed_value(
        language,
        "language",
        _SUPPORTED_METADATA_GENERATION_LANGUAGES,
    )

    await ctx.info(
        f"Generating metadata for {dataset_name} in {project_key} "
        f"(language={language}, save_description={save_description})..."
    )

    def _run():
        ds = get_dss_client().get_project(project_key).get_dataset(dataset_name)
        result = ds.generate_ai_description(
            language=language,
            save_description=save_description,
        )
        return {
            "language": language,
            "save_description": save_description,
            "result": result,
        }

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
    """Profile per-column nulls, value frequencies, and numeric stats (compact payload).

    Scans up to max_rows. Per string/boolean column: null_rate, distinct_count, and `top` — the
    most frequent values as `[value, count]` pairs (up to max_distinct_values, most frequent first;
    `truncated: true` when more distinct values exist). Per numeric column: null_rate + min/max/mean,
    plus distinct_count and `top` when the column is low-cardinality (no more than max_distinct_values
    distinct values — e.g. status codes, flags, country ids); high-cardinality numerics keep
    min/max/mean only. Use to understand column content, spot anomalies or misspellings, check nulls
    before transforms, or verify a small numeric value-set.

    Args:
        max_rows: Maximum rows to scan
        max_distinct_values: Max number of top values returned per column (default 5); also the
            cardinality threshold above which a numeric column is treated as continuous (top dropped).
            distinct_count is always exact when present. Raise it to see more of the distribution.
        columns: Subset of columns to profile; all columns if omitted
    """
    max_rows = _require_positive_int(max_rows, "max_rows")
    max_distinct_values = _require_positive_int(max_distinct_values, "max_distinct_values")

    await ctx.info(
        f"Profiling {dataset_name} in {project_key} (max_rows={max_rows}, columns={columns})..."
    )

    def _run():
        from collections import Counter

        project = get_dss_client().get_project(project_key)
        ds = project.get_dataset(dataset_name)
        schema = ds.get_schema()
        all_columns = [c["name"] for c in schema.get("columns", [])]
        col_types = {c["name"]: c.get("type", "string") for c in schema.get("columns", [])}

        keep = set(columns) if columns else None
        profiled_cols = [c for c in all_columns if keep is None or c in keep]
        col_indices = {c: i for i, c in enumerate(all_columns)}

        numeric_types = {"int", "bigint", "double", "float", "smallint", "tinyint", "decimal"}

        null_counts = {c: 0 for c in profiled_cols}
        value_counts: dict[str, Counter] = {
            c: Counter()
            for c in profiled_cols
            if col_types.get(c, "string") not in numeric_types
        }
        numeric_stats: dict[str, dict] = {
            c: {"min": None, "max": None, "sum": 0.0, "count": 0}
            for c in profiled_cols
            if col_types.get(c, "string") in numeric_types
        }
        # Track distinct values for numeric columns too, capped at max_distinct_values: a
        # low-cardinality numeric (code, flag, country id) then exposes a categorical
        # top/distinct_count exactly like a string column, so a value-set can be verified.
        # The first value past the cap trips overflow and the column stays min/max/mean only.
        numeric_distinct: dict[str, Counter] = {c: Counter() for c in numeric_stats}
        numeric_overflow: dict[str, bool] = {c: False for c in numeric_stats}

        rows_scanned = 0
        truncated = False
        try:
            for row in ds.iter_rows():
                if rows_scanned >= max_rows:
                    truncated = True
                    break

                rows_scanned += 1
                for col in profiled_cols:
                    val = row[col_indices[col]]
                    if val is None or val == "":
                        null_counts[col] += 1
                        continue

                    if col in value_counts:
                        value_counts[col][str(val)] += 1
                    elif col in numeric_stats:
                        try:
                            num = float(val)
                            stats = numeric_stats[col]
                            stats["sum"] += num
                            stats["count"] += 1
                            if stats["min"] is None or num < stats["min"]:
                                stats["min"] = num
                            if stats["max"] is None or num > stats["max"]:
                                stats["max"] = num
                            if not numeric_overflow[col]:
                                dc = numeric_distinct[col]
                                key = str(val)
                                if key in dc or len(dc) < max_distinct_values:
                                    dc[key] += 1
                                else:
                                    numeric_overflow[col] = True
                        except (ValueError, TypeError):
                            null_counts[col] += 1

        except Exception as e:
            raise ValueError(f"Could not profile dataset: {str(e)}") from e

        if rows_scanned == 0:
            return {"dataset": dataset_name, "rows_scanned": 0, "truncated": False, "columns": {}}

        column_profiles: dict[str, dict] = {}
        for col in profiled_cols:
            col_type = col_types.get(col, "string")
            null_rate = round(null_counts[col] / rows_scanned, 4)

            if col in numeric_stats:
                stats = numeric_stats[col]
                valid_count = stats["count"]
                mean = round(stats["sum"] / valid_count, 4) if valid_count > 0 else None
                col_profile = {
                    "type": col_type,
                    "null_rate": null_rate,
                    "min": stats["min"],
                    "max": stats["max"],
                    "mean": mean,
                }
                # Low-cardinality numeric: expose the categorical view so a value-set can be
                # verified. The distinct set is complete (it never overflowed the cap), so
                # top covers every value and is not truncated.
                if not numeric_overflow[col]:
                    dc = numeric_distinct[col]
                    col_profile["distinct_count"] = len(dc)
                    col_profile["top"] = [[v, c] for v, c in dc.most_common(max_distinct_values)]
                column_profiles[col] = col_profile
            else:
                counts = value_counts[col]
                distinct_count = len(counts)
                col_profile: dict = {
                    "type": col_type,
                    "null_rate": null_rate,
                    "distinct_count": distinct_count,
                    # top values as [value, count] pairs, most frequent first
                    "top": [[v, c] for v, c in counts.most_common(max_distinct_values)],
                }
                if distinct_count > max_distinct_values:
                    col_profile["truncated"] = True
                column_profiles[col] = col_profile

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
    """Get the last computed metric values for a dataset.

    Args:
        metric_ids: Optional JSON array to filter, e.g. '["basic:SIZE","records:COUNT_RECORDS"]'
    """
    await ctx.info(f"Loading dataset metrics for {dataset_name} in {project_key}...")

    metric_ids_list = _parse_metric_ids(metric_ids)

    def _run():
        ds = get_dss_client().get_project(project_key).get_dataset(dataset_name)
        result: dict = {}
        try:
            raw_metrics = ds.get_last_metric_values().get_raw().get("metrics", [])
            result.update(_select_metrics(raw_metrics, metric_ids_list))
        except Exception as exc:
            result["metrics_warning"] = str(exc)
        return result

    return compact_json(await run_blocking(_run))
