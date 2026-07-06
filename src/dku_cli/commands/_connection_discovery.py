from __future__ import annotations

from dku_cli.output import warn


def list_connection_schemas(proj, connection_name: str, fmt: str) -> list:
    # Lazy: keep the HTTP stack off the `dku --help` cold-import path.
    from dataikuapi.utils import DataikuException

    sql_error: Exception | None = None
    try:
        return proj.list_sql_schemas(connection_name)
    except DataikuException as exc:
        sql_error = exc
    try:
        return proj.list_iceberg_namespaces(connection_name)
    except DataikuException as ice_exc:
        if fmt != "json":
            warn(f"Could not list SQL schemas for '{connection_name}': {sql_error}")
            warn(
                f"Could not list Iceberg namespaces for '{connection_name}': {ice_exc}"
            )
        return []


def list_connection_tables(
    proj, connection_name: str, schema_name: str | None, fmt: str
) -> list:
    from dataikuapi.utils import DataikuException

    sql_error: Exception | None = None
    try:
        return proj.list_sql_tables(connection_name, schema_name=schema_name)
    except DataikuException as exc:
        sql_error = exc
    try:
        return proj.list_iceberg_tables(connection_name, namespace=schema_name)
    except DataikuException as ice_exc:
        if fmt != "json":
            warn(f"Could not list SQL tables for '{connection_name}': {sql_error}")
            warn(f"Could not list Iceberg tables for '{connection_name}': {ice_exc}")
        return []
