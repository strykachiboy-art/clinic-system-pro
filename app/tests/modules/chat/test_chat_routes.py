from __future__ import annotations

from app.extensions import db
from app.core.enums.chat_enums import (
    ConversationStatus,
    ConversationType,
    MessageStatus,
    ParticipantRole,
    ParticipantStatus,
)
from app.modules.chat.models.conversation_participant_model import (
    ConversationParticipant,
)


CHAT_BASE = "/api/v1/chat"


def _json(response):
    payload = response.get_json()

    assert isinstance(payload, dict)

    return payload


def _auth_headers(
    app,
    user,
):
    from flask_jwt_extended import create_access_token

    with app.app_context():
        token = create_access_token(
            identity=str(user.id),
            additional_claims={
                "role": user.role.value,
                "token_version": user.token_version,
            },
        )

    return {
        "Authorization": f"Bearer {token}",
    }


def _accepted_participant(
    make_conversation_participant,
    clinic,
    conversation,
    user,
    role=ParticipantRole.MEMBER,
):
    return make_conversation_participant(
        clinic=clinic,
        conversation=conversation,
        user=user,
        role=role,
        status=ParticipantStatus.ACCEPTED,
    )


def _make_accessible_conversation(
    clinic,
    user,
    make_user,
    make_conversation,
    make_conversation_participant,
):
    other_user = make_user(
        clinic=clinic,
    )

    conversation = make_conversation(
        clinic=clinic,
        created_by=user,
        conversation_type=ConversationType.GROUP,
        status=ConversationStatus.ACTIVE,
    )

    _accepted_participant(
        make_conversation_participant,
        clinic,
        conversation,
        user,
        role=ParticipantRole.ADMIN,
    )

    _accepted_participant(
        make_conversation_participant,
        clinic,
        conversation,
        other_user,
    )

    return conversation, other_user


def test_conversation_routes_require_authentication(
    client,
):
    response = client.get(
        f"{CHAT_BASE}/conversations"
    )

    assert response.status_code == 401


def test_create_direct_conversation(
    client,
    app,
    clinic,
    user,
    make_user,
    make_clinic_settings,
    no_audit,
):
    other_user = make_user(
        clinic=clinic,
    )

    make_clinic_settings(
        clinic=clinic,
        feature_flags={
            "chat_enabled": True,
        },
    )

    response = client.post(
        f"{CHAT_BASE}/conversations",
        json={
            "conversation_type": ConversationType.DIRECT.value,
            "participant_user_ids": [
                other_user.id,
            ],
        },
        headers=_auth_headers(
            app,
            user,
        ),
    )

    assert response.status_code == 201

    payload = _json(response)

    assert payload["success"] is True
    assert payload["data"]["conversation_type"] == (
        ConversationType.DIRECT.value
    )
    assert payload["data"]["clinic_id"] == clinic.id
    assert payload["data"]["created_by_id"] == user.id


def test_create_conversation_rejects_duplicate_participants(
    client,
    app,
    clinic,
    user,
    make_user,
):
    other_user = make_user(
        clinic=clinic,
    )

    response = client.post(
        f"{CHAT_BASE}/conversations",
        json={
            "conversation_type": ConversationType.GROUP.value,
            "participant_user_ids": [
                other_user.id,
                other_user.id,
            ],
        },
        headers=_auth_headers(
            app,
            user,
        ),
    )

    assert response.status_code == 422

    payload = _json(response)

    assert payload["success"] is False
    assert payload["error"] == "Invalid request payload"
    assert "details" in payload


def test_create_conversation_rejects_when_chat_disabled(
    client,
    app,
    clinic,
    user,
    make_user,
    make_clinic_settings,
):
    other_user = make_user(
        clinic=clinic,
    )

    make_clinic_settings(
        clinic=clinic,
        feature_flags={
            "chat_enabled": False,
        },
    )

    response = client.post(
        f"{CHAT_BASE}/conversations",
        json={
            "conversation_type": ConversationType.DIRECT.value,
            "participant_user_ids": [
                other_user.id,
            ],
        },
        headers=_auth_headers(
            app,
            user,
        ),
    )

    assert response.status_code == 422

    payload = _json(response)

    assert payload["success"] is False


