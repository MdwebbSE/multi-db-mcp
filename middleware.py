"""Rate limiting and authentication middleware."""
from __future__ import annotations

import hmac
import logging
import os
import re
import time
from collections import defaultdict
from threading import Lock
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

MCP_BEARER_TOKEN = os.getenv("MCP_BEARER_TOKEN", "")

# Rate limiting configuration
RATE_LIMIT_REQUESTS = int(os.getenv("RATE_LIMIT_REQUESTS", "100"))  # requests per window
RATE_LIMIT_WINDOW = int(os.getenv("RATE_LIMIT_WINDOW", "60"))  # seconds

# In-memory rate limiting storage
_rate_limit_store: dict[str, list[float]] = defaultdict(list)
_rate_limit_lock = Lock()

logger = logging.getLogger("multi-db-mcp")


def get_client_ip(request: Request) -> str:
    """Extract client IP from request, checking X-Forwarded-For header."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def is_rate_limited(ip: str) -> bool:
    """Check if IP has exceeded rate limit."""
    current_time = time.time()
    window_start = current_time - RATE_LIMIT_WINDOW

    with _rate_limit_lock:
        # Clean old entries for the current IP
        _rate_limit_store[ip] = [t for t in _rate_limit_store[ip] if t > window_start]

        # Remove stale IPs from the store (IPs with no timestamps)
        stale_ips = [key for key, timestamps in _rate_limit_store.items() if not timestamps]
        for stale_ip in stale_ips:
            del _rate_limit_store[stale_ip]

        # Check if limit exceeded
        if len(_rate_limit_store[ip]) >= RATE_LIMIT_REQUESTS:
            return True

        # Add current request
        _rate_limit_store[ip].append(current_time)
        return False


class BearerAuthMiddleware(BaseHTTPMiddleware):
    """Middleware for bearer token authentication and rate limiting."""

    async def dispatch(self, request: Request, call_next):
        if request.url.path in ("/", "/health"):
            return await call_next(request)

        client_ip = get_client_ip(request)

        # Check rate limit
        if is_rate_limited(client_ip):
            logger.warning("Rate limit exceeded for IP: %s", client_ip)
            return JSONResponse({"error": "rate limit exceeded"}, status_code=429)

        auth_header = request.headers.get("authorization", "")
        if not isinstance(auth_header, str):
            return JSONResponse({"error": "invalid token format"}, status_code=400)
        
        # Extract token from "Bearer <token>" format
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
        else:
            token = auth_header
        
        # If no token is configured, skip authentication
        if not MCP_BEARER_TOKEN:
            return await call_next(request)
        
        # Validate token format (allow JWT-compatible characters: alphanumeric, dash, underscore, period)
        if not re.match(r"^[A-Za-z0-9-_.]{10,}$", token):
            return JSONResponse({"error": "invalid token format"}, status_code=400)
        
        # Use constant-time comparison to prevent timing attacks
        auth_ok = hmac.compare_digest(token, MCP_BEARER_TOKEN)

        if not auth_ok:
            return JSONResponse({"error": "unauthorized"}, status_code=401)

        return await call_next(request)
