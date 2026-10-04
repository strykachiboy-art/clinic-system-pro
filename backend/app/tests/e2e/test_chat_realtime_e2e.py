from __future__ import annotations

from app.core.audit.models.audit_model import AuditLog
from app.core.enums.audit_enums import AuditAction
from app.core.enums.chat_enums import (
    MessageStatus,
    ParticipantStatus,
)
from app.core.enums.role_enums import Role
from app.extensions import db
from app.modules.chat.models.chat_outbox_model import ChatOutbox
from app.modules.chat.models.conversation_participant_model import (
    ConversationParticipant,
)
from app.modules.chat.models.message_model import Message
from app.modules.chat.tasks.chat_outbox_task import process_chat_outbox


def _event_payload(events, event_name):
    matches = [
        event
        for event in events
        if event["name"] == event_name
    ]

    assert matches, (
        f"Expected socket event {event_name!r}; "
        f"received {[event['name'] for event in events]!r}"
    )

    args = matches[-1]["args"]

    assert isinstance(args, list)
    assert args
    assert isinstance(args[0], dict)

    return args[0]


def test_chat_realtime_e2e(
    client,
    db,
    clinic,
    make_clinic,
    make_staff,
    e2e_login,
    chat_socket_client_for,
):
    sender_staff = make_staff(
        clinic=clinic,
        role=Role.DOCTOR,
        user_overrides={
            "email": "e2e-chat-sender@test.com",
        },
    )

    recipient_staff = make_staff(
        clinic=clinic,
        role=Role.NURSE,
        user_overrides={
            "email": "e2e-chat-recipient@test.com",
        },
    )

    sender_login = e2e_login(
        "e2e-chat-sender@test.com",
    )

    recipient_login = e2e_login(
        "e2e-chat-recipient@test.com",
    )

    assert sender_login["user_id"] == sender_staff.user.id
    assert sender_login["role"] == Role.DOCTOR.value

    assert recipient_login["user_id"] == recipient_staff.user.id
    assert recipient_login["role"] == Role.NURSE.value

    sender_headers = {
        "Authorization": (
            f"Bearer {sender_login['access_token']}"
        ),
    }

    recipient_headers = {
        "Authorization": (
            f"Bearer {recipient_login['access_token']}"
        ),
    }

    conversation_response = client.post(
        "/api/v1/chat/conversations",
        json={
            "conversation_type": "direct",
            "title": "Phase 8 Gate 10 realtime E2E",
            "participant_user_ids": [
                recipient_staff.user.id,
            ],
        },
        headers=sender_headers,
    )

    assert conversation_response.status_code == 201, (
        conversation_response.get_json()
    )

    conversation_body = conversation_response.get_json()

    assert conversation_body["success"] is True
    assert conversation_body["data"]["clinic_id"] == clinic.id
    assert conversation_body["data"]["created_by_id"] == sender_staff.user.id
    assert conversation_body["data"]["status"] == "active"

    conversation_id = conversation_body["data"]["id"]

    persisted_participants = list(
        db.session.execute(
            db.select(ConversationParticipant)
            .where(
                ConversationParticipant.conversation_id
                == conversation_id,
            )
            .order_by(
                ConversationParticipant.id.asc(),
            )
        ).scalars()
    )

    assert len(persisted_participants) == 2

    sender_participant = next(
        item
        for item in persisted_participants
        if item.user_id == sender_staff.user.id
    )

    recipient_participant = next(
        item
        for item in persisted_participants
        if item.user_id == recipient_staff.user.id
    )

    assert sender_participant.clinic_id == clinic.id
    assert sender_participant.status is ParticipantStatus.ACCEPTED

    assert recipient_participant.clinic_id == clinic.id
    assert recipient_participant.status is ParticipantStatus.PENDING

    participant_response = client.patch(
        (
            "/api/v1/chat/conversations/"
            f"{conversation_id}/participants/"
            f"{recipient_participant.id}"
        ),
        json={
            "status": "accepted",
        },
        headers=sender_headers,
    )

    assert participant_response.status_code == 200, (
        participant_response.get_json()
    )

    participant_body = participant_response.get_json()

    assert participant_body["success"] is True
    assert participant_body["data"]["clinic_id"] == clinic.id
    assert participant_body["data"]["conversation_id"] == conversation_id
    assert participant_body["data"]["user_id"] == recipient_staff.user.id
    assert participant_body["data"]["status"] == "accepted"

    refreshed_recipient_participant = db.session.get(
        ConversationParticipant,
        recipient_participant.id,
    )

    assert refreshed_recipient_participant is not None
    assert (
        refreshed_recipient_participant.status
        is ParticipantStatus.ACCEPTED
    )
    assert (
        refreshed_recipient_participant.clinic_id
        == clinic.id
    )

    update_response = client.patch(
        f"/api/v1/chat/conversations/{conversation_id}",
        json={
            "title": "Phase 8 Gate 10 realtime E2E updated",
        },
        headers=sender_headers,
    )

    assert update_response.status_code == 200, (
        update_response.get_json()
    )

    updated_conversation_body = (
        update_response.get_json()
    )

    assert updated_conversation_body["success"] is True
    assert (
        updated_conversation_body["data"]["title"]
        == "Phase 8 Gate 10 realtime E2E updated"
    )

    recipient_socket = chat_socket_client_for(
        user=recipient_staff.user,
    )

    foreign_clinic = make_clinic()

    foreign_staff = make_staff(
        clinic=foreign_clinic,
        role=Role.DOCTOR,
        user_overrides={
            "email": "e2e-chat-foreign@test.com",
        },
    )

    foreign_login = e2e_login(
        "e2e-chat-foreign@test.com",
    )

    foreign_headers = {
        "Authorization": (
            f"Bearer {foreign_login['access_token']}"
        ),
    }

    assert foreign_login["user_id"] == foreign_staff.user.id
    assert foreign_login["role"] == Role.DOCTOR.value

    cross_clinic_get_response = client.get(
        f"/api/v1/chat/conversations/{conversation_id}",
        headers=foreign_headers,
    )

    assert cross_clinic_get_response.status_code == 404
    assert (
        cross_clinic_get_response.get_json()["success"]
        is False
    )

    cross_clinic_message_response = client.post(
        (
            "/api/v1/chat/conversations/"
            f"{conversation_id}/messages"
        ),
        json={
            "content": "cross-clinic attempt",
        },
        headers=foreign_headers,
    )

    assert cross_clinic_message_response.status_code == 404
    assert (
        cross_clinic_message_response.get_json()["success"]
        is False
    )

    assert recipient_socket.is_connected("/chat") is True

    connected_events = recipient_socket.get_received(
        "/chat",
    )

    _event_payload(
        connected_events,
        "chat.connected",
    )

    recipient_socket.emit(
        "conversation.join",
        {
            "conversation_id": conversation_id,
        },
        namespace="/chat",
    )

    joined_events = recipient_socket.get_received(
        "/chat",
    )

    joined_payload = _event_payload(
        joined_events,
        "conversation.joined",
    )

    assert joined_payload["conversation_id"] == conversation_id
    assert joined_payload["user_id"] == recipient_staff.user.id

    foreign_socket = chat_socket_client_for(
        user=foreign_staff.user,
    )

    assert foreign_socket.is_connected("/chat") is True

    foreign_connected_events = foreign_socket.get_received(
        "/chat",
    )

    _event_payload(
        foreign_connected_events,
        "chat.connected",
    )

    foreign_socket.emit(
        "conversation.join",
        {
            "conversation_id": conversation_id,
        },
        namespace="/chat",
    )

    foreign_join_events = foreign_socket.get_received(
        "/chat",
    )

    _event_payload(
        foreign_join_events,
        "chat.error",
    )

    assert not any(
        event["name"] == "conversation.joined"
        for event in foreign_join_events
    )

    message_response = client.post(
        (
            "/api/v1/chat/conversations/"
            f"{conversation_id}/messages"
        ),
        json={
            "content": (
                "Phase 8 Gate 10 realtime message"
            ),
        },
        headers=sender_headers,
    )

    assert message_response.status_code == 201, (
        message_response.get_json()
    )

    message_body = message_response.get_json()

    assert message_body["success"] is True
    assert message_body["data"]["clinic_id"] == clinic.id
    assert message_body["data"]["conversation_id"] == conversation_id
    assert message_body["data"]["sender_id"] == sender_staff.user.id
    assert message_body["data"]["status"] == "pending"

    message_id = message_body["data"]["id"]

    persisted_message = db.session.get(
        Message,
        message_id,
    )

    assert persisted_message is not None
    assert persisted_message.clinic_id == clinic.id
    assert persisted_message.conversation_id == conversation_id
    assert persisted_message.sender_id == sender_staff.user.id
    assert persisted_message.content == (
        "Phase 8 Gate 10 realtime message"
    )
    assert persisted_message.status is MessageStatus.PENDING

    created_outbox = db.session.execute(
        db.select(ChatOutbox)
        .where(
            ChatOutbox.clinic_id == clinic.id,
            ChatOutbox.message_id == message_id,
            ChatOutbox.event_type == "message.created",
        )
    ).scalar_one_or_none()

    assert created_outbox is not None
    assert created_outbox.status == "pending"
    assert created_outbox.attempts == 0

    _ = recipient_socket.get_received("/chat")
    _ = foreign_socket.get_received("/chat")

    task_result = process_chat_outbox.run(
        limit=50,
    )

    assert task_result == {
        "claimed": 1,
        "processed": 1,
        "failed": 0,
    }

    created_events = recipient_socket.get_received(
        "/chat",
    )

    created_payload = _event_payload(
        created_events,
        "message.created",
    )

    assert created_payload["event_id"] == created_outbox.id
    assert created_payload["event_type"] == "message.created"
    assert created_payload["clinic_id"] == clinic.id
    assert created_payload["conversation_id"] == conversation_id
    assert created_payload["message_id"] == message_id
    assert created_payload["sender_id"] == sender_staff.user.id

    foreign_message_events = foreign_socket.get_received(
        "/chat",
    )

    assert not any(
        event["name"] == "message.created"
        for event in foreign_message_events
    )

    db.session.expire_all()

    processed_created_outbox = db.session.get(
        ChatOutbox,
        created_outbox.id,
    )

    assert processed_created_outbox is not None
    assert processed_created_outbox.clinic_id == clinic.id
    assert processed_created_outbox.status == "processed"
    assert processed_created_outbox.attempts == 1
    assert processed_created_outbox.processed_at is not None

    edit_response = client.patch(
        f"/api/v1/chat/messages/{message_id}",
        json={
            "content": (
                "Phase 8 Gate 10 realtime message edited"
            ),
        },
        headers=sender_headers,
    )

    assert edit_response.status_code == 200, (
        edit_response.get_json()
    )

    edit_body = edit_response.get_json()

    assert edit_body["success"] is True
    assert edit_body["data"]["id"] == message_id
    assert edit_body["data"]["clinic_id"] == clinic.id
    assert edit_body["data"]["status"] == "edited"
    assert edit_body["data"]["content"] == (
        "Phase 8 Gate 10 realtime message edited"
    )

    _ = recipient_socket.get_received("/chat")
    _ = foreign_socket.get_received("/chat")

    edit_task_result = process_chat_outbox.run(
        limit=50,
    )

    assert edit_task_result == {
        "claimed": 1,
        "processed": 1,
        "failed": 0,
    }

    edit_events = recipient_socket.get_received(
        "/chat",
    )

    edit_payload = _event_payload(
        edit_events,
        "message.updated",
    )

    assert edit_payload["event_type"] == "message.updated"
    assert edit_payload["clinic_id"] == clinic.id
    assert edit_payload["conversation_id"] == conversation_id
    assert edit_payload["message_id"] == message_id
    assert edit_payload["sender_id"] == sender_staff.user.id
    assert edit_payload["status"] == "edited"

    foreign_edit_events = foreign_socket.get_received(
        "/chat",
    )

    assert not any(
        event["name"] == "message.updated"
        for event in foreign_edit_events
    )

    deleted_response = client.delete(
        f"/api/v1/chat/messages/{message_id}",
        headers=sender_headers,
    )

    assert deleted_response.status_code == 200, (
        deleted_response.get_json()
    )

    deleted_body = deleted_response.get_json()

    assert deleted_body["success"] is True
    assert deleted_body["data"]["id"] == message_id
    assert deleted_body["data"]["clinic_id"] == clinic.id
    assert deleted_body["data"]["status"] == "deleted"

    _ = recipient_socket.get_received("/chat")
    _ = foreign_socket.get_received("/chat")

    delete_task_result = process_chat_outbox.run(
        limit=50,
    )

    assert delete_task_result == {
        "claimed": 1,
        "processed": 1,
        "failed": 0,
    }

    delete_events = recipient_socket.get_received(
        "/chat",
    )

    delete_payload = _event_payload(
        delete_events,
        "message.deleted",
    )

    assert delete_payload["event_type"] == "message.deleted"
    assert delete_payload["clinic_id"] == clinic.id
    assert delete_payload["conversation_id"] == conversation_id
    assert delete_payload["message_id"] == message_id
    assert delete_payload["sender_id"] == sender_staff.user.id
    assert delete_payload["status"] == "deleted"

    foreign_delete_events = foreign_socket.get_received(
        "/chat",
    )

    assert not any(
        event["name"] == "message.deleted"
        for event in foreign_delete_events
    )

    db.session.expire_all()

    final_message = db.session.get(
        Message,
        message_id,
    )

    assert final_message is not None
    assert final_message.clinic_id == clinic.id
    assert final_message.conversation_id == conversation_id
    assert final_message.sender_id == sender_staff.user.id
    assert final_message.status is MessageStatus.DELETED
    assert final_message.content == (
        "Phase 8 Gate 10 realtime message edited"
    )

    outbox_events = list(
        db.session.execute(
            db.select(ChatOutbox)
            .where(
                ChatOutbox.clinic_id == clinic.id,
                ChatOutbox.message_id == message_id,
            )
            .order_by(
                ChatOutbox.id.asc(),
            )
        ).scalars()
    )

    assert [
        event.event_type
        for event in outbox_events
    ] == [
        "message.created",
        "message.updated",
        "message.deleted",
    ]

    assert all(
        event.status == "processed"
        and event.attempts == 1
        and event.processed_at is not None
        and event.clinic_id == clinic.id
        for event in outbox_events
    )

    conversation_audits = list(
        db.session.execute(
            db.select(AuditLog)
            .where(
                AuditLog.clinic_id == clinic.id,
                AuditLog.entity_type == "Conversation",
                AuditLog.entity_id == conversation_id,
            )
            .order_by(
                AuditLog.id.asc(),
            )
        ).scalars()
    )

    assert any(
        row.action is AuditAction.CREATE
        for row in conversation_audits
    )

    assert any(
        row.action is AuditAction.UPDATE
        for row in conversation_audits
    )

    message_audits = list(
        db.session.execute(
            db.select(AuditLog)
            .where(
                AuditLog.clinic_id == clinic.id,
                AuditLog.entity_type == "Message",
                AuditLog.entity_id == message_id,
            )
            .order_by(
                AuditLog.id.asc(),
            )
        ).scalars()
    )

    assert [
        row.action
        for row in message_audits
    ] == [
        AuditAction.CREATE,
        AuditAction.UPDATE,
        AuditAction.DELETE,
    ]

    assert all(
        row.clinic_id == clinic.id
        for row in message_audits
    )

    foreign_message_audits = list(
        db.session.execute(
            db.select(AuditLog)
            .where(
                AuditLog.entity_id == message_id,
                AuditLog.clinic_id != clinic.id,
            )
        ).scalars()
    )

    assert foreign_message_audits == []

    if recipient_socket.is_connected("/chat"):
        recipient_socket.disconnect(
            namespace="/chat",
        )

    if foreign_socket.is_connected("/chat"):
        foreign_socket.disconnect(
            namespace="/chat",
        )

    print("PHASE8_GATE10_CHAT_REALTIME_E2E=PASS")
