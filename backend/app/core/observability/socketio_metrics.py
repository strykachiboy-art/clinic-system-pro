from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, timezone
from typing import Any
from weakref import WeakSet

from app import extensions


SOCKETIO_METRICS_STATE_KEY = "_clinic_socketio_metrics"

SOCKETIO_AGGREGATE_KEY = (
    "observability:socketio:aggregate:v1"
)

SOCKETIO_NAMESPACE_PREFIX = (
    "observability:socketio:namespace:v1:"
)

SOCKETIO_EVENT_PREFIX = (
    "observability:socketio:event:v1:"
)

DEFAULT_NAMESPACE = "/chat"

_REGISTERED_SOCKETIO: WeakSet = WeakSet()


def _to_int(
    value: Any,
    default: int = 0,
) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _get_redis_client():
    return extensions.redis_client


def _increment_metric(
    key: str,
    field: str,
    amount: int = 1,
) -> None:
    redis = _get_redis_client()

    if redis is None:
        return

    try:
        redis.hincrby(
            key,
            field,
            amount,
        )
    except Exception:
        return


def _set_metric(
    key: str,
    field: str,
    value: Any,
) -> None:
    redis = _get_redis_client()

    if redis is None:
        return

    try:
        redis.hset(
            key,
            field,
            value,
        )
    except Exception:
        return


def _namespace_key(
    namespace: str,
) -> str:
    return (
        f"{SOCKETIO_NAMESPACE_PREFIX}"
        f"{namespace}"
    )


def _event_key(
    namespace: str,
    event_name: str,
) -> str:
    return (
        f"{SOCKETIO_EVENT_PREFIX}"
        f"{namespace}:"
        f"{event_name}"
    )


def record_socketio_connection(
    *,
    namespace: str = DEFAULT_NAMESPACE,
) -> None:
    _increment_metric(
        SOCKETIO_AGGREGATE_KEY,
        "connect_events",
    )

    _increment_metric(
        _namespace_key(namespace),
        "connect_events",
    )

    _set_metric(
        SOCKETIO_AGGREGATE_KEY,
        "last_event_at",
        _utcnow().isoformat(),
    )


def record_socketio_rejected_connection(
    *,
    namespace: str = DEFAULT_NAMESPACE,
) -> None:
    _increment_metric(
        SOCKETIO_AGGREGATE_KEY,
        "rejected_connections",
    )

    _increment_metric(
        _namespace_key(namespace),
        "rejected_connections",
    )


def record_socketio_disconnection(
    *,
    namespace: str = DEFAULT_NAMESPACE,
) -> None:
    _increment_metric(
        SOCKETIO_AGGREGATE_KEY,
        "disconnect_events",
    )

    _increment_metric(
        _namespace_key(namespace),
        "disconnect_events",
    )

    _set_metric(
        SOCKETIO_AGGREGATE_KEY,
        "last_event_at",
        _utcnow().isoformat(),
    )


def record_socketio_event(
    event_name: str,
    *,
    namespace: str = DEFAULT_NAMESPACE,
    direction: str = "received",
) -> None:
    if (
        not isinstance(event_name, str)
        or not event_name.strip()
    ):
        raise ValueError(
            "event_name must be a non-empty string"
        )

    if (
        not isinstance(namespace, str)
        or not namespace
    ):
        raise ValueError(
            "namespace must be a non-empty string"
        )

    if direction not in {
        "received",
        "emitted",
    }:
        raise ValueError(
            "direction must be 'received' or 'emitted'"
        )

    event_name = event_name.strip()

    aggregate_field = (
        "received_events"
        if direction == "received"
        else "emitted_events"
    )

    _increment_metric(
        SOCKETIO_AGGREGATE_KEY,
        aggregate_field,
    )

    _increment_metric(
        _namespace_key(namespace),
        aggregate_field,
    )

    _increment_metric(
        _event_key(
            namespace,
            event_name,
        ),
        "event_count",
    )

    _set_metric(
        _event_key(
            namespace,
            event_name,
        ),
        "last_event_at",
        _utcnow().isoformat(),
    )


def record_socketio_join(
    *,
    namespace: str = DEFAULT_NAMESPACE,
) -> None:
    _increment_metric(
        SOCKETIO_AGGREGATE_KEY,
        "room_join_events",
    )

    _increment_metric(
        _namespace_key(namespace),
        "room_join_events",
    )


def record_socketio_leave(
    *,
    namespace: str = DEFAULT_NAMESPACE,
) -> None:
    _increment_metric(
        SOCKETIO_AGGREGATE_KEY,
        "room_leave_events",
    )

    _increment_metric(
        _namespace_key(namespace),
        "room_leave_events",
    )


def record_socketio_error(
    *,
    namespace: str = DEFAULT_NAMESPACE,
) -> None:
    _increment_metric(
        SOCKETIO_AGGREGATE_KEY,
        "error_events",
    )

    _increment_metric(
        _namespace_key(namespace),
        "error_events",
    )


