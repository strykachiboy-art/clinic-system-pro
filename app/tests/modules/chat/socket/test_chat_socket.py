from __future__ import annotations

import pytest
from flask_jwt_extended import create_access_token
from app.core.enums.chat_enums import ConversationType
from app.modules.chat.realtime import chat_socket
from app.modules.chat.services.conversation_service import (
    create_conversation,
)


# ============================================================================
# HELPERS
# ============================================================================


def _event_names(client, namespace="/chat") -> list[str]:
    return [
        event["name"]
        for event in client.get_received(namespace)
    ]


def _event_payload(
    client,
    event_name: str,
    namespace="/chat",
):
    for event in client.get_received(namespace):
        if event["name"] == event_name:
            args = event.get("args") or []

            if args:
                return args[0]

            return None

    return None


def _make_group_conversation(
    clinic,
    user,
    make_user,
):
    other_user = make_user(
        clinic=clinic,
    )

    conversation = create_conversation(
        clinic_id=clinic.id,
        created_by_id=user.id,
        conversation_type=ConversationType.GROUP,
        participant_user_ids=[
            other_user.id,
        ],
    )

    return conversation, other_user


# ============================================================================
# CONNECTION / AUTHENTICATION
# ============================================================================


def test_socket_rejects_missing_auth(
    chat_socket_client_for,
):
    client = chat_socket_client_for()

    assert client.is_connected("/chat") is False


def test_socket_rejects_empty_auth(
    chat_socket_client_for,
):
    client = chat_socket_client_for(
        auth={},
    )

    assert client.is_connected("/chat") is False


def test_socket_rejects_missing_access_token(
    chat_socket_client_for,
):
    client = chat_socket_client_for(
        auth={
            "something_else": "value",
        },
    )

    assert client.is_connected("/chat") is False


def test_socket_rejects_invalid_token(
    chat_socket_client_for,
):
    client = chat_socket_client_for(
        auth={
            "access_token": "invalid-token",
        },
    )

    assert client.is_connected("/chat") is False


def test_socket_rejects_malformed_identity(
    app,
    chat_socket_client_for,
):
    with app.test_request_context():
        token = create_access_token(
            identity="not-an-integer",
            additional_claims={
                "role": "admin",
            },
        )

    client = chat_socket_client_for(
        token=token,
    )

    assert client.is_connected("/chat") is False


def test_socket_rejects_revoked_token(
    app,
    chat_socket_client_for,
    user,
    monkeypatch,
):
    with app.test_request_context():
        token = create_access_token(
            identity=str(user.id),
            additional_claims={
                "role": (
                    user.role.value
                    if hasattr(user.role, "value")
                    else user.role
                ),
                "token_version": user.token_version,
            },
        )

    monkeypatch.setattr(
        chat_socket,
        "is_token_revoked",
        lambda claims: True,
    )

    client = chat_socket_client_for(
        token=token,
    )

    assert client.is_connected("/chat") is False


def test_socket_rejects_inactive_user(
    chat_socket_client_for,
    user,
):
    user.is_active = False

    client = chat_socket_client_for(
        user=user,
    )

    assert client.is_connected("/chat") is False


def test_socket_connects_authenticated_user(
    chat_socket_client_for,
    user,
):
    client = chat_socket_client_for(
        user=user,
    )

    assert client.is_connected("/chat") is True


def test_socket_connection_emits_connected_event(
    chat_socket_client_for,
    user,
):
    client = chat_socket_client_for(
        user=user,
    )

    payload = _event_payload(
        client,
        "chat.connected",
    )

    assert payload is not None
    assert payload["user_id"] == user.id
    assert payload["clinic_id"] == user.clinic_id


# ============================================================================
# CONVERSATION JOIN
# ============================================================================


def test_socket_joins_authorized_conversation(
    chat_socket_client_for,
    clinic,
    user,
    make_user,
):
    conversation, _ = _make_group_conversation(
        clinic,
        user,
        make_user,
    )

    client = chat_socket_client_for(
        user=user,
    )

    client.emit(
        "conversation.join",
        {
            "conversation_id": conversation.id,
        },
        namespace="/chat",
    )

    payload = _event_payload(
        client,
        "conversation.joined",
    )

    assert payload is not None
    assert payload["conversation_id"] == conversation.id
    assert payload["user_id"] == user.id


def test_socket_rejects_non_participant_conversation(
    chat_socket_client_for,
    clinic,
    user,
    make_user,
):
    conversation, other_user = _make_group_conversation(
        clinic,
        user,
        make_user,
    )

    client = chat_socket_client_for(
        user=other_user,
    )

    client.emit(
        "conversation.join",
        {
            "conversation_id": conversation.id,
        },
        namespace="/chat",
    )

    payload = _event_payload(
        client,
        "chat.error",
    )

    assert payload is not None
    assert payload["code"] == "conversation_join_failed"


