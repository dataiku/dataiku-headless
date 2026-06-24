"""Dataset create payload helpers."""

from __future__ import annotations

import typer

from dku_cli.errors import exit_with_error
from dku_cli.helpers import read_json_input


# Dataset types that live on a SQL connection. `dku dataset create --type <T> -c <C>`
# for these types should produce a managed, writable `mode: "table"` dataset by
# default — otherwise the dataset comes up as an unmanaged query-mode dataset
# that no recipe can write to. The canonical list of SQL dataset types exposed
# via dataikuapi's concrete type names.
_SQL_DATASET_TYPES = frozenset(
    {
        "PostgreSQL",
        "MySQL",
        "Snowflake",
        "Redshift",
        "BigQuery",
        "Oracle",
        "SQLServer",
        "Vertica",
        "Teradata",
        "Greenplum",
        "Netezza",
        "Synapse",
        "Databricks",
        "Exasol",
        "SAPHANA",
        "Athena",
        "DB2",
    }
)


def _load_create_definition(definition: str | None, type_name: str) -> dict:
    if not definition:
        return {}
    dataset_definition = read_json_input(definition) or {}
    definition_type = dataset_definition.get("type")
    if definition_type is not None and definition_type != type_name:
        raise typer.BadParameter(
            f"--type {type_name!r} conflicts with definition type {definition_type!r}",
            param_hint="--type",
        )
    return dataset_definition


def _apply_create_connection(params: dict, connection: str | None) -> None:
    if connection and "connection" not in params:
        params["connection"] = connection


def _apply_sql_create_defaults(
    params: dict,
    *,
    dataset_type: str,
    definition: str | None,
    dataset_name: str,
) -> None:
    if dataset_type in _SQL_DATASET_TYPES and not definition:
        params.setdefault("mode", "table")
        params.setdefault("table", "${projectKey}_" + dataset_name)
        params.setdefault("tableCreationMode", "auto")


def _reject_misplaced_inline_flags(
    *,
    dataset_type: str,
    keep_track_of_changes: bool,
    enable_clipboard_api: bool,
    import_source: str | None,
) -> None:
    if dataset_type == "Inline":
        return
    if keep_track_of_changes or enable_clipboard_api or import_source is not None:
        exit_with_error(
            "--keep-track-of-changes / --enable-clipboard-api / --import-source "
            "are Inline-dataset flags.",
            details=[f"Use --type Inline (got '{dataset_type}'), or drop these flags."],
        )


def _apply_create_connection_specific_params(
    params: dict,
    *,
    catalog: str | None,
    view: str | None,
) -> None:
    if catalog is not None:
        params["catalog"] = catalog
    if view is not None:
        params["view"] = view.upper()


def _apply_create_format_flags(
    params: dict,
    format_params: dict,
    *,
    with_header: bool | None,
    csv_dialect: str | None,
    compress: str | None,
    parquet_compression: str | None,
    parquet_flavor: str | None,
    parquet_block_size_mb: int | None,
    read_temporal_mode: str | None,
) -> None:
    if with_header is not None:
        format_params["parseHeaderRow"] = bool(with_header)
    if csv_dialect is not None:
        format_params["style"] = csv_dialect
    if compress is not None:
        params["compress"] = compress
    if parquet_compression is not None:
        format_params["compressionCodec"] = parquet_compression
    if parquet_flavor is not None:
        format_params["flavor"] = parquet_flavor
    if parquet_block_size_mb is not None:
        format_params["blockSizeMB"] = parquet_block_size_mb
    if read_temporal_mode is not None:
        format_params["readTemporalMode"] = read_temporal_mode


def _apply_create_sql_write_params(
    params: dict,
    *,
    write_bad_data_behavior: str | None,
    write_batch_size: int | None,
    table_creation_mode: str | None,
    no_drop_on_schema_mismatch: bool,
    write_descriptions_as_comment: bool,
    num_partitions: int | None,
    datetime_notz_read_mode: str | None,
    dateonly_read_mode: str | None,
) -> None:
    if write_bad_data_behavior is not None:
        params["writeBadDataBehavior"] = write_bad_data_behavior
    if write_batch_size is not None:
        params["writeBatchSize"] = write_batch_size
    if table_creation_mode is not None:
        params["tableCreationMode"] = table_creation_mode
    if no_drop_on_schema_mismatch:
        params["dropOnSchemaMismatch"] = False
    if write_descriptions_as_comment:
        params["writeDescriptionsAsComment"] = True
    if num_partitions is not None:
        params["numPartitions"] = num_partitions
    if datetime_notz_read_mode is not None:
        params["dateTimeNoTZReadMode"] = datetime_notz_read_mode
    if dateonly_read_mode is not None:
        params["dateOnlyReadMode"] = dateonly_read_mode