def _extract_manager_rooms(
    server,
    namespace: str,
) -> dict[Any, Any]:
    manager = getattr(
        server,
        "manager",
        None,
    )

    if manager is None:
        return {}

    rooms = getattr(
        manager,
        "rooms",
        None,
    )

    if not isinstance(rooms, dict):
        return {}

    namespace_rooms = rooms.get(
        namespace,
        {},
    )

    if not isinstance(
        namespace_rooms,
        dict,
    ):
        return {}

    return namespace_rooms


def _room_members(
    members: Any,
) -> set[str]:
    if members is None:
        return set()

    if isinstance(
        members,
        dict,
    ):
        return {
            str(member)
            for member in members.keys()
        }

    try:
        return {
            str(member)
            for member in members
        }
    except TypeError:
        return set()


def _snapshot_namespace_state(
    server,
    namespace: str,
) -> dict[str, Any]:
    rooms = _extract_manager_rooms(
        server,
        namespace,
    )

    all_sids: set[str] = set()
    room_member_counts: dict[str, int] = {}

    for room_name, members in rooms.items():
        normalized_members = _room_members(
            members
        )

        all_sids.update(
            normalized_members
        )

        if room_name is None:
            continue

        room_name_string = str(
            room_name
        )

        room_member_counts[
            room_name_string
        ] = len(normalized_members)

    connected_sids = set()

    for room_name, members in rooms.items():
        if room_name is None:
            continue

        room_name_string = str(
            room_name
        )

        if room_name_string in all_sids:
            connected_sids.add(
                room_name_string
            )

    named_rooms = {
        name: count
        for name, count in room_member_counts.items()
        if name not in connected_sids
    }

    return {
        "namespace": namespace,
        "active_connections": len(
            connected_sids
        ),
        "room_count": len(named_rooms),
        "rooms": named_rooms,
    }


def collect_socketio_metrics(
    *,
    socketio=None,
    client=None,
    namespaces: Iterable[str] | None = None,
) -> dict[str, Any]:
    if socketio is None:
        socketio = extensions.socketio

    if client is None:
        client = _get_redis_client()

    server = getattr(
        socketio,
        "server",
        None,
    )

    namespace_list = (
        list(namespaces)
        if namespaces is not None
        else [DEFAULT_NAMESPACE]
    )

    for namespace in namespace_list:
        if (
            not isinstance(namespace, str)
            or not namespace
        ):
            raise ValueError(
                "SocketIO namespaces must be "
                "non-empty strings"
            )

    namespace_metrics = {}

    for namespace in namespace_list:
        namespace_metrics[namespace] = (
            _snapshot_namespace_state(
                server,
                namespace,
            )
            if server is not None
            else {
                "namespace": namespace,
                "active_connections": 0,
                "room_count": 0,
                "rooms": {},
            }
        )

    active_connections = sum(
        metrics["active_connections"]
        for metrics in namespace_metrics.values()
    )

    room_count = sum(
        metrics["room_count"]
        for metrics in namespace_metrics.values()
    )

    aggregate_metrics: dict[str, Any] = {}

    if client is not None:
        try:
            values = client.hgetall(
                SOCKETIO_AGGREGATE_KEY
            )

            if isinstance(
                values,
                dict,
            ):
                aggregate_metrics = {
                    "connect_events": _to_int(
                        values.get(
                            "connect_events"
                        )
                    ),
                    "rejected_connections": _to_int(
                        values.get(
                            "rejected_connections"
                        )
                    ),
                    "disconnect_events": _to_int(
                        values.get(
                            "disconnect_events"
                        )
                    ),
                    "received_events": _to_int(
                        values.get(
                            "received_events"
                        )
                    ),
                    "emitted_events": _to_int(
                        values.get(
                            "emitted_events"
                        )
                    ),
                    "room_join_events": _to_int(
                        values.get(
                            "room_join_events"
                        )
                    ),
                    "room_leave_events": _to_int(
                        values.get(
                            "room_leave_events"
                        )
                    ),
                    "error_events": _to_int(
                        values.get(
                            "error_events"
                        )
                    ),
                    "last_event_at": values.get(
                        "last_event_at"
                    ),
                }
        except Exception:
            aggregate_metrics = {}

    redis_healthy = False

    if client is not None:
        try:
            redis_healthy = bool(
                client.ping()
            )
        except Exception:
            redis_healthy = False

    manager = (
        getattr(
            server,
            "manager",
            None,
        )
        if server is not None
        else None
    )

    manager_name = (
        manager.__class__.__name__
        if manager is not None
        else None
    )

    return {
        "timestamp": _utcnow().isoformat(),
        "healthy": (
            server is not None
        ),
        "server_available": (
            server is not None
        ),
        "redis_coordination_healthy": (
            redis_healthy
        ),
        "manager_type": manager_name,
        "active_connections": active_connections,
        "room_count": room_count,
        "namespaces": namespace_metrics,
        "aggregate_metrics": aggregate_metrics,
        "message_queue_enabled": (
            manager is not None
        ),
    }


def init_socketio_metrics(
    socketio,
) -> None:
    if socketio in _REGISTERED_SOCKETIO:
        return

    _REGISTERED_SOCKETIO.add(
        socketio
    )

    state = {
        "registered": True,
    }

    socketio._clinic_socketio_metrics_state = (
        state
    )