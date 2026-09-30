from __future__ import annotations

from flask_jwt_extended import create_access_token

from app.core.enums.chat_enums import ConversationType
from app.extensions import socketio
from app.modules.chat.realtime import chat_socket
from app.modules.chat.services.conversation_service import (
    create_conversation,
)

from load_tests.resilience.common.assertions import (
    assert_event_count,
    assert_event_present,
    assert_socket_connected,
    assert_socket_disconnected,
)
from load_tests.resilience.common.socketio import (
    connect_socket,
    receive_events,
)
from load_tests.resilience.scenarios.socketio_resilience import (
    build_socket_auth,
    disconnect,
    get_event_names,
    get_event_payload,
    join_conversation,
)


def _make_group_conversation(
    clinic,
    user,
    other_user,
):
    return create_conversation(
        clinic_id=clinic.id,
        created_by_id=user.id,
        conversation_type=ConversationType.GROUP,
        participant_user_ids=[
            other_user.id,
        ],
    )


def test_socket_connects_and_restores_authenticated_context(
    app,
    user,
    auth_headers_for,
):
    auth = build_socket_auth(
        user,
        auth_headers_for,
    )

    client = connect_socket(
        app,
        socketio,
        auth=auth,
        namespace="/chat",
    )

    assert_socket_connected(
        client,
        namespace="/chat",
    )

    events = receive_events(
        client,
        namespace="/chat",
    )

    assert_event_count(
        events,
        "chat.connected",
        1,
    )

    payload = assert_event_present(
        events,
        "chat.connected",
    )["args"][0]

    assert payload["user_id"] == user.id
    assert payload["clinic_id"] == user.clinic_id


def test_socket_disconnects_cleanly(
    app,
    user,
    auth_headers_for,
):
    auth = build_socket_auth(
        user,
        auth_headers_for,
    )

    client = connect_socket(
        app,
        socketio,
        auth=auth,
        namespace="/chat",
    )

    assert_socket_connected(
        client,
        namespace="/chat",
    )

    disconnect(
        client
    )

    assert_socket_disconnected(
        client,
        namespace="/chat",
    )


def test_socket_reconnects_with_valid_credentials(
    app,
    user,
    auth_headers_for,
):
    auth = build_socket_auth(
        user,
        auth_headers_for,
    )

    first_client = connect_socket(
        app,
        socketio,
        auth=auth,
        namespace="/chat",
    )

    assert_socket_connected(
        first_client,
        namespace="/chat",
    )

    disconnect(
        first_client
    )

    second_client = connect_socket(
        app,
        socketio,
        auth=auth,
        namespace="/chat",
    )

    assert_socket_connected(
        second_client,
        namespace="/chat",
    )

    events = receive_events(
        second_client,
        namespace="/chat",
    )

    assert_event_count(
        events,
        "chat.connected",
        1,
    )

    payload = assert_event_present(
        events,
        "chat.connected",
    )["args"][0]

    assert payload["user_id"] == user.id
    assert payload["clinic_id"] == user.clinic_id


def test_socket_rejects_reconnect_with_revoked_token(
    app,
    user,
    auth_headers_for,
    monkeypatch,
):
    auth = build_socket_auth(
        user,
        auth_headers_for,
    )

    first_client = connect_socket(
        app,
        socketio,
        auth=auth,
        namespace="/chat",
    )

    assert_socket_connected(
        first_client,
        namespace="/chat",
    )

    disconnect(
        first_client
    )

    monkeypatch.setattr(
        chat_socket,
        "is_token_revoked",
        lambda claims: True,
    )

    second_client = connect_socket(
        app,
        socketio,
        auth=auth,
        namespace="/chat",
    )

    assert_socket_disconnected(
        second_client,
        namespace="/chat",
    )