def test_list_conversations(
    client,
    app,
    clinic,
    user,
    make_user,
    make_conversation,
    make_conversation_participant,
):
    conversation, _ = _make_accessible_conversation(
        clinic,
        user,
        make_user,
        make_conversation,
        make_conversation_participant,
    )

    response = client.get(
        f"{CHAT_BASE}/conversations",
        headers=_auth_headers(
            app,
            user,
        ),
    )

    assert response.status_code == 200

    payload = _json(response)

    assert payload["success"] is True
    assert payload["total"] >= 1
    assert len(payload["data"]) >= 1
    assert payload["page"] == 1
    assert payload["per_page"] == 50
    assert payload["data"][0]["id"] == conversation.id


def test_list_conversations_rejects_unknown_query_parameter(
    client,
    app,
    user,
):
    response = client.get(
        f"{CHAT_BASE}/conversations?unknown=value",
        headers=_auth_headers(
            app,
            user,
        ),
    )

    assert response.status_code == 422

    payload = _json(response)

    assert payload["success"] is False


def test_get_conversation(
    client,
    app,
    clinic,
    user,
    make_user,
    make_conversation,
    make_conversation_participant,
):
    conversation, _ = _make_accessible_conversation(
        clinic,
        user,
        make_user,
        make_conversation,
        make_conversation_participant,
    )

    response = client.get(
        f"{CHAT_BASE}/conversations/{conversation.id}",
        headers=_auth_headers(
            app,
            user,
        ),
    )

    assert response.status_code == 200

    payload = _json(response)

    assert payload["success"] is True
    assert payload["data"]["id"] == conversation.id
    assert payload["data"]["clinic_id"] == clinic.id


def test_get_conversation_blocks_cross_clinic_access(
    client,
    app,
    clinic,
    make_clinic,
    user,
    make_user,
    make_conversation,
    make_conversation_participant,
):
    other_clinic = make_clinic(
        name="Other Clinic",
    )

    other_user = make_user(
        clinic=other_clinic,
    )

    other_conversation = make_conversation(
        clinic=other_clinic,
        created_by=other_user,
    )

    _accepted_participant(
        make_conversation_participant,
        other_clinic,
        other_conversation,
        other_user,
        role=ParticipantRole.ADMIN,
    )

    response = client.get(
        f"{CHAT_BASE}/conversations/{other_conversation.id}",
        headers=_auth_headers(
            app,
            user,
        ),
    )

    assert response.status_code == 404


def test_update_conversation(
    client,
    app,
    clinic,
    user,
    make_user,
    make_conversation,
    make_conversation_participant,
    no_audit,
):
    conversation, _ = _make_accessible_conversation(
        clinic,
        user,
        make_user,
        make_conversation,
        make_conversation_participant,
    )

    response = client.patch(
        f"{CHAT_BASE}/conversations/{conversation.id}",
        json={
            "title": "Updated Clinical Team",
            "description": "Updated description",
        },
        headers=_auth_headers(
            app,
            user,
        ),
    )

    assert response.status_code == 200

    payload = _json(response)

    assert payload["success"] is True
    assert payload["data"]["title"] == "Updated Clinical Team"
    assert payload["data"]["description"] == (
        "Updated description"
    )


def test_update_conversation_rejects_unsupported_type_change(
    client,
    app,
    clinic,
    user,
    make_user,
    make_conversation,
    make_conversation_participant,
):
    conversation, _ = _make_accessible_conversation(
        clinic,
        user,
        make_user,
        make_conversation,
        make_conversation_participant,
    )

    response = client.patch(
        f"{CHAT_BASE}/conversations/{conversation.id}",
        json={
            "conversation_type": ConversationType.DEPARTMENT.value,
        },
        headers=_auth_headers(
            app,
            user,
        ),
    )

    assert response.status_code == 422

    payload = _json(response)

    assert payload["success"] is False


