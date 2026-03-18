"""Database connections, pooling, and SQL helpers."""
from __future__ import annotations

import logging
import os
import re
import time
from collections import defaultdict
from threading import Lock
from typing import Any

import pymysql
from pymysql.cursors import DictCursor as MySQLDictCursor
from mssql_python import connect as mssql_connect

from config import get_server_config, validate_database_allowed, READ_ONLY, MAX_ROWS

logger = logging.getLogger("multi-db-mcp")

# Connection pool configuration
POOL_MAX_CONNECTIONS = int(os.getenv("DB_POOL_MAX_CONNECTIONS", "10"))
POOL_MIN_CONNECTIONS = int(os.getenv("DB_POOL_MIN_CONNECTIONS", "2"))
POOL_RECYCLE_SECONDS = int(os.getenv("DB_POOL_RECYCLE_SECONDS", "3600"))

# Connection pool storage: (db_server, database) -> list of (connection, created_at)
_connection_pools: dict[tuple[str, str], list[tuple[Any, float]]] = defaultdict(list)
_pool_lock = Lock()


def get_pooled_connection(db_server: str, database: str):
    """Get a connection from the pool or create a new one."""
    pool_key = (db_server, database)

    with _pool_lock:
        pool = _connection_pools[pool_key]

        # Try to get an existing connection from the pool
        current_time = time.time()
        while pool:
            conn, created_at = pool.pop()
            try:
                if conn.open and (current_time - created_at) < POOL_RECYCLE_SECONDS:
                    return conn
            except Exception as e:
                logger.warning("Discarding dead connection due to error: %s", e)

    # No available connection in pool, create a new one
    server_cfg = get_server_config(db_server)
    validate_database_allowed(server_cfg, database)

    engine = server_cfg["engine"].lower()
    if engine == "mysql":
        conn = mysql_connection(server_cfg, database)
    elif engine == "mssql":
        conn = mssql_connection(server_cfg, database)
    else:
        raise ValueError(f"Unsupported engine '{engine}' for db_server '{db_server}'")

    return conn


def return_connection_to_pool(db_server: str, database: str, conn: Any) -> None:
    """Return a connection to the pool."""
    pool_key = (db_server, database)

    with _pool_lock:
        pool = _connection_pools[pool_key]

        # Only return if pool is not full and connection is still alive
        if len(pool) < POOL_MAX_CONNECTIONS:
            try:
                if conn.open:
                    pool.append(conn)
                    return
            except Exception as e:
                logger.warning("Failed to return connection to pool: %s", e)

    # Pool is full or connection is dead, close it
    try:
        conn.close()
    except Exception as e:
        logger.warning("Error closing connection: %s", e)


def close_all_pools() -> None:
    """Close all connections in all pools."""
    with _pool_lock:
        for pool in _connection_pools.values():
            for conn in pool:
                try:
                    conn.close()
                except Exception:
                    pass
        _connection_pools.clear()


def validate_identifier(value: str, name: str) -> str:
    """Validate SQL identifier (table name, column name)."""
    if not re.fullmatch(r"[A-Za-z0-9_\-$]+", value):
        raise ValueError(f"Invalid {name}: {value}")
    return value


def validate_sql_query(sql: str) -> None:
    """
    Validate SQL query for basic safety.
    Raises ValueError if the query contains potentially dangerous patterns.
    """
    if not sql or not sql.strip():
        raise ValueError("SQL query cannot be empty")

    # Remove comments to check the actual SQL
    normalized = sql.strip()
    normalized = re.sub(r"--.*$", "", normalized, flags=re.MULTILINE)
    normalized = re.sub(r"/\*.*?\*/", "", normalized, flags=re.DOTALL)

    # Check for stacked queries (multiple statements)
    statements = [s.strip() for s in normalized.split(";") if s.strip()]
    if len(statements) > 1:
        raise ValueError("Multiple statements in a single query are not allowed")

    # Check for common SQL injection patterns (specific attacks, not general keywords)
    injection_patterns = [
        # Classic SQL injection: 'OR '1'='1
        (r"'\s*OR\s+'1'\s*=\s*'1", "SQL injection attempt detected"),
        # Numeric OR injection: 'OR 1=1
        (r"'\s*OR\s+\d+\s*=\s*\d+", "SQL injection attempt detected"),
        # UNION-based injection
        (r"\bUNION\s+(ALL\s+)?SELECT", "UNION SELECT injection attempt detected"),
        # Stacked queries after semicolon (redundant with check above, but extra safety)
        (r";\s*(drop|delete|insert|update|create|alter|truncate|exec|execute)", "Dangerous statement after semicolon"),
        # Tautology-based injection patterns
        (r"OR\s+1\s*=\s*1", "Tautology OR injection detected"),
        (r"OR\s+'[^']*'\s*=\s*'[^']*", "Tautology OR injection detected"),
    ]

    for pattern, message in injection_patterns:
        if re.search(pattern, normalized, re.IGNORECASE):
            raise ValueError(message)


