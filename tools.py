"""MCP tools for database operations."""
from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP, Context

from config import build_transport_security, MAX_ROWS, READ_ONLY
from db import (
    get_connection,
    release_connection,
    fetch_rows,
    validate_identifier,
    is_read_only_sql,
    validate_sql_query,
    get_server_config,
)


def get_header_map(ctx: Context) -> dict[str, str]:
    """Extract headers from context."""
    # Streamable HTTP transport: ctx.request_context.request.headers
    request_context = getattr(ctx, "request_context", None)
    if request_context is not None:
        request = getattr(request_context, "request", None)
        if request is not None:
            headers = getattr(request, "headers", None)
            if headers:
                return {k.lower(): v for k, v in headers.items()}

    # Legacy: ctx.request
    request = getattr(ctx, "request", None)
    if request is not None:
        headers = getattr(request, "headers", None)
        if headers:
            return {k.lower(): v for k, v in headers.items()}

    # Fallback: ctx.meta
    meta = getattr(ctx, "meta", None)
    if isinstance(meta, dict):
        headers = meta.get("headers")
        if isinstance(headers, dict):
            return {k.lower(): v for k, v in headers.items()}

    return {}


def resolve_db_target(
    ctx: Context,
    db_server: str | None = None,
    database: str | None = None,
) -> tuple[str, str]:
    """Resolve database target from context or headers."""
    headers = get_header_map(ctx)

    if not db_server:
        db_server = headers.get("x-db-server")

    if not database:
        database = headers.get("x-database")

    if not db_server or not database:
        raise ValueError(
            "db_server and database must be specified, either as tool arguments "
            "or via X-DB-Server / X-Database headers."
        )

    return db_server, database


mcp = FastMCP(
    "multi-db",
    instructions=(
        "Use db_server and database exactly as provided by the available server list. "
        "Prefer read-only inspection and avoid broad queries."
    ),
    json_response=True,
    transport_security=build_transport_security(),
)


@mcp.tool()
def get_current_database(ctx: Context) -> dict[str, str | None]:
    """Return the default db_server and database from request headers."""
    headers = get_header_map(ctx)
    return {
        "db_server": headers.get("x-db-server"),
        "database": headers.get("x-database"),
    }


@mcp.tool()
def list_tables(
    ctx: Context,
    db_server: str | None = None,
    database: str | None = None,
    schema: str | None = None,
) -> list[dict[str, Any]]:
    """
    List tables in a database.

    For MySQL, schema defaults to the database name.
    For MSSQL, schema defaults to 'dbo'.
    """
    db_server, database = resolve_db_target(ctx, db_server, database)
    engine, conn = get_connection(db_server, database)

    try:
        with conn.cursor() as cur:
            if engine == "mysql":
                target_schema = schema or database
                cur.execute(
                    """
                    SELECT table_name, table_type
                    FROM information_schema.tables
                    WHERE table_schema = %s
                    ORDER BY table_name
                    """,
                    (target_schema,),
                )
            else:
                target_schema = schema or "dbo"
                cur.execute(
                    """
                    SELECT TABLE_NAME AS table_name, TABLE_TYPE AS table_type
                    FROM INFORMATION_SCHEMA.TABLES
                    WHERE TABLE_CATALOG = ? AND TABLE_SCHEMA = ?
                    ORDER BY TABLE_NAME
                    """,
                    (database, target_schema),
                )

            return fetch_rows(cur)
    finally:
        release_connection(db_server, database, conn)


@mcp.tool()
def describe_table(
    ctx: Context,
    table_name: str,
    db_server: str | None = None,
    database: str | None = None,
    schema: str | None = None,
) -> list[dict[str, Any]]:
    """
    Describe a table's columns.
    """
    db_server, database = resolve_db_target(ctx, db_server, database)
    table_name = validate_identifier(table_name, "table_name")
    engine, conn = get_connection(db_server, database)

    try:
        with conn.cursor() as cur:
            if engine == "mysql":
                target_schema = schema or database
                cur.execute(
                    """
                    SELECT
                        column_name,
                        column_type,
                        is_nullable,
                        column_key,
                        column_default,
                        extra
                    FROM information_schema.columns
                    WHERE table_schema = %s
                      AND table_name = %s
                    ORDER BY ordinal_position
                    """,
                    (target_schema, table_name),
                )
            else:
                target_schema = schema or "dbo"
                cur.execute(
                    """
                    SELECT
                        COLUMN_NAME AS column_name,
                        DATA_TYPE AS data_type,
                        IS_NULLABLE AS is_nullable,
                        COLUMN_DEFAULT AS column_default,
                        CHARACTER_MAXIMUM_LENGTH AS character_maximum_length,
                        NUMERIC_PRECISION AS numeric_precision,
                        NUMERIC_SCALE AS numeric_scale
                    FROM INFORMATION_SCHEMA.COLUMNS
                    WHERE TABLE_CATALOG = ?
                      AND TABLE_SCHEMA = ?
                      AND TABLE_NAME = ?
                    ORDER BY ORDINAL_POSITION
                    """,
                    (database, target_schema, table_name),
                )

            return fetch_rows(cur)
    finally:
        release_connection(db_server, database, conn)