def test_update_conversation_status(
    client,
    app,
    clinic,
    user,
    make_user,
    make_conversation,
    make_conversation_participant,
    no_audit,
):
    conversation, _ = _make_accessible_conversation(
        clinic,
        user,
        make_user,
        make_conversation,
        make_conversation_participant,
    )

    response = client.post(
        f"{CHAT_BASE}/conversations/{conversation.id}/status",
        json={
            "status": ConversationStatus.ARCHIVED.value,
        },
        headers=_auth_headers(
            app,
            user,
        ),
    )

    assert response.status_code == 200

    payload = _json(response)

    assert payload["success"] is True
    assert payload["data"]["status"] == (
        ConversationStatus.ARCHIVED.value
    )


def test_add_participant(
    client,
    app,
    clinic,
    user,
    make_user,
    make_conversation,
    make_conversation_participant,
    no_audit,
):
    conversation, _ = _make_accessible_conversation(
        clinic,
        user,
        make_user,
        make_conversation,
        make_conversation_participant,
    )

    new_user = make_user(
        clinic=clinic,
    )

    response = client.post(
        f"{CHAT_BASE}/conversations/{conversation.id}/participants",
        json={
            "user_id": new_user.id,
            "role": ParticipantRole.MEMBER.value,
        },
        headers=_auth_headers(
            app,
            user,
        ),
    )

    assert response.status_code == 201

    payload = _json(response)

    assert payload["success"] is True
    assert payload["data"]["user_id"] == new_user.id
    assert payload["data"]["status"] == (
        ParticipantStatus.PENDING.value
    )
    assert payload["data"]["role"] == (
        ParticipantRole.MEMBER.value
    )


def test_list_participants(
    client,
    app,
    clinic,
    user,
    make_user,
    make_conversation,
    make_conversation_participant,
):
    conversation, other_user = _make_accessible_conversation(
        clinic,
        user,
        make_user,
        make_conversation,
        make_conversation_participant,
    )

    response = client.get(
        f"{CHAT_BASE}/conversations/{conversation.id}/participants",
        headers=_auth_headers(
            app,
            user,
        ),
    )

    assert response.status_code == 200

    payload = _json(response)

    assert payload["success"] is True
    assert payload["total"] == 2
    assert payload["page"] == 1
    assert payload["per_page"] == 50

    returned_ids = {
        item["user_id"]
        for item in payload["data"]
    }

    assert user.id in returned_ids
    assert other_user.id in returned_ids


def test_update_participant(
    client,
    app,
    clinic,
    user,
    make_user,
    make_conversation,
    make_conversation_participant,
    no_audit,
):
    conversation, other_user = _make_accessible_conversation(
        clinic,
        user,
        make_user,
        make_conversation,
        make_conversation_participant,
    )

    target = db.session.execute(
        db.select(
            ConversationParticipant
        ).where(
            ConversationParticipant.conversation_id
            == conversation.id,
            ConversationParticipant.user_id
            == other_user.id,
        )
    ).scalar_one()

    target.status = ParticipantStatus.PENDING
    target.joined_at = None
    target.left_at = None
    target.removed_at = None

    db.session.flush()

    response = client.patch(
        f"{CHAT_BASE}/conversations/{conversation.id}/participants/{target.id}",
        json={
            "status": ParticipantStatus.ACCEPTED.value,
        },
        headers=_auth_headers(
            app,
            user,
        ),
    )

    assert response.status_code == 200

    payload = _json(response)

    assert payload["success"] is True
    assert payload["data"]["status"] == (
        ParticipantStatus.ACCEPTED.value
    )


def test_leave_conversation(
    client,
    app,
    clinic,
    user,
    make_user,
    make_conversation,
    make_conversation_participant,
):
    conversation, _ = _make_accessible_conversation(
        clinic,
        user,
        make_user,
        make_conversation,
        make_conversation_participant,
    )

    user_participant = db.session.execute(
        db.select(
            ConversationParticipant
        ).where(
            ConversationParticipant.conversation_id
            == conversation.id,
            ConversationParticipant.user_id
            == user.id,
        )
    ).scalar_one()

    user_participant.role = ParticipantRole.MEMBER

    db.session.flush()

    response = client.post(
        f"{CHAT_BASE}/conversations/{conversation.id}/leave",
        headers=_auth_headers(
            app,
            user,
        ),
    )

    assert response.status_code == 200

    payload = _json(response)

    assert payload["success"] is True
    assert payload["data"]["status"] == (
        ParticipantStatus.LEFT.value
    )


