"""db.query() — pooling, statement timeout, deadlock retries, metrics."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import TypeVar

import structlog
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.engine import get_session_factory
from app.exceptions import DbTimeoutError
from app.metrics.cloudwatch import record_error, record_latency

logger = structlog.get_logger(__name__)

T = TypeVar("T")

# PostgreSQL retryable: deadlock_detected, serialization_failure
_RETRYABLE_SQLSTATES = {"40001", "40P01"}
_MAX_TIMEOUT_MS = 600_000  # 10 minutes cap


def _statement_timeout_literal(timeout_ms: int) -> str:
    """PostgreSQL SET LOCAL does not accept bind parameters ($1)."""
    ms = max(1, min(int(timeout_ms), _MAX_TIMEOUT_MS))
    return f"SET LOCAL statement_timeout = '{ms}ms'"


def _is_retryable(exc: OperationalError) -> bool:
    orig = getattr(exc, "orig", None)
    if orig is None:
        return False
    sqlstate = getattr(orig, "sqlstate", None) or getattr(orig, "pgcode", None)
    return sqlstate in _RETRYABLE_SQLSTATES


async def query(
    fn: Callable[[AsyncSession], Awaitable[T]],
    *,
    timeout_ms: int | None = None,
    retries: int = 3,
    operation: str = "db_query",
) -> T:
    settings = get_settings()
    timeout_ms = timeout_ms if timeout_ms is not None else settings.db_query_timeout_ms
    session_factory = get_session_factory()
    last_exc: Exception | None = None

    for attempt in range(1, retries + 1):
        start = time.perf_counter()
        try:
            async with session_factory() as session:
                await session.execute(text(_statement_timeout_literal(timeout_ms)))

                async def _run() -> T:
                    return await fn(session)

                result = await asyncio.wait_for(_run(), timeout=timeout_ms / 1000.0)
                duration_ms = (time.perf_counter() - start) * 1000
                record_latency("DbQueryDuration", duration_ms, {"Operation": operation})
                return result

        except asyncio.TimeoutError as exc:
            duration_ms = (time.perf_counter() - start) * 1000
            record_error("DbTimeout", {"Operation": operation})
            record_latency("DbQueryDuration", duration_ms, {"Operation": operation})
            logger.warning("db_query_timeout", operation=operation, timeout_ms=timeout_ms)
            raise DbTimeoutError(f"Query timed out after {timeout_ms}ms") from exc

        except OperationalError as exc:
            last_exc = exc
            if _is_retryable(exc) and attempt < retries:
                logger.warning(
                    "db_query_retry",
                    operation=operation,
                    attempt=attempt,
                    sqlstate=getattr(getattr(exc, "orig", None), "sqlstate", None),
                )
                await asyncio.sleep(0.05 * attempt)
                continue
            record_error("DbError", {"Operation": operation})
            raise

        except DBAPIError as exc:
            record_error("DbError", {"Operation": operation})
            if "pool" in str(exc).lower() or "timeout" in str(exc).lower():
                logger.error("db_pool_exhausted", operation=operation)
            raise

    assert last_exc is not None
    raise last_exc
