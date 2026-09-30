from __future__ import annotations

from unittest.mock import Mock

import pytest

from app.core.observability import (
    celery_metrics,
)


class FakeTask:
    name = "example.task"

    def __init__(
        self,
        app,
    ):
        self.app = app


def _celery_app_mock():
    app = Mock()
    app.extensions = {}
    app.conf.get.return_value = "celery"
    app.control.inspect.return_value = Mock()

    return app


def _configure_inspector(
    app,
):
    inspector = app.control.inspect.return_value

    inspector.ping.return_value = {
        "worker-1": {
            "ok": "pong",
        }
    }

    inspector.stats.return_value = {
        "worker-1": {
            "pool": {
                "max-concurrency": 4,
            },
            "pid": 1234,
            "total": {
                "example.task": 10,
                "other.task": 5,
            },
            "rusage": {
                "utime": 1.5,
                "stime": 0.5,
                "maxrss": 2048,
            },
        }
    }

    inspector.active.return_value = {
        "worker-1": []
    }

    inspector.reserved.return_value = {
        "worker-1": []
    }

    inspector.scheduled.return_value = {
        "worker-1": []
    }

    inspector.registered.return_value = {
        "worker-1": [
            "example.task",
            "other.task",
        ]
    }


def test_init_celery_metrics_registers_state():
    app = _celery_app_mock()

    celery_metrics.init_celery_metrics(
        app
    )

    assert (
        celery_metrics.CELERY_METRICS_STATE_KEY
        in app.extensions
    )

    assert (
        app.extensions[
            celery_metrics.CELERY_METRICS_STATE_KEY
        ]["registered"]
        is True
    )


def test_collect_celery_metrics_returns_worker_metrics():
    app = _celery_app_mock()
    _configure_inspector(app)

    redis = Mock()

    redis.ping.return_value = True
    redis.llen.return_value = 3
    redis.hgetall.return_value = {}

    redis.scan_iter.return_value = iter([])

    result = celery_metrics.collect_celery_metrics(
        celery_app=app,
        client=redis,
    )

    assert result["healthy"] is True
    assert result["broker_healthy"] is True
    assert result["workers_healthy"] is True

    assert result["worker_count"] == 1
    assert result["worker_names"] == [
        "worker-1"
    ]

    assert result["total_concurrency"] == 4
    assert result["active_tasks"] == 0
    assert result["reserved_tasks"] == 0
    assert result["scheduled_tasks"] == 0

    assert (
        result["worker_utilization_percent"]
        == 0.0
    )

    assert result["queue_depths"] == {
        "celery": 3,
    }

    assert result["worker_pids"] == [
        1234
    ]

    assert result["worker_task_totals"] == {
        "example.task": 10,
        "other.task": 5,
    }


def test_collect_celery_metrics_counts_active_tasks():
    app = _celery_app_mock()
    _configure_inspector(app)

    inspector = app.control.inspect.return_value

    inspector.active.return_value = {
        "worker-1": [
            {
                "id": "task-1",
                "name": "example.task",
                "time_start": 1000.0,
            },
            {
                "id": "task-2",
                "name": "other.task",
                "time_start": 1001.0,
            },
        ]
    }

    redis = Mock()
    redis.ping.return_value = True
    redis.llen.return_value = 0
    redis.hgetall.return_value = {}
    redis.scan_iter.return_value = iter([])

    result = celery_metrics.collect_celery_metrics(
        celery_app=app,
        client=redis,
    )

    assert result["active_tasks"] == 2
    assert (
        result["worker_utilization_percent"]
        == 50.0
    )


def test_collect_celery_metrics_detects_long_running_tasks(
    monkeypatch,
):
    app = _celery_app_mock()
    _configure_inspector(app)

    inspector = app.control.inspect.return_value

    inspector.active.return_value = {
        "worker-1": [
            {
                "id": "task-1",
                "name": "example.task",
                "time_start": 100.0,
            }
        ]
    }

    monkeypatch.setattr(
        celery_metrics.time,
        "time",
        lambda: 120.0,
    )

    redis = Mock()
    redis.ping.return_value = True
    redis.llen.return_value = 0
    redis.hgetall.return_value = {}
    redis.scan_iter.return_value = iter([])

    result = celery_metrics.collect_celery_metrics(
        celery_app=app,
        client=redis,
        long_running_threshold_seconds=10,
    )

    assert (
        result["long_running_active_count"]
        == 1
    )

    task = result[
        "long_running_active_tasks"
    ][0]

    assert task["task_id"] == "task-1"
    assert task["name"] == "example.task"
    assert task["runtime_seconds"] == 20.0


