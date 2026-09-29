from __future__ import annotations

import json

import pytest

from app.core.observability.failure_events import (
    FAILURE_EVENTS_KEY,
    collect_failure_events,
    record_failure_event,
    summarize_failure_events,
)


class FakeRedis:
    def __init__(self):
        self.items = []

    def lpush(self, key, value):
        assert key == FAILURE_EVENTS_KEY
        self.items.insert(0, value)
        return len(self.items)

    def ltrim(self, key, start, end):
        assert key == FAILURE_EVENTS_KEY

        self.items = self.items[
            start : end + 1
        ]

        return True

    def expire(self, key, seconds):
        assert key == FAILURE_EVENTS_KEY
        assert seconds > 0
        return True

    def lrange(self, key, start, end):
        assert key == FAILURE_EVENTS_KEY

        return self.items[
            start : end + 1
        ]


def test_record_failure_event_stores_safe_operational_fields():
    redis = FakeRedis()

    event = record_failure_event(
        redis_client=redis,
        event_type="application.error",
        component="api",
        severity="error",
        timestamp="2026-09-29T10:00:00+00:00",
        request_id="request-1\r\n",
        route="/api/v1/test",
        method="GET",
        status=500,
        error_type="RuntimeError",
    )

    assert event is not None
    assert event["request_id"] == "request-1"
    assert event["error_type"] == "RuntimeError"
    assert "message" not in event
    assert "traceback" not in event


def test_collect_failure_events_reads_recent_events():
    redis = FakeRedis()

    record_failure_event(
        redis_client=redis,
        event_type="http.5xx",
        component="api",
        status=503,
    )

    events = collect_failure_events(
        redis_client=redis
    )

    assert len(events) == 1
    assert events[0]["event_type"] == (
        "http.5xx"
    )


def test_record_failure_event_rejects_unknown_event_type():
    redis = FakeRedis()

    with pytest.raises(ValueError):
        record_failure_event(
            redis_client=redis,
            event_type="secret.event",
            component="api",
        )


def test_collect_failure_events_limits_results():
    redis = FakeRedis()

    for index in range(5):
        record_failure_event(
            redis_client=redis,
            event_type="http.5xx",
            component=f"api-{index}",
        )

    events = collect_failure_events(
        redis_client=redis,
        limit=2,
    )

    assert len(events) == 2


def test_summarize_failure_events_groups_failures():
    events = [
        {
            "timestamp": (
                "2026-09-29T10:02:00+00:00"
            ),
            "event_type": (
                "celery.task_failure"
            ),
            "component": "celery",
            "severity": "error",
        },
        {
            "timestamp": (
                "2026-09-29T10:01:00+00:00"
            ),
            "event_type": "http.5xx",
            "component": "api",
            "severity": "error",
        },
        {
            "timestamp": (
                "2026-09-29T10:00:00+00:00"
            ),
            "event_type": "http.5xx",
            "component": "api",
            "severity": "error",
        },
    ]

    result = summarize_failure_events(
        events
    )

    assert result[
        "recent_failure_count"
    ] == 3

    assert result["by_component"] == {
        "api": 2,
        "celery": 1,
    }

    assert result["by_event_type"] == {
        "celery.task_failure": 1,
        "http.5xx": 2,
    }

    assert result[
        "latest_failure_at"
    ] == (
        "2026-09-29T10:02:00+00:00"
    )


def test_record_failure_event_handles_redis_failure():
    class BrokenRedis:
        def lpush(self, *args, **kwargs):
            raise RuntimeError(
                "redis unavailable"
            )

    result = record_failure_event(
        redis_client=BrokenRedis(),
        event_type="application.error",
        component="api",
    )

    assert result is None


def test_event_payload_is_json_serializable():
    redis = FakeRedis()

    record_failure_event(
        redis_client=redis,
        event_type="celery.task_failure",
        component="celery",
        task_name="example.task",
        task_id="task-123",
    )

    json.loads(
        redis.items[0]
    )