def test_socket_rejects_cross_clinic_conversation(
    chat_socket_client_for,
    make_clinic,
    make_user,
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

    client = chat_socket_client_for(
        user=user_a,
    )

    client.emit(
        "conversation.join",
        {
            "conversation_id": conversation.id,
        },
        namespace="/chat",
    )

    payload = _event_payload(
        client,
        "chat.error",
    )

    assert payload is not None
    assert payload["code"] == "conversation_join_failed"


def test_socket_rejects_missing_conversation(
    chat_socket_client_for,
    user,
):
    client = chat_socket_client_for(
        user=user,
    )

    client.emit(
        "conversation.join",
        {
            "conversation_id": 999999,
        },
        namespace="/chat",
    )

    payload = _event_payload(
        client,
        "chat.error",
    )

    assert payload is not None
    assert payload["code"] == "conversation_join_failed"


@pytest.mark.parametrize(
    "payload",
    [
        None,
        [],
        "invalid",
        123,
        True,
    ],
)
def test_socket_rejects_non_object_join_payload(
    chat_socket_client_for,
    user,
    payload,
):
    client = chat_socket_client_for(
        user=user,
    )

    client.emit(
        "conversation.join",
        payload,
        namespace="/chat",
    )

    payload = _event_payload(
        client,
        "chat.error",
    )

    assert payload is not None
    assert payload["code"] == "conversation_join_failed"


@pytest.mark.parametrize(
    "conversation_id",
    [
        None,
        0,
        -1,
        True,
        "not-an-integer",
    ],
)
def test_socket_rejects_invalid_conversation_id(
    chat_socket_client_for,
    user,
    conversation_id,
):
    client = chat_socket_client_for(
        user=user,
    )

    client.emit(
        "conversation.join",
        {
            "conversation_id": conversation_id,
        },
        namespace="/chat",
    )

    payload = _event_payload(
        client,
        "chat.error",
    )

    assert payload is not None
    assert payload["code"] == "conversation_join_failed"


# ============================================================================
# CONVERSATION LEAVE
# ============================================================================


def test_socket_leaves_authorized_conversation(
    chat_socket_client_for,
    clinic,
    user,
    make_user,
):
    conversation, _ = _make_group_conversation(
        clinic,
        user,
        make_user,
    )

    client = chat_socket_client_for(
        user=user,
    )

    client.emit(
        "conversation.join",
        {
            "conversation_id": conversation.id,
        },
        namespace="/chat",
    )

    client.get_received("/chat")

    client.emit(
        "conversation.leave",
        {
            "conversation_id": conversation.id,
        },
        namespace="/chat",
    )

    payload = _event_payload(
        client,
        "conversation.left",
    )

    assert payload is not None
    assert payload["conversation_id"] == conversation.id
    assert payload["user_id"] == user.id


def test_socket_rejects_leave_from_unauthorized_conversation(
    chat_socket_client_for,
    clinic,
    user,
    make_user,
):
    conversation, other_user = _make_group_conversation(
        clinic,
        user,
        make_user,
    )

    client = chat_socket_client_for(
        user=other_user,
    )

    client.emit(
        "conversation.leave",
        {
            "conversation_id": conversation.id,
        },
        namespace="/chat",
    )

    payload = _event_payload(
        client,
        "chat.error",
    )

    assert payload is not None
    assert payload["code"] == "conversation_leave_failed"


def test_socket_rejects_cross_clinic_leave(
    chat_socket_client_for,
    make_clinic,
    make_user,
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

    client = chat_socket_client_for(
        user=user_a,
    )

    client.emit(
        "conversation.leave",
        {
            "conversation_id": conversation.id,
        },
        namespace="/chat",
    )

    payload = _event_payload(
        client,
        "chat.error",
    )

    assert payload is not None
    assert payload["code"] == "conversation_leave_failed"


@pytest.mark.parametrize(
    "payload",
    [
        None,
        [],
        "invalid",
        123,
        True,
    ],
)
def test_socket_rejects_non_object_leave_payload(
    chat_socket_client_for,
    user,
    payload,
):
    client = chat_socket_client_for(
        user=user,
    )

    client.emit(
        "conversation.leave",
        payload,
        namespace="/chat",
    )

    error_payload = _event_payload(
        client,
        "chat.error",
    )

    assert error_payload is not None
    assert error_payload["code"] == "conversation_leave_failed"


@pytest.mark.parametrize(
    "conversation_id",
    [
        None,
        0,
        -1,
        True,
        "not-an-integer",
    ],
)
def test_socket_rejects_invalid_leave_conversation_id(
    chat_socket_client_for,
    user,
    conversation_id,
):
    client = chat_socket_client_for(
        user=user,
    )

    client.emit(
        "conversation.leave",
        {
            "conversation_id": conversation_id,
        },
        namespace="/chat",
    )

    payload = _event_payload(
        client,
        "chat.error",
    )

    assert payload is not None
    assert payload["code"] == "conversation_leave_failed"


# ============================================================================
# DISCONNECT
# ============================================================================


def test_socket_disconnects_cleanly(
    chat_socket_client_for,
    user,
):
    client = chat_socket_client_for(
        user=user,
    )

    assert client.is_connected("/chat") is True

    client.disconnect(
        namespace="/chat",
    )

    assert client.is_connected("/chat") is False