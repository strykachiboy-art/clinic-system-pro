from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable

from app.core.observability.celery_metrics import (
    collect_celery_metrics,
)
from app.core.observability.health import (
    collect_readiness,
)
from app.core.observability.redis_metrics import (
    collect_redis_metrics,
)
from app.core.observability.socketio_metrics import (
    collect_socketio_metrics,
)
from app.core.observability.system_metrics import (
    collect_system_metrics,
)


def _utcnow() -> str:
    return datetime.now(
        timezone.utc
    ).isoformat()


def _collect_component(
    collector: Callable[[], dict[str, Any]],
) -> dict[str, Any]:
    try:
        result = collector()

        if not isinstance(result, dict):
            return {
                "available": False,
                "healthy": False,
                "error_type": "InvalidCollectorResult",
            }

        result.setdefault(
            "available",
            True,
        )

        result.setdefault(
            "healthy",
            True,
        )

        return result

    except Exception as exc:
        return {
            "available": False,
            "healthy": False,
            "error_type": type(exc).__name__,
        }


def collect_operational_snapshot(
    *,
    system_collector: Callable[
        [],
        dict[str, Any],
    ] = collect_system_metrics,
    redis_collector: Callable[
        [],
        dict[str, Any],
    ] = collect_redis_metrics,
    celery_collector: Callable[
        [],
        dict[str, Any],
    ] = collect_celery_metrics,
    socketio_collector: Callable[
        [],
        dict[str, Any],
    ] = collect_socketio_metrics,
    readiness_collector: Callable[
        [],
        dict[str, Any],
    ] = collect_readiness,
) -> dict[str, Any]:
    components = {
        "readiness": _collect_component(
            readiness_collector
        ),
        "system": _collect_component(
            system_collector
        ),
        "redis": _collect_component(
            redis_collector
        ),
        "celery": _collect_component(
            celery_collector
        ),
        "socketio": _collect_component(
            socketio_collector
        ),
    }

    healthy = all(
        bool(
            component.get(
                "healthy",
                False,
            )
        )
        for component in components.values()
    )

    return {
        "timestamp": _utcnow(),
        "healthy": healthy,
        "components": components,
    }
