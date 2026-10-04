from __future__ import annotations

from time import monotonic, sleep
from typing import Any


DEFAULT_NAMESPACE = "/chat"


def connect_socket(
    app: Any,
    socketio: Any,
    *,
    auth: dict[str, Any] | None = None,
    namespace: str = DEFAULT_NAMESPACE,
) -> Any:
    return socketio.test_client(
        app,
        namespace=namespace,
        auth=auth,
    )


def is_connected(
    client: Any,
    namespace: str = DEFAULT_NAMESPACE,
) -> bool:
    return bool(
        client.is_connected(namespace)
    )


def emit_event(
    client: Any,
    event: str,
    payload: Any = None,
    *,
    namespace: str = DEFAULT_NAMESPACE,
) -> None:
    client.emit(
        event,
        payload,
        namespace=namespace,
    )


def receive_events(
    client: Any,
    *,
    namespace: str = DEFAULT_NAMESPACE,
) -> list[dict[str, Any]]:
    return list(
        client.get_received(namespace)
    )


def wait_for_event(
    client: Any,
    event_name: str,
    *,
    timeout_seconds: float = 2.0,
    poll_interval_seconds: float = 0.01,
    namespace: str = DEFAULT_NAMESPACE,
) -> dict[str, Any] | None:
    if timeout_seconds <= 0:
        raise ValueError(
            "timeout_seconds must be greater than zero"
        )

    if poll_interval_seconds <= 0:
        raise ValueError(
            "poll_interval_seconds must be greater than zero"
        )

    deadline = (
        monotonic()
        + timeout_seconds
    )

    while monotonic() < deadline:
        events = receive_events(
            client,
            namespace=namespace,
        )

        for event in events:
            if event.get("name") == event_name:
                return event

        sleep(
            poll_interval_seconds
        )

    return None


def disconnect_socket(
    client: Any,
    *,
    namespace: str = DEFAULT_NAMESPACE,
) -> None:
    client.disconnect(
        namespace=namespace
    )


def reconnect_socket(
    app: Any,
    socketio: Any,
    *,
    auth: dict[str, Any] | None = None,
    namespace: str = DEFAULT_NAMESPACE,
) -> Any:
    return connect_socket(
        app,
        socketio,
        auth=auth,
        namespace=namespace,
    )


def clear_received_events(
    client: Any,
    *,
    namespace: str = DEFAULT_NAMESPACE,
) -> list[dict[str, Any]]:
    return receive_events(
        client,
        namespace=namespace,
    )