@mcp.tool()
def run_query(
    ctx: Context,
    sql: str,
    db_server: str | None = None,
    database: str | None = None,
) -> dict[str, Any]:
    """
    Run a query against the selected server and database.
    Read-only mode allows only SELECT/SHOW/DESCRIBE/EXPLAIN/WITH style queries.
    """
    db_server, database = resolve_db_target(ctx, db_server, database)

    # Always validate SQL for basic safety
    validate_sql_query(sql)

    if READ_ONLY and not is_read_only_sql(sql):
        raise ValueError(
            "Read-only mode is enabled. Only SELECT/SHOW/DESCRIBE/EXPLAIN/WITH queries are allowed."
        )

    engine, conn = get_connection(db_server, database)

    try:
        with conn.cursor() as cur:
            cur.execute(sql)

            if cur.description:
                rows = fetch_rows(cur)
                limited = rows[:MAX_ROWS]
                return {
                    "engine": engine,
                    "db_server": db_server,
                    "database": database,
                    "row_count": len(limited),
                    "truncated": len(rows) > len(limited),
                    "rows": limited,
                }

            return {
                "engine": engine,
                "db_server": db_server,
                "database": database,
                "row_count": 0,
                "truncated": False,
                "rows": [],
                "affected_rows": cur.rowcount,
                "message": "Statement executed successfully.",
            }
    finally:
        release_connection(db_server, database, conn)


@mcp.tool()
def preview_table(
    ctx: Context,
    table_name: str,
    limit: int = 50,
    db_server: str | None = None,
    database: str | None = None,
) -> dict[str, Any]:
    db_server, database = resolve_db_target(ctx, db_server, database)
    table_name = validate_identifier(table_name, "table_name")
    engine, conn = get_connection(db_server, database)

    limit = max(1, min(limit, 200))

    cfg = get_server_config(db_server)
    allowed_tables = cfg.get("allowed_tables", {}).get(database)
    if allowed_tables is not None and table_name not in allowed_tables:
        raise ValueError(f"Table '{table_name}' is not allowed")

    try:
        with conn.cursor() as cur:
            if engine == "mysql":
                sql = f"SELECT * FROM `{table_name}` LIMIT %s"
                cur.execute(sql, (limit,))
            else:
                sql = f"SELECT TOP ({limit}) * FROM [{table_name}]"
                cur.execute(sql)

            rows = fetch_rows(cur)
            return {
                "engine": engine,
                "db_server": db_server,
                "database": database,
                "table_name": table_name,
                "row_count": len(rows),
                "rows": rows,
            }
    finally:
        release_connection(db_server, database, conn)


@mcp.tool()
def select_where(
    ctx: Context,
    table_name: str,
    filters: dict[str, Any],
    limit: int = 50,
    db_server: str | None = None,
    database: str | None = None,
) -> dict[str, Any]:
    """
    Select rows from a table using column=value filters.
    Example filters: {"user_id": 123, "status": "active"}
    """

    db_server, database = resolve_db_target(ctx, db_server, database)
    table_name = validate_identifier(table_name, "table_name")
    engine, conn = get_connection(db_server, database)

    limit = max(1, min(limit, 200))

    cfg = get_server_config(db_server)
    allowed_tables = cfg.get("allowed_tables", {}).get(database)

    if allowed_tables is not None and table_name not in allowed_tables:
        raise ValueError(f"Table '{table_name}' is not allowed")

    if not filters:
        raise ValueError("filters cannot be empty")

    try:
        with conn.cursor() as cur:

            where_parts = []
            params = []

            for column, value in filters.items():
                validate_identifier(column, "column")

                if engine == "mysql":
                    where_parts.append(f"`{column}` = %s")
                else:
                    where_parts.append(f"[{column}] = ?")

                params.append(value)

            where_clause = " AND ".join(where_parts)

            if engine == "mysql":
                sql = f"SELECT * FROM `{table_name}` WHERE {where_clause} LIMIT %s"
                params.append(limit)

            else:
                sql = f"SELECT TOP ({limit}) * FROM [{table_name}] WHERE {where_clause}"

            cur.execute(sql, params)
            rows = fetch_rows(cur)

            return {
                "engine": engine,
                "db_server": db_server,
                "database": database,
                "table_name": table_name,
                "row_count": len(rows),
                "rows": rows,
            }

    finally:
        release_connection(db_server, database, conn)


@mcp.tool()
def list_columns(
    ctx: Context,
    table_name: str,
    db_server: str | None = None,
    database: str | None = None,
    schema: str | None = None,
) -> list[dict[str, Any]]:
    """
    List columns of a table.
    """

    db_server, database = resolve_db_target(ctx, db_server, database)
    table_name = validate_identifier(table_name, "table_name")
    engine, conn = get_connection(db_server, database)

    try:
        with conn.cursor() as cur:

            if engine == "mysql":
                target_schema = schema or database

                cur.execute(
                    """
                    SELECT
                        COLUMN_NAME AS column_name,
                        DATA_TYPE AS data_type,
                        IS_NULLABLE AS is_nullable,
                        COLUMN_KEY AS column_key,
                        COLUMN_DEFAULT AS column_default
                    FROM information_schema.columns
                    WHERE table_schema = %s
                      AND table_name = %s
                    ORDER BY ordinal_position
                    """,
                    (target_schema, table_name),
                )

            else:
                target_schema = schema or "dbo"

                cur.execute(
                    """
                    SELECT
                        COLUMN_NAME AS column_name,
                        DATA_TYPE AS data_type,
                        IS_NULLABLE AS is_nullable,
                        COLUMN_DEFAULT AS column_default,
                        CHARACTER_MAXIMUM_LENGTH AS character_maximum_length,
                        NUMERIC_PRECISION AS numeric_precision,
                        NUMERIC_SCALE AS numeric_scale
                    FROM INFORMATION_SCHEMA.COLUMNS
                    WHERE TABLE_CATALOG = ?
                      AND TABLE_SCHEMA = ?
                      AND TABLE_NAME = ?
                    ORDER BY ORDINAL_POSITION
                    """,
                    (database, target_schema, table_name),
                )

            return fetch_rows(cur)

    finally:
        release_connection(db_server, database, conn)
