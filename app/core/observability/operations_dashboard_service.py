from __future__ import annotations

import json
from typing import Any, Callable

from app import extensions
from app.core.auth.user.models.user_model import User
from app.core.enums.role_enums import Role
from app.core.exceptions import NotFoundError, ValidationError
from app.core.observability.alerts import (
    evaluate_operational_alerts,
)
from app.core.observability.alert_state import (
    ALERT_ACTIVE_SET_KEY,
    ALERT_STATE_PREFIX,
)
from app.core.observability.operational_metrics import (
    collect_operational_snapshot,
)
from app.extensions import db


OPERATIONAL_DASHBOARD_ROLES = {
    Role.ADMIN,
    Role.SUPER_ADMIN,
}


def _get_authorized_user(
    actor_id: int,
) -> User:
    if (
        isinstance(actor_id, bool)
        or not isinstance(actor_id, int)
        or actor_id <= 0
    ):
        raise ValidationError(
            "Actor ID must be a positive integer"
        )

    actor = db.session.get(
        User,
        actor_id,
    )

    if actor is None:
        raise NotFoundError(
            f"User {actor_id} not found"
        )

    if not actor.is_active:
        raise ValidationError(
            "User account is inactive"
        )

    if actor.role not in OPERATIONAL_DASHBOARD_ROLES:
        raise ValidationError(
            "Operational dashboard is not available "
            "to this user"
        )

    return actor


def _read_value(
    value: Any,
) -> str | None:
    if value is None:
        return None

    if isinstance(value, bytes):
        return value.decode(
            "utf-8",
            errors="replace",
        )

    return str(value)


def _read_active_alerts(
    redis_client,
) -> dict[str, Any]:
    if redis_client is None:
        return {
            "available": False,
            "active": [],
            "error_type": "RedisUnavailable",
        }

    try:
        raw_fingerprints = (
            redis_client.smembers(
                ALERT_ACTIVE_SET_KEY
            )
        )
    except Exception as exc:
        return {
            "available": False,
            "active": [],
            "error_type": type(exc).__name__,
        }

    alerts = []

    for raw_fingerprint in raw_fingerprints:
        fingerprint = _read_value(
            raw_fingerprint
        )

        if not fingerprint:
            continue

        try:
            raw_state = redis_client.get(
                f"{ALERT_STATE_PREFIX}{fingerprint}"
            )
        except Exception:
            continue

        raw_state = _read_value(
            raw_state
        )

        if not raw_state:
            continue

        try:
            state = json.loads(
                raw_state
            )
        except (TypeError, ValueError):
            continue

        if not isinstance(
            state,
            dict,
        ):
            continue

        if state.get("status") != "active":
            continue

        alerts.append(
            {
                "fingerprint": state.get(
                    "fingerprint"
                ),
                "code": state.get(
                    "code"
                ),
                "severity": state.get(
                    "severity"
                ),
                "component": state.get(
                    "component"
                ),
                "resource": state.get(
                    "resource"
                ),
                "observed_value": state.get(
                    "observed_value"
                ),
                "threshold": state.get(
                    "threshold"
                ),
                "occurrence_count": state.get(
                    "occurrence_count"
                ),
                "first_seen_at": state.get(
                    "first_seen_at"
                ),
                "last_seen_at": state.get(
                    "last_seen_at"
                ),
            }
        )

    severity_rank = {
        "critical": 3,
        "warning": 2,
        "info": 1,
    }

    alerts.sort(
        key=lambda item: (
            -severity_rank.get(
                str(
                    item.get(
                        "severity"
                    )
                ),
                0,
            ),
            str(
                item.get("code")
                or ""
            ),
            str(
                item.get("resource")
                or ""
            ),
            str(
                item.get("fingerprint")
                or ""
            ),
        )
    )

    return {
        "available": True,
        "active": alerts,
    }


def _safe_alert(
    alert: dict[str, Any],
) -> dict[str, Any]:
    return {
        "code": alert.get(
            "code"
        ),
        "severity": alert.get(
            "severity"
        ),
        "component": alert.get(
            "component"
        ),
        "resource": alert.get(
            "resource"
        ),
        "observed_value": alert.get(
            "observed_value"
        ),
        "threshold": alert.get(
            "threshold"
        ),
        "occurrence_count": alert.get(
            "occurrence_count"
        ),
        "first_seen_at": alert.get(
            "first_seen_at"
        ),
        "last_seen_at": alert.get(
            "last_seen_at"
        ),
    }