def _apply_create_redshift_params(
    params: dict,
    *,
    dist_style: str | None,
    dist_key: str | None,
    sort_key: str | None,
    sort_key_columns: str | None,
) -> None:
    if dist_style is not None:
        params["redshiftDistStyle"] = dist_style
    if dist_key is not None:
        params["redshiftDistKey"] = dist_key
    if sort_key is not None:
        params["redshiftSortKey"] = sort_key
    if sort_key_columns is not None:
        params["redshiftSortKeyColumns"] = [
            c.strip() for c in sort_key_columns.split(",") if c.strip()
        ]


def _apply_create_bigquery_params(
    params: dict,
    *,
    use_bigquery_partitioning: bool,
    bigquery_partitioning_type: str | None,
    bigquery_partitioning_period: str | None,
    require_partition_filter: bool,
) -> None:
    if use_bigquery_partitioning:
        params["useBigQueryPartitioning"] = True
    if bigquery_partitioning_type is not None:
        params["bigQueryPartitioningType"] = bigquery_partitioning_type
    if bigquery_partitioning_period is not None:
        params["bigQueryPartitioningPeriod"] = bigquery_partitioning_period
    if require_partition_filter:
        params["requirePartitionFilter"] = True


def _apply_create_storage_params(
    params: dict,
    *,
    upload_provider: str | None,
    metastore_sync: bool,
    metastore_database: str | None,
    metastore_table: str | None,
) -> None:
    if upload_provider is not None:
        params["uploadProvider"] = upload_provider
    if metastore_sync:
        params["metastoreSynchronizationEnabled"] = True
    if metastore_database is not None:
        params["metastoreDatabase"] = metastore_database
    if metastore_table is not None:
        params["metastoreTable"] = metastore_table


def _apply_create_file_selection_params(
    params: dict,
    *,
    include_glob: list[str] | None,
    exclude_glob: list[str] | None,
    explicit_files: list[str] | None,
) -> None:
    if not (include_glob or exclude_glob or explicit_files):
        return
    selection = params.setdefault("filesSelectionRules", {})
    if include_glob:
        selection.setdefault("includeRules", []).extend(
            [{"expr": glob} for glob in include_glob]
        )
    if exclude_glob:
        selection.setdefault("excludeRules", []).extend(
            [{"expr": glob} for glob in exclude_glob]
        )
    if explicit_files:
        selection.setdefault("explicitFiles", []).extend(explicit_files)
    selection.setdefault("mode", "ALL")


def _apply_create_inline_params(
    params: dict,
    *,
    dataset_type: str,
    keep_track_of_changes: bool,
    enable_clipboard_api: bool,
    import_source: str | None,
) -> None:
    if dataset_type != "Inline":
        return
    params.pop("connection", None)
    if keep_track_of_changes:
        params.setdefault("keepTrackOfChanges", True)
    if enable_clipboard_api:
        params.setdefault("enableClipboardApi", True)
    if import_source is not None:
        params.setdefault("importSourceType", import_source)


def _apply_uploaded_files_connection(
    client,
    params: dict,
    *,
    dataset_type: str,
    connection: str | None,
) -> None:
    if dataset_type != "UploadedFiles" or "uploadConnection" in params:
        return
    if connection:
        params["uploadConnection"] = connection
        params.pop("connection", None)
        return
    try:
        conn_names = list(client.list_connections())
        for candidate in ["dataiku-managed-storage", "filesystem_managed"]:
            if candidate in conn_names:
                params["uploadConnection"] = candidate
                break
        if "uploadConnection" not in params and conn_names:
            params["uploadConnection"] = conn_names[0]
    except Exception:
        pass  # list_connections may require admin — fall through to create attempt


