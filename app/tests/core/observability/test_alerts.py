from __future__ import annotations

from app.core.observability.alerts import (
    evaluate_operational_alerts,
)


def _healthy_snapshot():
    return {
        "healthy": True,
        "components": {
            "readiness": {
                "healthy": True,
            },
            "redis": {
                "healthy": True,
            },
            "celery": {
                "healthy": True,
                "broker_healthy": True,
                "workers_healthy": True,
                "queue_depths": {
                    "celery": 10,
                },
                "worker_utilization_percent": 40.0,
                "long_running_active_count": 0,
            },
            "system": {
                "healthy": True,
                "cpu": {
                    "percent": 30.0,
                },
                "memory": {
                    "percent": 40.0,
                },
                "swap": {
                    "percent": 5.0,
                },
            },
        },
    }


def test_healthy_snapshot_has_no_alerts():
    alerts = evaluate_operational_alerts(
        _healthy_snapshot()
    )

    assert alerts == []


def test_readiness_failure_is_critical():
    snapshot = _healthy_snapshot()

    snapshot["components"]["readiness"][
        "healthy"
    ] = False

    alerts = evaluate_operational_alerts(
        snapshot
    )

    assert alerts == [
        {
            "code": "readiness_failed",
            "severity": "critical",
            "component": "readiness",
            "message": (
                "Application readiness check failed."
            ),
            "observed_value": None,
            "threshold": None,
        }
    ]


def test_redis_and_celery_dependency_failures_are_critical():
    snapshot = _healthy_snapshot()

    snapshot["components"]["redis"][
        "healthy"
    ] = False

    snapshot["components"]["celery"][
        "broker_healthy"
    ] = False

    snapshot["components"]["celery"][
        "workers_healthy"
    ] = False

    alerts = evaluate_operational_alerts(
        snapshot
    )

    codes = {
        alert["code"]
        for alert in alerts
    }

    assert codes == {
        "redis_unhealthy",
        "celery_broker_unhealthy",
        "celery_workers_unavailable",
    }

    assert all(
        alert["severity"] == "critical"
        for alert in alerts
    )


def test_queue_depth_warning_and_critical_thresholds():
    snapshot = _healthy_snapshot()

    snapshot["components"]["celery"][
        "queue_depths"
    ] = {
        "warning-queue": 1000,
        "critical-queue": 5000,
    }

    alerts = evaluate_operational_alerts(
        snapshot
    )

    assert {
        alert["code"]
        for alert in alerts
    } == {
        "celery_queue_depth_high",
        "celery_queue_depth_critical",
    }

    observed = {
        (
            alert["code"],
            alert["observed_value"],
            alert["threshold"],
        )
        for alert in alerts
    }

    assert observed == {
        (
            "celery_queue_depth_high",
            1000,
            1000,
        ),
        (
            "celery_queue_depth_critical",
            5000,
            5000,
        ),
    }


def test_system_pressure_generates_warnings():
    snapshot = _healthy_snapshot()

    snapshot["components"]["system"]["cpu"][
        "percent"
    ] = 95.0

    snapshot["components"]["system"]["memory"][
        "percent"
    ] = 92.0

    snapshot["components"]["system"]["swap"][
        "percent"
    ] = 60.0

    alerts = evaluate_operational_alerts(
        snapshot
    )

    assert {
        alert["code"]
        for alert in alerts
    } == {
        "system_cpu_high",
        "system_memory_high",
        "system_swap_high",
    }

    assert all(
        alert["severity"] == "warning"
        for alert in alerts
    )


def test_celery_pressure_generates_warnings():
    snapshot = _healthy_snapshot()

    snapshot["components"]["celery"][
        "worker_utilization_percent"
    ] = 95.0

    snapshot["components"]["celery"][
        "long_running_active_count"
    ] = 2

    alerts = evaluate_operational_alerts(
        snapshot
    )

    assert {
        alert["code"]
        for alert in alerts
    } == {
        "celery_worker_utilization_high",
        "celery_long_running_tasks",
    }

    assert all(
        alert["severity"] == "warning"
        for alert in alerts
    )


def test_threshold_overrides_are_applied():
    snapshot = _healthy_snapshot()

    snapshot["components"]["celery"][
        "queue_depths"
    ] = {
        "celery": 25,
    }

    alerts = evaluate_operational_alerts(
        snapshot,
        thresholds={
            "queue_depth_warning": 20,
            "queue_depth_critical": 100,
        },
    )

    assert len(alerts) == 1

    assert alerts[0]["code"] == (
        "celery_queue_depth_high"
    )

    assert alerts[0]["observed_value"] == 25
    assert alerts[0]["threshold"] == 20


def test_invalid_snapshot_is_rejected():
    try:
        evaluate_operational_alerts(
            None
        )
    except TypeError as exc:
        assert str(exc) == (
            "snapshot must be a dictionary"
        )
    else:
        raise AssertionError(
            "Expected TypeError"
        )


def test_alerts_do_not_include_raw_exception_text():
    snapshot = _healthy_snapshot()

    snapshot["components"]["redis"][
        "healthy"
    ] = False

    snapshot["components"]["redis"][
        "error"
    ] = "password=super-secret-value"

    alerts = evaluate_operational_alerts(
        snapshot
    )

    serialized = str(alerts)

    assert (
        "super-secret-value"
        not in serialized
    )
    assert "password=" not in serialized