def test_read_state(
    client,
    app,
    clinic,
    user,
    make_user,
    make_conversation,
    make_conversation_participant,
    make_message,
):
    conversation, _ = _make_accessible_conversation(
        clinic,
        user,
        make_user,
        make_conversation,
        make_conversation_participant,
    )

    message = make_message(
        clinic=clinic,
        conversation=conversation,
        sender=user,
        status=MessageStatus.SENT,
    )

    response = client.post(
        f"{CHAT_BASE}/conversations/{conversation.id}/read",
        json={
            "last_read_message_id": message.id,
        },
        headers=_auth_headers(
            app,
            user,
        ),
    )

    assert response.status_code == 200

    payload = _json(response)

    assert payload["success"] is True
    assert payload["data"]["last_read_message_id"] == (
        message.id
    )


def test_create_message(
    client,
    app,
    clinic,
    user,
    make_user,
    make_conversation,
    make_conversation_participant,
    no_audit,
):
    conversation, _ = _make_accessible_conversation(
        clinic,
        user,
        make_user,
        make_conversation,
        make_conversation_participant,
    )

    response = client.post(
        f"{CHAT_BASE}/conversations/{conversation.id}/messages",
        json={
            "message_type": "text",
            "content": "Clinical route test message",
            "priority": "normal",
        },
        headers=_auth_headers(
            app,
            user,
        ),
    )

    assert response.status_code == 201

    payload = _json(response)

    assert payload["success"] is True
    assert payload["data"]["conversation_id"] == conversation.id
    assert payload["data"]["sender_id"] == user.id
    assert payload["data"]["content"] == (
        "Clinical route test message"
    )


def test_create_message_rejects_over_maximum_length(
    client,
    app,
    clinic,
    user,
    make_user,
    make_conversation,
    make_conversation_participant,
    no_audit,
):
    conversation, _ = _make_accessible_conversation(
        clinic,
        user,
        make_user,
        make_conversation,
        make_conversation_participant,
    )

    response = client.post(
        f"{CHAT_BASE}/conversations/{conversation.id}/messages",
        json={
            "message_type": "text",
            "content": "x" * 5001,
            "priority": "normal",
        },
        headers=_auth_headers(
            app,
            user,
        ),
    )

    assert response.status_code == 422

    payload = _json(response)

    assert payload["success"] is False


def test_list_messages(
    client,
    app,
    clinic,
    user,
    make_user,
    make_conversation,
    make_conversation_participant,
    make_message,
):
    conversation, other_user = _make_accessible_conversation(
        clinic,
        user,
        make_user,
        make_conversation,
        make_conversation_participant,
    )

    make_message(
        clinic=clinic,
        conversation=conversation,
        sender=user,
        content="First route message",
        status=MessageStatus.SENT,
    )

    make_message(
        clinic=clinic,
        conversation=conversation,
        sender=other_user,
        content="Second route message",
        status=MessageStatus.SENT,
    )

    response = client.get(
        f"{CHAT_BASE}/conversations/{conversation.id}/messages",
        headers=_auth_headers(
            app,
            user,
        ),
    )

    assert response.status_code == 200

    payload = _json(response)

    assert payload["success"] is True
    assert payload["total"] == 2
    assert payload["page"] == 1
    assert payload["per_page"] == 50

    contents = {
        item["content"]
        for item in payload["data"]
    }

    assert "First route message" in contents
    assert "Second route message" in contents


