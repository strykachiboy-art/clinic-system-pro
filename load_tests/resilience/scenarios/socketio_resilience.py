from __future__ import annotations

from typing import Any

from load_tests.resilience.common.socketio import (
    connect_socket,
    disconnect_socket,
    emit_event,
    receive_events,
)


CHAT_NAMESPACE = "/chat"


def build_socket_auth(
    user: Any,
    auth_headers_for,
) -> dict[str, str]:
    authorization = auth_headers_for(
        user
    )["Authorization"]

    token = authorization.removeprefix(
        "Bearer "
    )

    return {
        "access_token": token,
    }


def connect_authenticated_socket(
    app: Any,
    user: Any,
    auth_headers_for,
    chat_socket_client_for,
) -> Any:
    auth = build_socket_auth(
        user,
        auth_headers_for,
    )

    return connect_socket(
        app,
        __import__("app.extensions", fromlist=["socketio"]).socketio,
        auth=auth,
        namespace=CHAT_NAMESPACE,
    )


def reconnect_authenticated_socket(
    app: Any,
    user: Any,
    auth_headers_for,
    chat_socket_client_for,
) -> Any:
    return chat_socket_client_for(
        user=user,
        namespace=CHAT_NAMESPACE,
    )


def get_event_names(
    client: Any,
) -> list[str]:
    return [
        event["name"]
        for event in receive_events(
            client,
            namespace=CHAT_NAMESPACE,
        )
    ]


def get_event_payload(
    client: Any,
    event_name: str,
) -> dict[str, Any] | None:
    for event in receive_events(
        client,
        namespace=CHAT_NAMESPACE,
    ):
        if event.get("name") != event_name:
            continue

        args = event.get("args") or []

        if not args:
            return None

        payload = args[0]

        if isinstance(
            payload,
            dict,
        ):
            return payload

        return None

    return None


def join_conversation(
    client: Any,
    conversation_id: int,
) -> None:
    emit_event(
        client,
        "conversation.join",
        {
            "conversation_id": conversation_id,
        },
        namespace=CHAT_NAMESPACE,
    )


def leave_conversation(
    client: Any,
    conversation_id: int,
) -> None:
    emit_event(
        client,
        "conversation.leave",
        {
            "conversation_id": conversation_id,
        },
        namespace=CHAT_NAMESPACE,
    )


def disconnect(
    client: Any,
) -> None:
    disconnect_socket(
        client,
        namespace=CHAT_NAMESPACE,
    )