from __future__ import annotations

import pytest

from app.core.observability.alert_delivery import (
    build_alert_delivery_events,
    deliver_alert_events,
)


def _state():
    return {
        "timestamp": "2026-09-29T10:00:00+00:00",
        "active": [],
        "new": [
            {
                "fingerprint": "fingerprint-new",
                "code": "system_cpu_high",
                "severity": "warning",
                "component": "system",
                "message": "System CPU utilization is high.",
                "observed_value": 95.0,
                "threshold": 90.0,
                "occurrence_count": 1,
                "last_seen_at": "2026-09-29T10:00:00+00:00",
            }
        ],
        "escalated": [
            {
                "fingerprint": "fingerprint-escalated",
                "code": "redis_unhealthy",
                "severity": "critical",
                "component": "redis",
                "message": "Redis is unavailable or unhealthy.",
                "observed_value": None,
                "threshold": None,
                "occurrence_count": 3,
                "last_seen_at": "2026-09-29T10:01:00+00:00",
            }
        ],
        "ongoing": [
            {
                "fingerprint": "fingerprint-ongoing",
                "code": "system_memory_high",
                "severity": "warning",
                "component": "system",
                "message": "System memory utilization is high.",
                "observed_value": 95.0,
                "threshold": 90.0,
                "occurrence_count": 4,
                "last_seen_at": "2026-09-29T10:02:00+00:00",
            }
        ],
        "resolved": [
            {
                "fingerprint": "fingerprint-resolved",
                "code": "celery_workers_unavailable",
                "severity": "critical",
                "component": "celery",
                "message": "No healthy Celery workers are available.",
                "observed_value": None,
                "threshold": None,
                "occurrence_count": 2,
                "last_seen_at": "2026-09-29T10:03:00+00:00",
                "resolved_at": "2026-09-29T10:04:00+00:00",
            }
        ],
    }


def test_build_delivery_events_excludes_ongoing_alerts():
    events = build_alert_delivery_events(
        _state()
    )

    assert [
        event["event_type"]
        for event in events
    ] == [
        "new",
        "escalated",
        "resolved",
    ]


def test_delivery_event_contains_operational_fields_only():
    events = build_alert_delivery_events(
        _state()
    )

    event = events[0]

    assert event == {
        "event_id": (
            "fingerprint-new:"
            "new:"
            "2026-09-29T10:00:00+00:00"
        ),
        "event_type": "new",
        "timestamp": "2026-09-29T10:00:00+00:00",
        "fingerprint": "fingerprint-new",
        "code": "system_cpu_high",
        "severity": "warning",
        "component": "system",
        "resource": None,
        "message": "System CPU utilization is high.",
        "observed_value": 95.0,
        "threshold": 90.0,
        "occurrence_count": 1,
    }


def test_resolved_event_uses_resolved_timestamp():
    events = build_alert_delivery_events(
        _state()
    )

    resolved = events[-1]

    assert resolved["event_type"] == "resolved"
    assert resolved["timestamp"] == (
        "2026-09-29T10:04:00+00:00"
    )


def test_delivery_events_are_deterministically_ordered():
    state = _state()

    state["new"].append(
        {
            "fingerprint": "fingerprint-earlier",
            "code": "system_cpu_high",
            "severity": "warning",
            "component": "system",
            "message": "System CPU utilization is high.",
            "observed_value": 91.0,
            "threshold": 90.0,
            "occurrence_count": 1,
            "last_seen_at": "2026-09-29T09:59:00+00:00",
        }
    )

    events = build_alert_delivery_events(
        state
    )

    assert [
        event["fingerprint"]
        for event in events
    ] == [
        "fingerprint-earlier",
        "fingerprint-new",
        "fingerprint-escalated",
        "fingerprint-resolved",
    ]


def test_invalid_alert_state_bucket_is_rejected():
    state = _state()
    state["new"] = "invalid"

    with pytest.raises(TypeError):
        build_alert_delivery_events(state)


class FakeSink:
    def __init__(self):
        self.delivered = []

    def deliver(self, events):
        self.delivered.append(events)


def test_delivery_sink_receives_only_deliverable_events():
    events = build_alert_delivery_events(
        _state()
    )

    sink = FakeSink()

    count = deliver_alert_events(
        events,
        sink=sink,
    )

    assert count == 3
    assert len(sink.delivered) == 1
    assert sink.delivered[0] == events


def test_empty_delivery_does_not_call_sink():
    sink = FakeSink()

    count = deliver_alert_events(
        [],
        sink=sink,
    )

    assert count == 0
    assert sink.delivered == []


def test_missing_delivery_sink_is_rejected():
    with pytest.raises(RuntimeError):
        deliver_alert_events(
            [],
            sink=None,
        )