def test_get_message(
    client,
    app,
    clinic,
    user,
    make_user,
    make_conversation,
    make_conversation_participant,
    make_message,
):
    conversation, _ = _make_accessible_conversation(
        clinic,
        user,
        make_user,
        make_conversation,
        make_conversation_participant,
    )

    message = make_message(
        clinic=clinic,
        conversation=conversation,
        sender=user,
        status=MessageStatus.SENT,
    )

    response = client.get(
        f"{CHAT_BASE}/messages/{message.id}",
        headers=_auth_headers(
            app,
            user,
        ),
    )

    assert response.status_code == 200

    payload = _json(response)

    assert payload["success"] is True
    assert payload["data"]["id"] == message.id
    assert payload["data"]["conversation_id"] == (
        conversation.id
    )


def test_edit_message(
    client,
    app,
    clinic,
    user,
    make_user,
    make_conversation,
    make_conversation_participant,
    make_message,
    no_audit,
):
    conversation, _ = _make_accessible_conversation(
        clinic,
        user,
        make_user,
        make_conversation,
        make_conversation_participant,
    )

    message = make_message(
        clinic=clinic,
        conversation=conversation,
        sender=user,
        status=MessageStatus.SENT,
    )

    response = client.patch(
        f"{CHAT_BASE}/messages/{message.id}",
        json={
            "content": "Edited route message",
        },
        headers=_auth_headers(
            app,
            user,
        ),
    )

    assert response.status_code == 200

    payload = _json(response)

    assert payload["success"] is True
    assert payload["data"]["content"] == (
        "Edited route message"
    )


def test_delete_message(
    client,
    app,
    clinic,
    user,
    make_user,
    make_conversation,
    make_conversation_participant,
    make_message,
    no_audit,
):
    conversation, _ = _make_accessible_conversation(
        clinic,
        user,
        make_user,
        make_conversation,
        make_conversation_participant,
    )

    message = make_message(
        clinic=clinic,
        conversation=conversation,
        sender=user,
        status=MessageStatus.SENT,
    )

    response = client.delete(
        f"{CHAT_BASE}/messages/{message.id}",
        headers=_auth_headers(
            app,
            user,
        ),
    )

    assert response.status_code == 200

    payload = _json(response)

    assert payload["success"] is True
    assert payload["data"]["id"] == message.id
    assert payload["data"]["status"] == "deleted"


def test_search_messages(
    client,
    app,
    clinic,
    user,
    make_user,
    make_conversation,
    make_conversation_participant,
    make_message,
):
    conversation, _ = _make_accessible_conversation(
        clinic,
        user,
        make_user,
        make_conversation,
        make_conversation_participant,
    )

    make_message(
        clinic=clinic,
        conversation=conversation,
        sender=user,
        content="unique cardiac route message",
        status=MessageStatus.SENT,
    )

    response = client.get(
        f"{CHAT_BASE}/messages/search",
        query_string={
            "query": "unique cardiac",
        },
        headers=_auth_headers(
            app,
            user,
        ),
    )

    assert response.status_code == 200

    payload = _json(response)

    assert payload["success"] is True
    assert payload["total"] >= 1

    returned_contents = [
        item["content"]
        for item in payload["data"]
    ]

    assert "unique cardiac route message" in (
        returned_contents
    )


def test_get_message_blocks_cross_clinic_access(
    client,
    app,
    clinic,
    make_clinic,
    user,
    make_user,
    make_conversation,
    make_conversation_participant,
    make_message,
):
    other_clinic = make_clinic(
        name="Other Clinic",
    )

    other_user = make_user(
        clinic=other_clinic,
    )

    other_conversation = make_conversation(
        clinic=other_clinic,
        created_by=other_user,
    )

    _accepted_participant(
        make_conversation_participant,
        other_clinic,
        other_conversation,
        other_user,
        role=ParticipantRole.ADMIN,
    )

    message = make_message(
        clinic=other_clinic,
        conversation=other_conversation,
        sender=other_user,
        status=MessageStatus.SENT,
    )

    response = client.get(
        f"{CHAT_BASE}/messages/{message.id}",
        headers=_auth_headers(
            app,
            user,
        ),
    )

    assert response.status_code == 404

    payload = _json(response)

    assert payload["success"] is False