from __future__ import annotations

from app.core.observability.failure_dashboard_service import (
    get_failure_dashboard,
)


class FakeRedis:
    def __init__(self, events):
        self.events = events

    def lrange(self, key, start, end):
        return self.events[
            start : end + 1
        ]


def _event(
    event_id,
    component,
    event_type,
    severity="error",
):
    import json

    return json.dumps(
        {
            "event_id": event_id,
            "timestamp": (
                "2026-09-29T10:00:00+00:00"
            ),
            "event_type": event_type,
            "component": component,
            "severity": severity,
            "request_id": "request-123",
            "method": "GET",
            "route": "/api/v1/test",
            "status": 500,
            "error_type": "RuntimeError",
            "task_name": None,
            "task_id": None,
            "secret": "must-not-leak",
        }
    )


def test_failure_dashboard_returns_curated_failures(
    user,
):
    result = get_failure_dashboard(
        actor_id=user.id,
        redis_client=FakeRedis(
            [
                _event(
                    "1",
                    "api",
                    "http.5xx",
                ),
                _event(
                    "2",
                    "celery",
                    "celery.task_failure",
                ),
            ]
        ),
    )

    assert result["schema_version"] == "v1"
    assert result["scope"] == "platform"
    assert len(
        result["recent_failures"]
    ) == 2

    assert (
        result["summary"][
            "recent_failure_count"
        ]
        == 2
    )

    serialized = str(result)

    assert "must-not-leak" not in serialized


def test_failure_dashboard_rejects_non_admin(
    make_user,
):
    from app.core.enums.role_enums import Role
    from app.core.exceptions import ValidationError

    actor = make_user(
        role=Role.DOCTOR,
    )

    try:
        get_failure_dashboard(
            actor_id=actor.id,
            redis_client=FakeRedis([]),
        )
    except ValidationError as exc:
        assert "not available" in str(exc)
    else:
        raise AssertionError(
            "Expected ValidationError"
        )


def test_failure_dashboard_allows_super_admin(
    make_user,
):
    from app.core.enums.role_enums import Role

    actor = make_user(
        role=Role.SUPER_ADMIN,
    )

    result = get_failure_dashboard(
        actor_id=actor.id,
        redis_client=FakeRedis([]),
    )

    assert result["scope"] == "platform"


def test_failure_dashboard_respects_limit(
    user,
):
    events = [
        _event(
            str(index),
            "api",
            "http.5xx",
        )
        for index in range(5)
    ]

    result = get_failure_dashboard(
        actor_id=user.id,
        redis_client=FakeRedis(events),
        limit=2,
    )

    assert len(
        result["recent_failures"]
    ) == 2