def test_collect_celery_metrics_returns_task_metrics():
    app = _celery_app_mock()
    _configure_inspector(app)

    redis = Mock()

    redis.ping.return_value = True
    redis.llen.return_value = 0

    task_metrics = {
        (
            "observability:celery:task:v1:"
            "example.task"
        ): {
            "started_tasks": "10",
            "executed_tasks": "8",
            "succeeded_tasks": "7",
            "failed_tasks": "1",
            "retry_events": "2",
            "revoked_tasks": "0",
            "runtime_ms_total": "4000",
            "last_runtime_ms": "500",
            "max_runtime_ms": "900",
            "long_running_tasks": "1",
        },
        (
            "observability:celery:task:v1:"
            "other.task"
        ): {
            "started_tasks": "5",
            "executed_tasks": "5",
            "succeeded_tasks": "5",
            "failed_tasks": "0",
            "retry_events": "0",
            "revoked_tasks": "0",
            "runtime_ms_total": "2500",
            "last_runtime_ms": "600",
            "max_runtime_ms": "700",
            "long_running_tasks": "0",
        },
    }

    def hgetall(key):
        if (
            key
            == celery_metrics.CELERY_AGGREGATE_KEY
        ):
            return {}

        return task_metrics.get(
            str(key),
            {},
        )

    redis.hgetall.side_effect = hgetall

    redis.scan_iter.return_value = iter(
        task_metrics.keys()
    )

    result = celery_metrics.collect_celery_metrics(
        celery_app=app,
        client=redis,
    )

    metrics = result["task_metrics"]

    assert metrics[
        "example.task"
    ]["executed_tasks"] == 8

    assert metrics[
        "example.task"
    ]["average_runtime_ms"] == 500.0

    assert metrics[
        "other.task"
    ]["executed_tasks"] == 5


def test_task_prerun_records_started_task(
    monkeypatch,
):
    app = _celery_app_mock()
    task = FakeTask(app)

    celery_metrics.init_celery_metrics(
        app
    )

    monkeypatch.setattr(
        celery_metrics.time,
        "perf_counter",
        lambda: 10.0,
    )

    redis = Mock()

    monkeypatch.setattr(
        celery_metrics,
        "_get_redis_client",
        lambda: redis,
    )

    celery_metrics._handle_task_prerun(
        task_id="task-1",
        task=task,
    )

    assert (
        celery_metrics._TASK_START_TIMES[
            "task-1"
        ]
        == 10.0
    )

    assert redis.hincrby.call_count >= 2


def test_task_postrun_records_success_runtime(
    monkeypatch,
):
    app = _celery_app_mock()
    task = FakeTask(app)

    celery_metrics.init_celery_metrics(
        app
    )

    celery_metrics._TASK_START_TIMES[
        "task-1"
    ] = 10.0

    monkeypatch.setattr(
        celery_metrics.time,
        "perf_counter",
        lambda: 10.75,
    )

    redis = Mock()
    redis.hget.return_value = "0"

    monkeypatch.setattr(
        celery_metrics,
        "_get_redis_client",
        lambda: redis,
    )

    celery_metrics._handle_task_postrun(
        task_id="task-1",
        task=task,
        state="SUCCESS",
    )

    assert (
        "task-1"
        not in celery_metrics._TASK_START_TIMES
    )

    calls = [
        call.args
        for call in (
            redis.hincrbyfloat.call_args_list
        )
    ]

    assert any(
        call[1] == "runtime_ms_total"
        and call[2] == 750.0
        for call in calls
    )


def test_task_retry_increments_retry_metrics():
    app = _celery_app_mock()
    task = FakeTask(app)

    celery_metrics.init_celery_metrics(
        app
    )

    redis = Mock()

    original_get_client = (
        celery_metrics._get_redis_client
    )

    celery_metrics._get_redis_client = (
        lambda: redis
    )

    try:
        celery_metrics._handle_task_retry(
            sender=task,
            task_id="task-1",
        )
    finally:
        celery_metrics._get_redis_client = (
            original_get_client
        )

    assert redis.hincrby.call_count >= 2


def test_task_revoked_increments_revoked_metrics():
    app = _celery_app_mock()
    task = FakeTask(app)

    celery_metrics.init_celery_metrics(
        app
    )

    redis = Mock()

    original_get_client = (
        celery_metrics._get_redis_client
    )

    celery_metrics._get_redis_client = (
        lambda: redis
    )

    try:
        celery_metrics._handle_task_revoked(
            sender=task,
            task_id="task-1",
        )
    finally:
        celery_metrics._get_redis_client = (
            original_get_client
        )

    assert redis.hincrby.call_count >= 2


def test_collect_celery_metrics_rejects_invalid_timeout():
    app = _celery_app_mock()

    with pytest.raises(ValueError):
        celery_metrics.collect_celery_metrics(
            celery_app=app,
            client=Mock(),
            inspect_timeout=0,
        )


def test_collect_celery_metrics_rejects_invalid_long_running_threshold():
    app = _celery_app_mock()

    with pytest.raises(ValueError):
        celery_metrics.collect_celery_metrics(
            celery_app=app,
            client=Mock(),
            long_running_threshold_seconds=0,
        )


def test_collect_celery_metrics_rejects_invalid_queue_name():
    app = _celery_app_mock()
    _configure_inspector(app)

    redis = Mock()
    redis.ping.return_value = True

    with pytest.raises(ValueError):
        celery_metrics.collect_celery_metrics(
            celery_app=app,
            client=redis,
            queue_names=[""],
        )