def _build_components(
    snapshot: dict[str, Any],
) -> dict[str, Any]:
    components = snapshot.get(
        "components",
        {},
    )

    readiness = components.get(
        "readiness",
        {},
    )

    database = readiness.get(
        "database",
        {},
    )

    readiness_redis = readiness.get(
        "redis",
        {},
    )

    system = components.get(
        "system",
        {},
    )

    cpu = system.get(
        "cpu",
        {},
    )

    memory = system.get(
        "memory",
        {},
    )

    swap = system.get(
        "swap",
        {},
    )

    celery = components.get(
        "celery",
        {},
    )

    redis = components.get(
        "redis",
        {},
    )

    socketio = components.get(
        "socketio",
        {},
    )

    return {
        "database": {
            "available": bool(
                readiness.get(
                    "available",
                    False,
                )
            ),
            "healthy": bool(
                database.get(
                    "healthy",
                    False,
                )
            ),
            "latency_ms": database.get(
                "latency_ms"
            ),
        },
        "redis": {
            "available": bool(
                redis.get(
                    "available",
                    False,
                )
            ),
            "healthy": bool(
                redis.get(
                    "healthy",
                    False,
                )
            ),
            "latency_ms": (
                readiness_redis.get(
                    "latency_ms"
                )
            ),
            "redis_version": redis.get(
                "redis_version"
            ),
            "connected_clients": redis.get(
                "connected_clients"
            ),
            "blocked_clients": redis.get(
                "blocked_clients"
            ),
            "used_memory_bytes": redis.get(
                "used_memory_bytes"
            ),
            "cache_hit_ratio": redis.get(
                "cache_hit_ratio"
            ),
            "instantaneous_ops_per_sec": (
                redis.get(
                    "instantaneous_ops_per_sec"
                )
            ),
            "rejected_connections": (
                redis.get(
                    "rejected_connections"
                )
            ),
            "evicted_keys": redis.get(
                "evicted_keys"
            ),
            "expired_keys": redis.get(
                "expired_keys"
            ),
        },
        "system": {
            "available": bool(
                system.get(
                    "available",
                    False,
                )
            ),
            "healthy": bool(
                system.get(
                    "healthy",
                    False,
                )
            ),
            "cpu_percent": cpu.get(
                "percent"
            ),
            "memory_percent": memory.get(
                "percent"
            ),
            "swap_percent": swap.get(
                "percent"
            ),
            "load_average": system.get(
                "load_average"
            ),
        },
        "celery": {
            "available": bool(
                celery.get(
                    "available",
                    False,
                )
            ),
            "healthy": bool(
                celery.get(
                    "healthy",
                    False,
                )
            ),
            "broker_healthy": celery.get(
                "broker_healthy",
                False,
            ),
            "workers_healthy": celery.get(
                "workers_healthy",
                False,
            ),
            "worker_count": celery.get(
                "worker_count",
                0,
            ),
            "total_concurrency": celery.get(
                "total_concurrency",
                0,
            ),
            "active_tasks": celery.get(
                "active_tasks",
                0,
            ),
            "reserved_tasks": celery.get(
                "reserved_tasks",
                0,
            ),
            "scheduled_tasks": celery.get(
                "scheduled_tasks",
                0,
            ),
            "worker_utilization_percent": (
                celery.get(
                    "worker_utilization_percent",
                    0.0,
                )
            ),
            "queue_depths": celery.get(
                "queue_depths",
                {},
            ),
            "long_running_active_count": (
                celery.get(
                    "long_running_active_count",
                    0,
                )
            ),
        },
        "socketio": {
            "available": bool(
                socketio.get(
                    "available",
                    False,
                )
            ),
            "healthy": bool(
                socketio.get(
                    "healthy",
                    False,
                )
            ),
            "server_available": socketio.get(
                "server_available",
                False,
            ),
            "redis_coordination_healthy": (
                socketio.get(
                    "redis_coordination_healthy",
                    False,
                )
            ),
            "active_connections": socketio.get(
                "active_connections",
                0,
            ),
            "room_count": socketio.get(
                "room_count",
                0,
            ),
            "message_queue_enabled": (
                socketio.get(
                    "message_queue_enabled",
                    False,
                )
            ),
        },
    }


def get_operational_dashboard(
    *,
    actor_id: int,
    snapshot_collector: Callable[
        [],
        dict[str, Any],
    ] | None = None,
    alert_evaluator: Callable[
        [dict[str, Any]],
        list[dict[str, Any]],
    ] | None = None,
    redis_client=None,
) -> dict[str, Any]:
    _get_authorized_user(
        actor_id
    )

    if snapshot_collector is None:
        snapshot_collector = (
            collect_operational_snapshot
        )

    if alert_evaluator is None:
        alert_evaluator = (
            evaluate_operational_alerts
        )

    snapshot = snapshot_collector()

    if not isinstance(
        snapshot,
        dict,
    ):
        raise ValidationError(
            "Operational snapshot is invalid"
        )

    current_alerts = alert_evaluator(
        snapshot
    )

    if redis_client is None:
        redis_client = (
            extensions.redis_client
        )

    active_alert_state = (
        _read_active_alerts(
            redis_client
        )
    )

    safe_current_alerts = [
        _safe_alert(alert)
        for alert in current_alerts
        if isinstance(
            alert,
            dict,
        )
    ]

    safe_active_alerts = [
        alert
        for alert in active_alert_state[
            "active"
        ]
        if isinstance(
            alert,
            dict,
        )
    ]

    return {
        "schema_version": "v1",
        "scope": "platform",
        "timestamp": snapshot.get(
            "timestamp"
        ),
        "healthy": bool(
            snapshot.get(
                "healthy",
                False,
            )
        ),
        "components": _build_components(
            snapshot
        ),
        "alerts": {
            "current_conditions": (
                safe_current_alerts
            ),
            "current_count": len(
                safe_current_alerts
            ),
            "active": safe_active_alerts,
            "active_count": len(
                safe_active_alerts
            ),
            "critical_count": sum(
                1
                for alert in safe_active_alerts
                if alert.get(
                    "severity"
                )
                == "critical"
            ),
            "warning_count": sum(
                1
                for alert in safe_active_alerts
                if alert.get(
                    "severity"
                )
                == "warning"
            ),
            "state_store_available": bool(
                active_alert_state[
                    "available"
                ]
            ),
        },
    }
