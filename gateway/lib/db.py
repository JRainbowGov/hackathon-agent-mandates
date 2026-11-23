"""Postgres connection pool for the gateway's audit and history store (schema: db/init/01_schema.sql).

Off unless GATEWAY_DATABASE_URL is set (docker-compose.observability.yaml sets it). With it unset, psycopg is
never imported and the gateway behaves exactly as before.

Scaffold only: no gateway decision reads or writes the database yet. Writing audit events, DB-backed nonces,
budgets and suspensions are later changes. When a decision does depend on the DB, a DB error must deny
(fail closed); `get_pool()` raising is the hook for that.

The gateway connects as GATEWAY_DB_USER, which may SELECT/INSERT on audit_events but not UPDATE, DELETE or
TRUNCATE it.
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

from fastapi import APIRouter
from fastapi.responses import JSONResponse

if TYPE_CHECKING:
    from psycopg_pool import AsyncConnectionPool

log = logging.getLogger(__name__)

URL_ENV = "GATEWAY_DATABASE_URL"
OPEN_TIMEOUT_S = 10.0

_pool: AsyncConnectionPool | None = None


def enabled() -> bool:
    return bool(os.environ.get(URL_ENV))


async def open_pool() -> AsyncConnectionPool | None:
    """Open the pool if GATEWAY_DATABASE_URL is set. Fails startup if the DB is configured but unreachable."""
    global _pool  # noqa: PLW0603
    if not enabled() or _pool is not None:
        return _pool
    from psycopg_pool import AsyncConnectionPool  # noqa: PLC0415

    pool = AsyncConnectionPool(os.environ[URL_ENV], min_size=1, max_size=5, open=False, name="gateway")
    await pool.open(wait=True, timeout=OPEN_TIMEOUT_S)
    _pool = pool
    log.info("database pool open")
    return _pool


async def close_pool() -> None:
    global _pool  # noqa: PLW0603
    if _pool is not None:
        await _pool.close()
        _pool = None


def get_pool() -> AsyncConnectionPool:
    """The open pool. Raises if the DB is not configured, so callers that need it fail closed."""
    if _pool is None:
        msg = f"database not configured ({URL_ENV} unset) or not open"
        raise RuntimeError(msg)
    return _pool


async def health() -> dict:
    """{'status': 'disabled' | 'ok' | 'error', ...}. Never includes connection details or error text."""
    if _pool is None:
        return {"status": "disabled"}
    try:
        async with _pool.connection(timeout=2.0) as conn:
            cur = await conn.execute("SELECT max(version) FROM gateway.schema_version")
            row = await cur.fetchone()
    except Exception:  # noqa: BLE001  (health probe: any failure is "error")
        log.warning("database health check failed", exc_info=True)
        return {"status": "error"}
    return {"status": "ok", "schema_version": row[0] if row else None}


router = APIRouter()


@router.get("/healthcheck/db")
async def healthcheck_db() -> JSONResponse:
    """Separate from /healthcheck so the container probe never depends on the DB."""
    result = await health()
    return JSONResponse(result, status_code=503 if result["status"] == "error" else 200)