def _build_create_dataset_payload(
    *,
    dataset_name: str,
    type_name: str,
    connection: str | None,
    definition: str | None,
    keep_track_of_changes: bool,
    enable_clipboard_api: bool,
    import_source: str | None,
    catalog: str | None,
    view: str | None,
    with_header: bool | None,
    csv_dialect: str | None,
    compress: str | None,
    parquet_compression: str | None,
    parquet_flavor: str | None,
    parquet_block_size_mb: int | None,
    read_temporal_mode: str | None,
    write_bad_data_behavior: str | None,
    write_batch_size: int | None,
    table_creation_mode: str | None,
    no_drop_on_schema_mismatch: bool,
    write_descriptions_as_comment: bool,
    num_partitions: int | None,
    datetime_notz_read_mode: str | None,
    dateonly_read_mode: str | None,
    dist_style: str | None,
    dist_key: str | None,
    sort_key: str | None,
    sort_key_columns: str | None,
    use_bigquery_partitioning: bool,
    bigquery_partitioning_type: str | None,
    bigquery_partitioning_period: str | None,
    require_partition_filter: bool,
    upload_provider: str | None,
    metastore_sync: bool,
    metastore_database: str | None,
    metastore_table: str | None,
    include_glob: list[str] | None,
    exclude_glob: list[str] | None,
    explicit_files: list[str] | None,
    variable_loop: str | None,
) -> tuple[str, dict, dict, dict]:
    dataset_definition = _load_create_definition(definition, type_name)
    params = dataset_definition.get("params") or {}
    format_params: dict = dataset_definition.get("formatParams") or {}
    dataset_type = dataset_definition.get("type") or type_name

    _apply_create_connection(params, connection)
    _apply_sql_create_defaults(
        params,
        dataset_type=dataset_type,
        definition=definition,
        dataset_name=dataset_name,
    )
    _reject_misplaced_inline_flags(
        dataset_type=dataset_type,
        keep_track_of_changes=keep_track_of_changes,
        enable_clipboard_api=enable_clipboard_api,
        import_source=import_source,
    )
    _apply_create_connection_specific_params(params, catalog=catalog, view=view)
    _apply_create_format_flags(
        params,
        format_params,
        with_header=with_header,
        csv_dialect=csv_dialect,
        compress=compress,
        parquet_compression=parquet_compression,
        parquet_flavor=parquet_flavor,
        parquet_block_size_mb=parquet_block_size_mb,
        read_temporal_mode=read_temporal_mode,
    )
    _apply_create_sql_write_params(
        params,
        write_bad_data_behavior=write_bad_data_behavior,
        write_batch_size=write_batch_size,
        table_creation_mode=table_creation_mode,
        no_drop_on_schema_mismatch=no_drop_on_schema_mismatch,
        write_descriptions_as_comment=write_descriptions_as_comment,
        num_partitions=num_partitions,
        datetime_notz_read_mode=datetime_notz_read_mode,
        dateonly_read_mode=dateonly_read_mode,
    )
    _apply_create_redshift_params(
        params,
        dist_style=dist_style,
        dist_key=dist_key,
        sort_key=sort_key,
        sort_key_columns=sort_key_columns,
    )
    _apply_create_bigquery_params(
        params,
        use_bigquery_partitioning=use_bigquery_partitioning,
        bigquery_partitioning_type=bigquery_partitioning_type,
        bigquery_partitioning_period=bigquery_partitioning_period,
        require_partition_filter=require_partition_filter,
    )
    _apply_create_storage_params(
        params,
        upload_provider=upload_provider,
        metastore_sync=metastore_sync,
        metastore_database=metastore_database,
        metastore_table=metastore_table,
    )
    _apply_create_file_selection_params(
        params,
        include_glob=include_glob,
        exclude_glob=exclude_glob,
        explicit_files=explicit_files,
    )
    if variable_loop is not None:
        params["variablesExpansionLoopConfig"] = read_json_input(variable_loop)
    _apply_create_inline_params(
        params,
        dataset_type=dataset_type,
        keep_track_of_changes=keep_track_of_changes,
        enable_clipboard_api=enable_clipboard_api,
        import_source=import_source,
    )
    return dataset_type, params, format_params, dataset_definition


def _create_filesystem_dataset(proj, dataset_name: str, connection: str | None) -> None:
    builder = proj.new_managed_dataset(dataset_name)
    builder.with_store_into(connection or "filesystem_managed")
    builder.create()


def _translate_create_dataset_error(
    create_err: Exception,
    *,
    dataset_type: str,
    dataset_name: str,
    project_key: str,
) -> None:
    msg = str(create_err).lower()
    if dataset_type == "UploadedFiles" and ("connection" in msg or "target" in msg):
        exit_with_error(
            "Cannot create UploadedFiles dataset — no upload connection found.",
            details=[
                "Cloud DSS instances require an explicit upload connection.",
                f"Fix: dku dataset create {dataset_name} --type UploadedFiles --connection <CONNECTION_NAME> -P {project_key}",
                "Find connections: dku connection list",
            ],
        )
    if dataset_type == "SQL" and ("license" in msg and "sql" in msg):
        exit_with_error(
            "'--type SQL' is a catch-all name and is rejected by the DSS license system.",
            details=[
                "Use the concrete DB subtype instead:",
                "  --type PostgreSQL / --type MySQL / --type Snowflake /",
                "  --type Redshift / --type BigQuery / --type Oracle / --type SQLServer",
                "Run 'dku connection list' to see which connection types your instance has.",
                f"Example: dku dataset create {dataset_name} --type PostgreSQL -c <YOUR_CONN> -P {project_key}",
            ],
        )
