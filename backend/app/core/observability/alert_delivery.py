from __future__ import annotations

from typing import Any, Protocol


DELIVERABLE_ACTIONS = frozenset(
    {
        "new",
        "escalated",
        "resolved",
    }
)

_ACTION_ORDER = {
    "new": 1,
    "escalated": 2,
    "resolved": 3,
}


class AlertDeliverySink(Protocol):
    def deliver(
        self,
        events: list[dict[str, Any]],
    ) -> None:
        ...


def _validate_state_bucket(
    state: dict[str, Any],
    key: str,
) -> list[dict[str, Any]]:
    value = state.get(key, [])

    if not isinstance(value, list):
        raise TypeError(
            f"alert state '{key}' must be a list"
        )

    for event in value:
        if not isinstance(
            event,
            dict,
        ):
            raise TypeError(
                f"alert state '{key}' entries must be dictionaries"
            )

    return value


def _build_delivery_event(
    alert: dict[str, Any],
    *,
    action: str,
) -> dict[str, Any]:
    if action not in DELIVERABLE_ACTIONS:
        raise ValueError(
            f"unsupported alert delivery action: {action}"
        )

    fingerprint = alert.get("fingerprint")

    if not fingerprint:
        raise ValueError(
            "alert delivery event requires a fingerprint"
        )

    timestamp = (
        alert.get("resolved_at")
        if action == "resolved"
        else alert.get("last_seen_at")
    )

    if not timestamp:
        raise ValueError(
            "alert delivery event requires a timestamp"
        )

    return {
        "event_id": (
            f"{fingerprint}:"
            f"{action}:"
            f"{timestamp}"
        ),
        "event_type": action,
        "timestamp": timestamp,
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
        "occurrence_count": alert.get(
            "occurrence_count"
        ),
    }


def build_alert_delivery_events(
    alert_state: dict[str, Any],
) -> list[dict[str, Any]]:
    if not isinstance(
        alert_state,
        dict,
    ):
        raise TypeError(
            "alert_state must be a dictionary"
        )

    events: list[dict[str, Any]] = []

    for action in (
        "new",
        "escalated",
        "resolved",
    ):
        alerts = _validate_state_bucket(
            alert_state,
            action,
        )

        for alert in alerts:
            events.append(
                _build_delivery_event(
                    alert,
                    action=action,
                )
            )

    events.sort(
        key=lambda event: (
            event["timestamp"],
            _ACTION_ORDER[
                event["event_type"]
            ],
            event["fingerprint"],
        )
    )

    return events


def deliver_alert_events(
    events: list[dict[str, Any]],
    *,
    sink: AlertDeliverySink,
) -> int:
    if not isinstance(
        events,
        list,
    ):
        raise TypeError(
            "events must be a list"
        )

    if sink is None:
        raise RuntimeError(
            "alert delivery sink is required"
        )

    deliver = getattr(
        sink,
        "deliver",
        None,
    )

    if not callable(deliver):
        raise TypeError(
            "alert delivery sink must implement deliver(events)"
        )

    if not events:
        return 0

    deliver(events)

    return len(events)
