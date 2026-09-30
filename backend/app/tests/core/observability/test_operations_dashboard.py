from __future__ import annotations

import json

from app.core.observability.operations_dashboard_service import (
    get_operational_dashboard,
)


def _snapshot():
    return {
        "timestamp": "2026-09-29T10:00:00+00:00",
        "healthy": True,
        "components": {
            "readiness": {
                "available": True,
                "healthy": True,
                "database": {
                    "healthy": True,
                    "latency_ms": 1.5,
                },
                "redis": {
                    "healthy": True,
                    "latency_ms": 0.8,
                },
            },
            "system": {
                "available": True,
                "healthy": True,
                "cpu": {"percent": 20.0},
                "memory": {"percent": 35.0},
                "swap": {"percent": 0.0},
                "load_average": {
                    "one_minute": 0.5,
                    "five_minutes": 0.4,
                    "fifteen_minutes": 0.3,
                },
                "secret": "must-not-leak",
            },
            "redis": {
                "available": True,
                "healthy": True,
                "redis_version": "7.2.0",
                "connected_clients": 4,
                "blocked_clients": 0,
                "used_memory_bytes": 1024,
                "cache_hit_ratio": 0.9,
                "instantaneous_ops_per_sec": 12,
                "rejected_connections": 0,
                "evicted_keys": 0,
                "expired_keys": 2,
            },
            "celery": {
                "available": True,
                "healthy": True,
                "broker_healthy": True,
                "workers_healthy": True,
                "worker_count": 2,
                "total_concurrency": 8,
                "active_tasks": 1,
                "reserved_tasks": 2,
                "scheduled_tasks": 3,
                "worker_utilization_percent": 12.5,
                "queue_depths": {
                    "celery": 4,
                },
                "long_running_active_count": 0,
            },
            "socketio": {
                "available": True,
                "healthy": True,
                "server_available": True,
                "redis_coordination_healthy": True,
                "active_connections": 3,
                "room_count": 2,
                "message_queue_enabled": True,
            },
        },
    }


def _alerts(_snapshot):
    return [
        {
            "code": "system_cpu_high",
            "severity": "warning",
            "component": "system",
            "message": "System CPU utilization is high.",
            "observed_value": 95.0,
            "threshold": 90.0,
        },
        {
            "code": "redis_unhealthy",
            "severity": "critical",
            "component": "redis",
            "message": "Redis is unavailable or unhealthy.",
        },
    ]


class FakeRedis:
    def __init__(self, states):
        self.states = states

    def smembers(self, key):
        assert key == "observability:alert:active:v1"
        return set(self.states)

    def get(self, key):
        fingerprint = key.rsplit(":", 1)[-1]
        return self.states[fingerprint]


def _json_state(
    fingerprint,
    severity="critical",
):
    return json.dumps(
        {
            "fingerprint": fingerprint,
            "code": "redis_unhealthy",
            "severity": severity,
            "component": "redis",
            "resource": None,
            "message": "do-not-expose",
            "observed_value": None,
            "threshold": None,
            "occurrence_count": 2,
            "first_seen_at": "2026-09-29T09:00:00+00:00",
            "last_seen_at": "2026-09-29T09:59:00+00:00",
            "status": "active",
        }
    )


def test_dashboard_returns_curated_operational_view(
    user,
    monkeypatch,
):
    import app.core.observability.operations_dashboard_service as service

    monkeypatch.setattr(
        service,
        "collect_operational_snapshot",
        _snapshot,
    )

    monkeypatch.setattr(
        service,
        "evaluate_operational_alerts",
        _alerts,
    )

    result = get_operational_dashboard(
        actor_id=user.id,
        redis_client=FakeRedis(
            {
                "fp-1": _json_state(
                    "fp-1"
                ),
            }
        ),
    )

    assert result["schema_version"] == "v1"
    assert result["scope"] == "platform"
    assert result["healthy"] is True

    assert result["components"]["database"][
        "healthy"
    ] is True

    assert result["components"]["celery"][
        "queue_depths"
    ] == {"celery": 4}

    assert result["alerts"]["active_count"] == 1
    assert result["alerts"]["critical_count"] == 1

    serialized = str(result)

    assert "must-not-leak" not in serialized
    assert "do-not-expose" not in serialized


def test_dashboard_allows_super_admin(
    make_user,
    monkeypatch,
):
    from app.core.enums.role_enums import Role

    actor = make_user(
        role=Role.SUPER_ADMIN,
    )

    monkeypatch.setattr(
        "app.core.observability.operations_dashboard_service.collect_operational_snapshot",
        lambda: _snapshot(),
    )

    monkeypatch.setattr(
        "app.core.observability.operations_dashboard_service.evaluate_operational_alerts",
        lambda snapshot: [],
    )

    result = get_operational_dashboard(
        actor_id=actor.id,
        redis_client=FakeRedis({}),
    )

    assert result["scope"] == "platform"


def test_dashboard_rejects_non_operational_role(
    make_user,
    monkeypatch,
):
    from app.core.enums.role_enums import Role
    from app.core.exceptions import ValidationError

    actor = make_user(
        role=Role.DOCTOR,
    )

    monkeypatch.setattr(
        "app.core.observability.operations_dashboard_service.collect_operational_snapshot",
        lambda: (_ for _ in ()).throw(
            AssertionError(
                "snapshot must not be collected"
            )
        ),
    )

    try:
        get_operational_dashboard(
            actor_id=actor.id,
            redis_client=FakeRedis({}),
        )
    except ValidationError as exc:
        assert "not available" in str(exc)
    else:
        raise AssertionError(
            "Expected ValidationError"
        )


def test_dashboard_rejects_inactive_user(
    make_user,
):
    from app.core.exceptions import ValidationError

    actor = make_user(
        is_active=False,
    )

    try:
        get_operational_dashboard(
            actor_id=actor.id,
            redis_client=FakeRedis({}),
        )
    except ValidationError as exc:
        assert "inactive" in str(exc)
    else:
        raise AssertionError(
            "Expected ValidationError"
        )
