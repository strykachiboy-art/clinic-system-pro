from __future__ import annotations

from unittest.mock import Mock

import pytest

from app.core.observability import (
    socketio_metrics,
)


def _socketio_mock():
    socketio = Mock()

    manager = Mock()

    manager.rooms = {}

    server = Mock()

    server.manager = manager

    socketio.server = server

    return socketio


def test_init_socketio_metrics_registers_state():
    socketio = _socketio_mock()

    socketio_metrics.init_socketio_metrics(
        socketio
    )

    assert (
        socketio._clinic_socketio_metrics_state[
            "registered"
        ]
        is True
    )

    assert (
        socketio
        in socketio_metrics._REGISTERED_SOCKETIO
    )


def test_record_socketio_connection():
    redis = Mock()

    original = (
        socketio_metrics._get_redis_client
    )

    socketio_metrics._get_redis_client = (
        lambda: redis
    )

    try:
        socketio_metrics.record_socketio_connection(
            namespace="/chat"
        )
    finally:
        socketio_metrics._get_redis_client = (
            original
        )

    assert redis.hincrby.call_count == 2
    assert redis.hset.call_count == 1


def test_record_rejected_connection():
    redis = Mock()

    original = (
        socketio_metrics._get_redis_client
    )

    socketio_metrics._get_redis_client = (
        lambda: redis
    )

    try:
        socketio_metrics.record_socketio_rejected_connection(
            namespace="/chat"
        )
    finally:
        socketio_metrics._get_redis_client = (
            original
        )

    assert redis.hincrby.call_count == 2


def test_record_disconnect():
    redis = Mock()

    original = (
        socketio_metrics._get_redis_client
    )

    socketio_metrics._get_redis_client = (
        lambda: redis
    )

    try:
        socketio_metrics.record_socketio_disconnection(
            namespace="/chat"
        )
    finally:
        socketio_metrics._get_redis_client = (
            original
        )

    assert redis.hincrby.call_count == 2
    assert redis.hset.call_count == 1


def test_record_event():
    redis = Mock()

    original = (
        socketio_metrics._get_redis_client
    )

    socketio_metrics._get_redis_client = (
        lambda: redis
    )

    try:
        socketio_metrics.record_socketio_event(
            "conversation.join",
            namespace="/chat",
            direction="received",
        )
    finally:
        socketio_metrics._get_redis_client = (
            original
        )

    assert redis.hincrby.call_count == 3
    assert redis.hset.call_count == 1


def test_record_event_rejects_invalid_direction():
    with pytest.raises(ValueError):
        socketio_metrics.record_socketio_event(
            "conversation.join",
            direction="invalid",
        )


def test_record_event_rejects_empty_event():
    with pytest.raises(ValueError):
        socketio_metrics.record_socketio_event(
            "",
        )


def test_record_join_leave_and_error():
    redis = Mock()

    original = (
        socketio_metrics._get_redis_client
    )

    socketio_metrics._get_redis_client = (
        lambda: redis
    )

    try:
        socketio_metrics.record_socketio_join(
            namespace="/chat"
        )

        socketio_metrics.record_socketio_leave(
            namespace="/chat"
        )

        socketio_metrics.record_socketio_error(
            namespace="/chat"
        )
    finally:
        socketio_metrics._get_redis_client = (
            original
        )

    assert redis.hincrby.call_count == 6


def test_collect_socketio_metrics_counts_connections_and_rooms():
    socketio = _socketio_mock()

    socketio.server.manager.rooms = {
        "/chat": {
            "sid-1": {
                "sid-1": True,
            },
            "sid-2": {
                "sid-2": True,
            },
            "chat:conversation:1:10": {
                "sid-1": True,
                "sid-2": True,
            },
        }
    }

    redis = Mock()
    redis.ping.return_value = True
    redis.hgetall.return_value = {
        "connect_events": "5",
        "rejected_connections": "1",
        "disconnect_events": "2",
        "received_events": "20",
        "emitted_events": "25",
        "room_join_events": "8",
        "room_leave_events": "4",
        "error_events": "2",
        "last_event_at": (
            "2026-09-21T10:00:00+00:00"
        ),
    }

    result = (
        socketio_metrics.collect_socketio_metrics(
            socketio=socketio,
            client=redis,
            namespaces=["/chat"],
        )
    )

    assert result["healthy"] is True
    assert result["server_available"] is True
    assert (
        result["redis_coordination_healthy"]
        is True
    )

    assert result["active_connections"] == 2
    assert result["room_count"] == 1

    assert (
        result["namespaces"]["/chat"][
            "active_connections"
        ]
        == 2
    )

    assert (
        result["namespaces"]["/chat"][
            "rooms"
        ][
            "chat:conversation:1:10"
        ]
        == 2
    )

    assert (
        result["aggregate_metrics"][
            "received_events"
        ]
        == 20
    )


def test_collect_socketio_metrics_supports_multiple_namespaces():
    socketio = _socketio_mock()

    socketio.server.manager.rooms = {
        "/chat": {
            "sid-1": {
                "sid-1": True,
            },
        },
        "/notifications": {
            "sid-2": {
                "sid-2": True,
            },
        },
    }

    redis = Mock()

    redis.ping.return_value = True
    redis.hgetall.return_value = {}

    result = (
        socketio_metrics.collect_socketio_metrics(
            socketio=socketio,
            client=redis,
            namespaces=[
                "/chat",
                "/notifications",
            ],
        )
    )

    assert (
        result["active_connections"]
        == 2
    )

    assert (
        result["namespaces"]["/chat"][
            "active_connections"
        ]
        == 1
    )

    assert (
        result["namespaces"]["/notifications"][
            "active_connections"
        ]
        == 1
    )


def test_collect_socketio_metrics_detects_redis_coordination_failure():
    socketio = _socketio_mock()

    redis = Mock()
    redis.ping.side_effect = RuntimeError(
        "Redis unavailable"
    )
    redis.hgetall.return_value = {}

    result = (
        socketio_metrics.collect_socketio_metrics(
            socketio=socketio,
            client=redis,
        )
    )

    assert (
        result["redis_coordination_healthy"]
        is False
    )
    assert result["server_available"] is True
    assert result["healthy"] is True


def test_collect_socketio_metrics_rejects_invalid_namespace():
    socketio = _socketio_mock()
    redis = Mock()

    with pytest.raises(ValueError):
        socketio_metrics.collect_socketio_metrics(
            socketio=socketio,
            client=redis,
            namespaces=[""],
        )