def is_read_only_sql(sql: str) -> bool:
    """Validate that SQL query is read-only using multiple checks."""
    if not sql or not sql.strip():
        return False

    # Remove comments and normalize whitespace
    normalized = sql.strip()
    normalized = re.sub(r"--.*$", "", normalized, flags=re.MULTILINE)  # Remove single-line comments
    normalized = re.sub(r"/\*.*?\*/", "", normalized, flags=re.DOTALL)  # Remove block comments
    normalized = normalized.lower().rstrip(";").strip()

    if not normalized:
        return False

    # Check for dangerous SQL constructs that could modify data
    dangerous_keywords = [
        "insert", "update", "delete", "drop", "alter", "truncate",
        "create", "replace", "grant", "revoke", "rename", "call",
        "exec", "execute", "merge", "load", "into outfile", "into dumpfile",
    ]

    for keyword in dangerous_keywords:
        # Use word boundary to match whole words only
        if re.search(r'\b' + re.escape(keyword) + r'\b', normalized):
            return False

    # Check for UNION attacks (could be used to extract data from other tables)
    if re.search(r'\bunion\b', normalized):
        return False

    # Check for sensitive system databases/tables
    sensitive_patterns = [
        r"\binformation_schema\b",
        r"\bmysql\b",
        r"\bmsdb\b",
        r"\bmaster\b",
        r"\bsys\b",
        r"\bpg_catalog\b",
    ]

    for pattern in sensitive_patterns:
        if re.search(pattern, normalized):
            return False

    # Only allow specific read-only prefixes
    allowed_prefixes = ("select", "show", "describe", "desc", "explain", "with", "use", "set")

    if not normalized.startswith(allowed_prefixes):
        return False

    return True


def mysql_connection(server_cfg: dict[str, Any], database: str):
    """Create a MySQL database connection."""
    return pymysql.connect(
        host=server_cfg["host"],
        port=int(server_cfg.get("port", 3306)),
        user=server_cfg["user"],
        password=server_cfg["password"],
        database=database,
        charset="utf8mb4",
        autocommit=True,
        cursorclass=MySQLDictCursor,
        connect_timeout=int(server_cfg.get("connect_timeout", 10)),
        read_timeout=int(server_cfg.get("read_timeout", 30)),
        write_timeout=int(server_cfg.get("write_timeout", 30)),
    )


def mssql_connection(server_cfg: dict[str, Any], database: str):
    """Create a MSSQL database connection."""
    encrypt = "yes" if server_cfg.get("encrypt", True) else "no"
    trust = "yes" if server_cfg.get("trust_server_certificate", False) else "no"

    connection_string = (
        f"Server={server_cfg['host']},{int(server_cfg.get('port', 1433))};"
        f"Database={database};"
        f"User Id={server_cfg['user']};"
        f"Password={server_cfg['password']};"
        f"Encrypt={encrypt};"
        f"TrustServerCertificate={trust};"
        f"Connection Timeout={int(server_cfg.get('connect_timeout', 10))};"
    )
    return mssql_connect(connection_string)


def get_connection(db_server: str, database: str):
    """Get a connection from the pool or create a new one."""
    server_cfg = get_server_config(db_server)
    validate_database_allowed(server_cfg, database)

    engine = server_cfg["engine"].lower()
    conn = get_pooled_connection(db_server, database)
    return engine, conn


def release_connection(db_server: str, database: str, conn: Any) -> None:
    """Return a connection to the pool."""
    return_connection_to_pool(db_server, database, conn)


def fetch_rows(cursor) -> list[dict[str, Any]]:
    """Fetch all rows from cursor and convert to list of dicts."""
    rows = cursor.fetchall()
    result = []

    for row in rows:
        if isinstance(row, dict):
            result.append(row)
            continue

        if hasattr(row, "_asdict"):
            result.append(row._asdict())
            continue

        if hasattr(cursor, "description") and cursor.description:
            columns = [col[0] for col in cursor.description]
            result.append(dict(zip(columns, row)))
            continue

        result.append({"value": row})

    return result
