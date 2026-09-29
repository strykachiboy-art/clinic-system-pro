from __future__ import annotations

from app.core.observability.operational_metrics import (
    collect_operational_snapshot,
)


def _healthy_component(name):
    return {
        "component": name,
        "healthy": True,
        "value": 1,
    }


def test_operational_snapshot_collects_all_components():
    snapshot = collect_operational_snapshot(
        system_collector=lambda: _healthy_component(
            "system"
        ),
        redis_collector=lambda: _healthy_component(
            "redis"
        ),
        celery_collector=lambda: _healthy_component(
            "celery"
        ),
        socketio_collector=lambda: _healthy_component(
            "socketio"
        ),
        readiness_collector=lambda: {
            "ready": True,
            "database": {
                "healthy": True,
            },
            "redis": {
                "healthy": True,
            },
        },
    )

    assert snapshot["healthy"] is True

    assert set(
        snapshot["components"]
    ) == {
        "readiness",
        "system",
        "redis",
        "celery",
        "socketio",
    }

    for component in snapshot["components"].values():
        assert component["healthy"] is True
        assert component["available"] is True


def test_operational_snapshot_is_unhealthy_when_component_fails():
    snapshot = collect_operational_snapshot(
        system_collector=lambda: _healthy_component(
            "system"
        ),
        redis_collector=lambda: {
            "healthy": False,
            "reason": "unavailable",
        },
        celery_collector=lambda: _healthy_component(
            "celery"
        ),
        socketio_collector=lambda: _healthy_component(
            "socketio"
        ),
        readiness_collector=lambda: {
            "ready": True,
        },
    )

    assert snapshot["healthy"] is False
    assert snapshot["components"]["redis"][
        "healthy"
    ] is False
    assert snapshot["components"]["redis"][
        "available"
    ] is True


def test_operational_snapshot_contains_only_safe_error_metadata():
    snapshot = collect_operational_snapshot(
        system_collector=lambda: {
            "healthy": True,
        },
        redis_collector=lambda: (
            (_ for _ in ()).throw(
                RuntimeError(
                    "secret internal infrastructure detail"
                )
            )
        ),
        celery_collector=lambda: {
            "healthy": True,
        },
        socketio_collector=lambda: {
            "healthy": True,
        },
        readiness_collector=lambda: {
            "ready": True,
        },
    )

    redis = snapshot["components"]["redis"]

    assert snapshot["healthy"] is False
    assert redis["available"] is False
    assert redis["healthy"] is False
    assert redis["error_type"] == "RuntimeError"
    assert (
        "secret internal infrastructure detail"
        not in str(redis)
    )


def test_operational_snapshot_does_not_crash_when_readiness_fails():
    snapshot = collect_operational_snapshot(
        system_collector=lambda: {
            "healthy": True,
        },
        redis_collector=lambda: {
            "healthy": True,
        },
        celery_collector=lambda: {
            "healthy": True,
        },
        socketio_collector=lambda: {
            "healthy": True,
        },
        readiness_collector=lambda: (
            (_ for _ in ()).throw(
                ConnectionError(
                    "database unavailable"
                )
            )
        ),
    )

    assert snapshot["healthy"] is False

    readiness = snapshot[
        "components"
    ]["readiness"]

    assert readiness["available"] is False
    assert readiness["healthy"] is False
    assert readiness["error_type"] == (
        "ConnectionError"
    )


def test_operational_snapshot_has_timestamp():
    snapshot = collect_operational_snapshot(
        system_collector=lambda: {
            "healthy": True,
        },
        redis_collector=lambda: {
            "healthy": True,
        },
        celery_collector=lambda: {
            "healthy": True,
        },
        socketio_collector=lambda: {
            "healthy": True,
        },
        readiness_collector=lambda: {
            "ready": True,
        },
    )

    assert isinstance(
        snapshot["timestamp"],
        str,
    )
    assert snapshot["timestamp"]
