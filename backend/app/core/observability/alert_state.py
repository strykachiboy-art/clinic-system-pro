from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any


ALERT_STATE_PREFIX = (
    "observability:alert:state:v1:"
)

ALERT_ACTIVE_SET_KEY = (
    "observability:alert:active:v1"
)

_SEVERITY_RANK = {
    "info": 1,
    "warning": 2,
    "critical": 3,
}


def _utcnow() -> str:
    return datetime.now(
        timezone.utc
    ).isoformat()


def _fingerprint(
    alert: dict[str, Any],
) -> str:
    identity = {
        "code": alert.get("code"),
        "component": alert.get("component"),
        "resource": alert.get("resource"),
    }

    payload = json.dumps(
        identity,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")

    return hashlib.sha256(
        payload
    ).hexdigest()


def _state_key(
    fingerprint: str,
) -> str:
    return (
        f"{ALERT_STATE_PREFIX}"
        f"{fingerprint}"
    )


def _read_value(
    value: Any,
) -> str | None:
    if value is None:
        return None

    if isinstance(
        value,
        bytes,
    ):
        return value.decode("utf-8")

    return str(value)


def _load_state(
    redis,
    fingerprint: str,
) -> dict[str, Any] | None:
    raw = _read_value(
        redis.get(
            _state_key(
                fingerprint
            )
        )
    )

    if raw is None:
        return None

    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return None

    if not isinstance(
        value,
        dict,
    ):
        return None

    return value


def _save_state(
    redis,
    fingerprint: str,
    state: dict[str, Any],
) -> None:
    redis.set(
        _state_key(
            fingerprint
        ),
        json.dumps(
            state,
            sort_keys=True,
        ),
    )


def _severity_rank(
    severity: Any,
) -> int:
    return _SEVERITY_RANK.get(
        str(severity),
        0,
    )


def _build_active_state(
    alert: dict[str, Any],
    *,
    fingerprint: str,
    timestamp: str,
    occurrence_count: int,
) -> dict[str, Any]:
    return {
        "fingerprint": fingerprint,
        "code": alert.get("code"),
        "severity": alert.get("severity"),
        "component": alert.get("component"),
        "resource": alert.get("resource"),
        "message": alert.get("message"),
        "observed_value": alert.get(
            "observed_value"
        ),
        "threshold": alert.get(
            "threshold"
        ),
        "status": "active",
        "occurrence_count": occurrence_count,
        "first_seen_at": timestamp,
        "last_seen_at": timestamp,
    }


def record_operational_alerts(
    alerts: list[dict[str, Any]],
    *,
    redis_client,
    timestamp: str | None = None,
) -> dict[str, Any]:
    if not isinstance(
        alerts,
        list,
    ):
        raise TypeError(
            "alerts must be a list"
        )

    if redis_client is None:
        raise RuntimeError(
            "Redis client is required for alert state tracking"
        )

    timestamp = (
        timestamp
        or _utcnow()
    )

    current_fingerprints: set[str] = set()

    active = []
    new_alerts = []
    escalated_alerts = []
    ongoing_alerts = []

    for alert in alerts:
        if not isinstance(
            alert,
            dict,
        ):
            raise TypeError(
                "each alert must be a dictionary"
            )

        fingerprint = _fingerprint(
            alert
        )

        current_fingerprints.add(
            fingerprint
        )

        existing = _load_state(
            redis_client,
            fingerprint,
        )

        if existing is None:
            state = _build_active_state(
                alert,
                fingerprint=fingerprint,
                timestamp=timestamp,
                occurrence_count=1,
            )

            action = "new"

        else:
            old_severity = existing.get(
                "severity"
            )

            count = int(
                existing.get(
                    "occurrence_count",
                    0,
                )
            ) + 1

            state = dict(existing)

            state.update(
                {
                    "severity": alert.get(
                        "severity"
                    ),
                    "component": alert.get(
                        "component"
                    ),
                    "resource": alert.get(
                        "resource"
                    ),
                    "message": alert.get(
                        "message"
                    ),
                    "observed_value": alert.get(
                        "observed_value"
                    ),
                    "threshold": alert.get(
                        "threshold"
                    ),
                    "status": "active",
                    "occurrence_count": count,
                    "last_seen_at": timestamp,
                    "resolved_at": None,
                }
            )

            if (
                _severity_rank(
                    alert.get("severity")
                )
                > _severity_rank(
                    old_severity
                )
            ):
                action = "escalated"
            else:
                action = "ongoing"

        state = dict(state)
        state["notification_action"] = action

        if action == "new":
            new_alerts.append(state)
        elif action == "escalated":
            escalated_alerts.append(state)
        else:
            ongoing_alerts.append(state)

        _save_state(
            redis_client,
            fingerprint,
            state,
        )

        redis_client.sadd(
            ALERT_ACTIVE_SET_KEY,
            fingerprint,
        )

        active.append(
            state
        )

    raw_active = redis_client.smembers(
        ALERT_ACTIVE_SET_KEY
    )

    previous_fingerprints = {
        _read_value(value)
        for value in raw_active
    }

    resolved_alerts = []

    for fingerprint in (
        previous_fingerprints
        - current_fingerprints
    ):
        if fingerprint is None:
            continue

        state = _load_state(
            redis_client,
            fingerprint,
        )

        if state is None:
            redis_client.srem(
                ALERT_ACTIVE_SET_KEY,
                fingerprint,
            )
            continue

        if state.get("status") != "active":
            redis_client.srem(
                ALERT_ACTIVE_SET_KEY,
                fingerprint,
            )
            continue

        state = dict(state)
        state.update(
            {
                "status": "resolved",
                "resolved_at": timestamp,
                "last_seen_at": timestamp,
                "notification_action": "resolved",
            }
        )

        _save_state(
            redis_client,
            fingerprint,
            state,
        )

        redis_client.srem(
            ALERT_ACTIVE_SET_KEY,
            fingerprint,
        )

        resolved_alerts.append(
            state
        )

    return {
        "timestamp": timestamp,
        "active": active,
        "new": new_alerts,
        "escalated": escalated_alerts,
        "ongoing": ongoing_alerts,
        "resolved": resolved_alerts,
    }
