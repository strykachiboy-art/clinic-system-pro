from __future__ import annotations

from typing import Any


DEFAULT_THRESHOLDS = {
    "queue_depth_warning": 1000,
    "queue_depth_critical": 5000,
    "worker_utilization_warning_percent": 90.0,
    "cpu_warning_percent": 90.0,
    "memory_warning_percent": 90.0,
    "swap_warning_percent": 50.0,
    "long_running_task_warning_count": 1,
}


def _alert(
    *,
    code: str,
    severity: str,
    component: str,
    message: str,
    observed_value: Any = None,
    threshold: Any = None,
) -> dict[str, Any]:
    return {
        "code": code,
        "severity": severity,
        "component": component,
        "message": message,
        "observed_value": observed_value,
        "threshold": threshold,
    }


def _get_thresholds(
    overrides: dict[str, Any] | None,
) -> dict[str, Any]:
    thresholds = dict(
        DEFAULT_THRESHOLDS
    )

    if overrides:
        for key, value in overrides.items():
            if key in thresholds:
                thresholds[key] = value

    return thresholds


def evaluate_operational_alerts(
    snapshot: dict[str, Any],
    *,
    thresholds: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    if not isinstance(snapshot, dict):
        raise TypeError(
            "snapshot must be a dictionary"
        )

    resolved = _get_thresholds(
        thresholds
    )

    components = snapshot.get(
        "components",
        {},
    )

    if not isinstance(components, dict):
        raise ValueError(
            "snapshot components must be a dictionary"
        )

    alerts: list[dict[str, Any]] = []

    readiness = components.get(
        "readiness",
        {},
    )

    if not readiness.get(
        "healthy",
        False,
    ):
        alerts.append(
            _alert(
                code="readiness_failed",
                severity="critical",
                component="readiness",
                message=(
                    "Application readiness check failed."
                ),
            )
        )

    redis = components.get(
        "redis",
        {},
    )

    if not redis.get(
        "healthy",
        False,
    ):
        alerts.append(
            _alert(
                code="redis_unhealthy",
                severity="critical",
                component="redis",
                message=(
                    "Redis is unavailable or unhealthy."
                ),
            )
        )

    celery = components.get(
        "celery",
        {},
    )

    if not celery.get(
        "broker_healthy",
        False,
    ):
        alerts.append(
            _alert(
                code="celery_broker_unhealthy",
                severity="critical",
                component="celery",
                message=(
                    "Celery broker is unavailable or unhealthy."
                ),
            )
        )

    if not celery.get(
        "workers_healthy",
        False,
    ):
        alerts.append(
            _alert(
                code="celery_workers_unavailable",
                severity="critical",
                component="celery",
                message=(
                    "No healthy Celery workers are available."
                ),
            )
        )

    queue_depths = celery.get(
        "queue_depths",
        {},
    )

    if isinstance(
        queue_depths,
        dict,
    ):
        for queue_name, depth in queue_depths.items():
            if not isinstance(
                depth,
                (int, float),
            ):
                continue

            if depth >= resolved[
                "queue_depth_critical"
            ]:
                alerts.append(
                    _alert(
                        code="celery_queue_depth_critical",
                        severity="critical",
                        component="celery",
                        message=(
                            "Celery queue depth is critically high."
                        ),
                        observed_value=depth,
                        threshold=resolved[
                            "queue_depth_critical"
                        ],
                    )
                )

            elif depth >= resolved[
                "queue_depth_warning"
            ]:
                alerts.append(
                    _alert(
                        code="celery_queue_depth_high",
                        severity="warning",
                        component="celery",
                        message=(
                            "Celery queue depth is high."
                        ),
                        observed_value=depth,
                        threshold=resolved[
                            "queue_depth_warning"
                        ],
                    )
                )

    worker_utilization = celery.get(
        "worker_utilization_percent"
    )

    if isinstance(
        worker_utilization,
        (int, float),
    ) and worker_utilization >= resolved[
        "worker_utilization_warning_percent"
    ]:
        alerts.append(
            _alert(
                code="celery_worker_utilization_high",
                severity="warning",
                component="celery",
                message=(
                    "Celery worker utilization is high."
                ),
                observed_value=worker_utilization,
                threshold=resolved[
                    "worker_utilization_warning_percent"
                ],
            )
        )

    long_running_count = celery.get(
        "long_running_active_count",
        0,
    )

    if (
        isinstance(
            long_running_count,
            (int, float),
        )
        and long_running_count
        >= resolved[
            "long_running_task_warning_count"
        ]
    ):
        alerts.append(
            _alert(
                code="celery_long_running_tasks",
                severity="warning",
                component="celery",
                message=(
                    "Long-running Celery tasks are active."
                ),
                observed_value=long_running_count,
                threshold=resolved[
                    "long_running_task_warning_count"
                ],
            )
        )

    system = components.get(
        "system",
        {},
    )

    cpu = system.get(
        "cpu",
        {},
    )

    cpu_percent = cpu.get(
        "percent"
    )

    if isinstance(
        cpu_percent,
        (int, float),
    ) and cpu_percent >= resolved[
        "cpu_warning_percent"
    ]:
        alerts.append(
            _alert(
                code="system_cpu_high",
                severity="warning",
                component="system",
                message=(
                    "System CPU utilization is high."
                ),
                observed_value=cpu_percent,
                threshold=resolved[
                    "cpu_warning_percent"
                ],
            )
        )

    memory = system.get(
        "memory",
        {},
    )

    memory_percent = memory.get(
        "percent"
    )

    if isinstance(
        memory_percent,
        (int, float),
    ) and memory_percent >= resolved[
        "memory_warning_percent"
    ]:
        alerts.append(
            _alert(
                code="system_memory_high",
                severity="warning",
                component="system",
                message=(
                    "System memory utilization is high."
                ),
                observed_value=memory_percent,
                threshold=resolved[
                    "memory_warning_percent"
                ],
            )
        )

    swap = system.get(
        "swap",
        {},
    )

    swap_percent = swap.get(
        "percent"
    )

    if isinstance(
        swap_percent,
        (int, float),
    ) and swap_percent >= resolved[
        "swap_warning_percent"
    ]:
        alerts.append(
            _alert(
                code="system_swap_high",
                severity="warning",
                component="system",
                message=(
                    "System swap utilization is high."
                ),
                observed_value=swap_percent,
                threshold=resolved[
                    "swap_warning_percent"
                ],
            )
        )

    return alerts