def test_socket_rejoins_authorized_conversation_after_reconnect(
    app,
    clinic,
    user,
    make_user,
    auth_headers_for,
):
    other_user = make_user(
        clinic=clinic,
    )

    conversation = _make_group_conversation(
        clinic,
        user,
        other_user,
    )

    auth = build_socket_auth(
        user,
        auth_headers_for,
    )

    first_client = connect_socket(
        app,
        socketio,
        auth=auth,
        namespace="/chat",
    )

    assert_socket_connected(
        first_client,
        namespace="/chat",
    )

    join_conversation(
        first_client,
        conversation.id,
    )

    first_events = receive_events(
        first_client,
        namespace="/chat",
    )

    assert_event_present(
        first_events,
        "conversation.joined",
    )

    disconnect(
        first_client
    )

    second_client = connect_socket(
        app,
        socketio,
        auth=auth,
        namespace="/chat",
    )

    assert_socket_connected(
        second_client,
        namespace="/chat",
    )

    join_conversation(
        second_client,
        conversation.id,
    )

    second_events = receive_events(
        second_client,
        namespace="/chat",
    )

    joined = assert_event_present(
        second_events,
        "conversation.joined",
    )

    payload = joined["args"][0]

    assert payload["conversation_id"] == conversation.id
    assert payload["user_id"] == user.id


def test_socket_does_not_restore_unauthorized_conversation_after_reconnect(
    app,
    make_clinic,
    make_user,
    auth_headers_for,
):
    clinic_a = make_clinic(
        name="Clinic A",
    )

    clinic_b = make_clinic(
        name="Clinic B",
    )

    user_a = make_user(
        clinic=clinic_a,
    )

    user_b = make_user(
        clinic=clinic_b,
    )

    conversation = create_conversation(
        clinic_id=clinic_b.id,
        created_by_id=user_b.id,
        conversation_type=ConversationType.GROUP,
        participant_user_ids=[],
    )

    auth = build_socket_auth(
        user_a,
        auth_headers_for,
    )

    client = connect_socket(
        app,
        socketio,
        auth=auth,
        namespace="/chat",
    )

    assert_socket_connected(
        client,
        namespace="/chat",
    )

    join_conversation(
        client,
        conversation.id,
    )

    events = receive_events(
        client,
        namespace="/chat",
    )

    error = assert_event_present(
        events,
        "chat.error",
    )

    payload = error["args"][0]

    assert payload["code"] == (
        "conversation_join_failed"
    )


def test_socket_rejects_invalid_reconnect_credentials(
    app,
):
    with app.test_request_context():
        token = create_access_token(
            identity="invalid-user",
            additional_claims={
                "role": "admin",
                "token_version": 1,
            },
        )

    client = connect_socket(
        app,
        socketio,
        auth={
            "access_token": token,
        },
        namespace="/chat",
    )

    assert_socket_disconnected(
        client,
        namespace="/chat",
    )


def test_socket_repeated_reconnects_remain_authenticated(
    app,
    user,
    auth_headers_for,
):
    auth = build_socket_auth(
        user,
        auth_headers_for,
    )

    for _ in range(3):
        client = connect_socket(
            app,
            socketio,
            auth=auth,
            namespace="/chat",
        )

        assert_socket_connected(
            client,
            namespace="/chat",
        )

        events = receive_events(
            client,
            namespace="/chat",
        )

        event_names = [
            event["name"]
            for event in events
        ]

        assert event_names.count(
            "chat.connected"
        ) == 1

        connected_events = [
            event
            for event in events
            if event.get("name")
            == "chat.connected"
        ]

        assert len(
            connected_events
        ) == 1

        args = (
            connected_events[0].get("args")
            or []
        )

        assert args

        payload = args[0]

        assert isinstance(
            payload,
            dict,
        )

        assert payload["user_id"] == user.id
        assert payload["clinic_id"] == user.clinic_id

        disconnect(
            client
        )

        assert_socket_disconnected(
            client,
            namespace="/chat",
        )