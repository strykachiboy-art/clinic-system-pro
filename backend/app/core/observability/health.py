from __future__ import annotations

import time
from datetime import datetime, timezone

from sqlalchemy import text

from app import extensions


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _check_database() -> dict[str, object]:
    started_at = time.perf_counter()

    try:
        with extensions.db.engine.connect() as connection:
            connection.execute(text("SELECT 1"))

        healthy = True
    except Exception:
        healthy = False

    return {
        "healthy": healthy,
        "latency_ms": (
            time.perf_counter() - started_at
        ) * 1000.0,
    }


def _check_redis() -> dict[str, object]:
    started_at = time.perf_counter()

    try:
        client = extensions.redis_client

        if client is None:
            raise RuntimeError(
                "Redis client is not initialized"
            )

        client.ping()
        healthy = True
    except Exception:
        healthy = False

    return {
        "healthy": healthy,
        "latency_ms": (
            time.perf_counter() - started_at
        ) * 1000.0,
    }


def collect_readiness() -> dict[str, object]:
    database = _check_database()
    redis = _check_redis()

    ready = bool(
        database["healthy"]
        and redis["healthy"]
    )

    return {
        "timestamp": _utcnow(),
        "ready": ready,
        "database": database,
        "redis": redis,
    }
