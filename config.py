"""Configuration loading and validation."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from mcp.server.transport_security import TransportSecuritySettings

CONFIG_PATH = Path(os.getenv("DB_SERVERS_CONFIG", "./db_servers.json"))
READ_ONLY = os.getenv("DB_READ_ONLY", "true").lower() == "true"
MAX_ROWS = int(os.getenv("DB_MAX_ROWS", "200"))


def load_config() -> dict[str, Any]:
    """Load database server configuration from JSON file."""
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(f"Config file not found: {CONFIG_PATH}")
    with CONFIG_PATH.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if "servers" not in data or not isinstance(data["servers"], dict):
        raise ValueError("Config must contain a top-level 'servers' object")
    return data


def build_transport_security() -> TransportSecuritySettings:
    """Build transport security settings from config."""
    config = load_config()
    ts = config.get("transport_security", {})

    return TransportSecuritySettings(
        enable_dns_rebinding_protection=ts.get("enable_dns_rebinding_protection", True),
        allowed_hosts=ts.get("allowed_hosts", ["localhost:*", "127.0.0.1:*"]),
        allowed_origins=ts.get("allowed_origins", []),
    )


def get_server_config(db_server: str) -> dict[str, Any]:
    """Get configuration for a specific database server."""
    config = load_config()
    servers = config["servers"]
    if db_server not in servers:
        raise ValueError(f"Unknown db_server: {db_server}")
    server_cfg = servers[db_server]
    if "engine" not in server_cfg:
        raise ValueError(f"Server '{db_server}' is missing 'engine'")
    return server_cfg


def validate_database_allowed(server_cfg: dict[str, Any], database: str) -> None:
    """Validate that the database is allowed for the server."""
    allowed = server_cfg.get("allowed_databases")
    if allowed is None:
        return
    if database not in allowed:
        raise ValueError(f"Database '{database}' is not allowed for this db_server")
