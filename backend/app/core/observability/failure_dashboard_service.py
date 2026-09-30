from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app import extensions
from app.core.auth.user.models.user_model import User
from app.core.enums.role_enums import Role
from app.core.exceptions import (
    NotFoundError,
    ValidationError,
)
from app.core.observability.failure_events import (
    collect_failure_events,
    summarize_failure_events,
)
from app.extensions import db


FAILURE_DASHBOARD_ROLES = {
    Role.ADMIN,
    Role.SUPER_ADMIN,
}


def _utcnow() -> str:
    return datetime.now(
        timezone.utc
    ).isoformat()


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

    if actor.role not in FAILURE_DASHBOARD_ROLES:
        raise ValidationError(
            "Failure dashboard is not available "
            "to this user"
        )

    return actor


def _safe_event(
    event: dict[str, Any],
) -> dict[str, Any]:
    return {
        "event_id": event.get(
            "event_id"
        ),
        "timestamp": event.get(
            "timestamp"
        ),
        "event_type": event.get(
            "event_type"
        ),
        "component": event.get(
            "component"
        ),
        "severity": event.get(
            "severity"
        ),
        "request_id": event.get(
            "request_id"
        ),
        "trace_id": event.get(
            "trace_id"
        ),
        "method": event.get(
            "method"
        ),
        "route": event.get(
            "route"
        ),
        "status": event.get(
            "status"
        ),
        "error_type": event.get(
            "error_type"
        ),
        "task_name": event.get(
            "task_name"
        ),
        "task_id": event.get(
            "task_id"
        ),
    }


def get_failure_dashboard(
    *,
    actor_id: int,
    redis_client=None,
    limit: int = 50,
) -> dict[str, Any]:
    _get_authorized_user(
        actor_id
    )

    if redis_client is None:
        redis_client = (
            extensions.redis_client
        )

    events = collect_failure_events(
        redis_client=redis_client,
        limit=limit,
    )

    safe_events = [
        _safe_event(event)
        for event in events
        if isinstance(
            event,
            dict,
        )
    ]

    summary = summarize_failure_events(
        events
    )

    return {
        "schema_version": "v1",
        "scope": "platform",
        "timestamp": _utcnow(),
        "recent_failures": safe_events,
        "summary": summary,
        "state_store_available": (
            redis_client is not None
        ),
    }
