"""Multi-database MCP HTTP server entry point."""
from __future__ import annotations

import asyncio
import contextlib

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse, Response
from starlette.routing import Mount, Route

from config import load_config, READ_ONLY, MAX_ROWS
from db import close_all_pools
from middleware import BearerAuthMiddleware
from tools import mcp


import time

_cached_config = None
_config_last_loaded = 0
_config_lock = asyncio.Lock()
CONFIG_CACHE_TTL = 60  # seconds

async def health(_: Request) -> Response:
    """Health check endpoint."""
    global _cached_config, _config_last_loaded

    # Check if cache needs refresh
    if not _cached_config or (time.time() - _config_last_loaded > CONFIG_CACHE_TTL):
        async with _config_lock:
            # Double-check after acquiring lock to avoid race condition
            if not _cached_config or (time.time() - _config_last_loaded > CONFIG_CACHE_TTL):
                _cached_config = load_config()
                _config_last_loaded = time.time()

    return JSONResponse(
        {
            "ok": True,
            "read_only": READ_ONLY,
            "max_rows": MAX_ROWS,
            "configured_servers": list(_cached_config["servers"].keys()),
        }
    )


async def index(_: Request) -> Response:
    """Root endpoint."""
    return PlainTextResponse("Multi-DB MCP server is running.")


@contextlib.asynccontextmanager
async def lifespan(app: Starlette):
    """Application lifespan handler."""
    async with mcp.session_manager.run():
        yield
    # Close all connection pools on shutdown
    close_all_pools()


app = Starlette(
    routes=[
        Route("/", endpoint=index),
        Route("/health", endpoint=health),
        Mount("/", app=mcp.streamable_http_app()),
    ],
    middleware=[Middleware(BearerAuthMiddleware)],
    lifespan=lifespan,
)
