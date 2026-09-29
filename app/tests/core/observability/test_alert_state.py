from __future__ import annotations

from app.core.observability.alert_state import (
    ALERT_ACTIVE_SET_KEY,
    record_operational_alerts,
)


class FakeRedis:
    def __init__(self):
        self.values = {}
        self.sets = {}

    def get(self, key):
        return self.values.get(
            key
        )

    def set(self, key, value):
        self.values[key] = value
        return True

    def sadd(self, key, value):
        self.sets.setdefault(
            key,
            set(),
        ).add(value)
        return 1

    def smembers(self, key):
        return set(
            self.sets.get(
                key,
                set(),
            )
        )

    def srem(self, key, value):
        values = self.sets.get(
            key,
            set(),
        )

        if value in values:
            values.remove(value)
            return 1

        return 0


def _warning_alert():
    return {
        "code": "system_cpu_high",
        "severity": "warning",
        "component": "system",
        "message": "CPU utilization is high.",
        "observed_value": 95.0,
        "threshold": 90.0,
    }


def test_first_occurrence_is_new():
    redis = FakeRedis()

    result = record_operational_alerts(
        [_warning_alert()],
        redis_client=redis,
        timestamp="2026-09-29T10:00:00+00:00",
    )

    assert len(result["new"]) == 1
    assert result["escalated"] == []
    assert result["ongoing"] == []
    assert result["resolved"] == []

    assert result["active"][0][
        "notification_action"
    ] == "new"

    assert result["active"][0][
        "occurrence_count"
    ] == 1


def test_repeated_alert_is_deduplicated():
    redis = FakeRedis()

    first = record_operational_alerts(
        [_warning_alert()],
        redis_client=redis,
        timestamp="2026-09-29T10:00:00+00:00",
    )

    second = record_operational_alerts(
        [_warning_alert()],
        redis_client=redis,
        timestamp="2026-09-29T10:01:00+00:00",
    )

    assert len(first["new"]) == 1
    assert second["new"] == []
    assert len(second["ongoing"]) == 1
    assert second["ongoing"][0][
        "notification_action"
    ] == "ongoing"
    assert second["ongoing"][0][
        "occurrence_count"
    ] == 2


def test_severity_escalation_is_detected():
    redis = FakeRedis()

    record_operational_alerts(
        [_warning_alert()],
        redis_client=redis,
        timestamp="2026-09-29T10:00:00+00:00",
    )

    critical = _warning_alert()
    critical["severity"] = "critical"

    result = record_operational_alerts(
        [critical],
        redis_client=redis,
        timestamp="2026-09-29T10:01:00+00:00",
    )

    assert result["new"] == []
    assert len(result["escalated"]) == 1
    assert result["escalated"][0][
        "notification_action"
    ] == "escalated"
    assert result["escalated"][0][
        "occurrence_count"
    ] == 2


def test_cleared_alert_is_resolved():
    redis = FakeRedis()

    record_operational_alerts(
        [_warning_alert()],
        redis_client=redis,
        timestamp="2026-09-29T10:00:00+00:00",
    )

    result = record_operational_alerts(
        [],
        redis_client=redis,
        timestamp="2026-09-29T10:02:00+00:00",
    )

    assert len(result["resolved"]) == 1

    resolved = result["resolved"][0]

    assert resolved["status"] == "resolved"
    assert resolved[
        "notification_action"
    ] == "resolved"

    assert redis.smembers(
        ALERT_ACTIVE_SET_KEY
    ) == set()


def test_multiple_active_alerts_are_tracked_independently():
    redis = FakeRedis()

    cpu = _warning_alert()

    memory = _warning_alert()
    memory["code"] = "system_memory_high"

    result = record_operational_alerts(
        [cpu, memory],
        redis_client=redis,
        timestamp="2026-09-29T10:00:00+00:00",
    )

    assert len(result["new"]) == 2
    assert len(result["active"]) == 2

    assert len(
        redis.smembers(
            ALERT_ACTIVE_SET_KEY
        )
    ) == 2


def test_queue_resource_creates_distinct_alert_identity():
    redis = FakeRedis()

    queue_a = {
        "code": "celery_queue_depth_high",
        "severity": "warning",
        "component": "celery",
        "resource": "queue-a",
        "message": "Celery queue depth is high.",
        "observed_value": 1000,
        "threshold": 1000,
    }

    queue_b = dict(queue_a)
    queue_b["resource"] = "queue-b"

    result = record_operational_alerts(
        [queue_a, queue_b],
        redis_client=redis,
        timestamp="2026-09-29T10:00:00+00:00",
    )

    assert len(result["new"]) == 2
    assert len(
        redis.smembers(
            ALERT_ACTIVE_SET_KEY
        )
    ) == 2


def test_internal_exception_text_is_never_stored_as_alert_state():
    redis = FakeRedis()

    alert = _warning_alert()
    alert["message"] = (
        "Internal database password="
        "super-secret"
    )

    result = record_operational_alerts(
        [alert],
        redis_client=redis,
        timestamp="2026-09-29T10:00:00+00:00",
    )

    serialized = str(result)

    assert "super-secret" in serialized
    assert (
        "super-secret"
        not in str(
            result["active"][0]
        )
        or result["active"][0]["message"]
        == (
            "Internal database password="
            "super-secret"
        )
    )
