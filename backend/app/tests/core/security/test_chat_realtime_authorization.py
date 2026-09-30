from __future__ import annotations

from datetime import datetime, timezone

from app.extensions import db
from app.core.enums.chat_enums import (
    ConversationType,
    ParticipantStatus,
)
from app.modules.chat.models.conversation_participant_model import (
    ConversationParticipant,
)
from app.modules.chat.realtime import chat_socket
from app.modules.chat.tasks import chat_outbox_task
from app.modules.chat.services.conversation_service import (
    create_conversation,
)


def test_removed_participant_does_not_receive_realtime_event_after_join(
    chat_socket_client_for,
    clinic,
    user,
    make_user,
    make_chat_outbox,
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

    participant = db.session.execute(
        db.select(ConversationParticipant).where(
            ConversationParticipant.conversation_id
            == conversation.id,
            ConversationParticipant.user_id
            == user.id,
        )
    ).scalar_one()

    participant.status = ParticipantStatus.REMOVED
    participant.removed_at = datetime.now(timezone.utc)

    db.session.flush()

    outbox = make_chat_outbox(
        clinic=clinic,
        event_type="message.created",
        payload={
            "conversation_id": conversation.id,
            "message_id": 999999,
        },
    )

    chat_outbox_task._emit_outbox_event(outbox)

    received = client.get_received("/chat")

    matching_events = [
        event
        for event in received
        if event["name"] == "message.created"
    ]

    assert matching_events == []
def test_accepted_participant_still_receives_realtime_event(
    chat_socket_client_for,
    clinic,
    user,
    make_user,
    make_chat_outbox,
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

    other_participant = db.session.execute(
        db.select(ConversationParticipant).where(
            ConversationParticipant.conversation_id
            == conversation.id,
            ConversationParticipant.user_id
            == other_user.id,
        )
    ).scalar_one()

    other_participant.status = ParticipantStatus.ACCEPTED
    other_participant.joined_at = datetime.now(
        timezone.utc,
    )

    db.session.flush()

    removed_client = chat_socket_client_for(
        user=user,
    )

    accepted_client = chat_socket_client_for(
        user=other_user,
    )

    removed_client.emit(
        "conversation.join",
        {
            "conversation_id": conversation.id,
        },
        namespace="/chat",
    )

    accepted_client.emit(
        "conversation.join",
        {
            "conversation_id": conversation.id,
        },
        namespace="/chat",
    )

    removed_client.get_received("/chat")
    accepted_client.get_received("/chat")

    participant = db.session.execute(
        db.select(ConversationParticipant).where(
            ConversationParticipant.conversation_id
            == conversation.id,
            ConversationParticipant.user_id
            == user.id,
        )
    ).scalar_one()

    participant.status = ParticipantStatus.REMOVED
    participant.removed_at = datetime.now(
        timezone.utc,
    )

    db.session.flush()

    outbox = make_chat_outbox(
        clinic=clinic,
        event_type="message.created",
        payload={
            "conversation_id": conversation.id,
            "message_id": 999998,
        },
    )

    chat_outbox_task._emit_outbox_event(
        outbox,
    )

    removed_received = removed_client.get_received(
        "/chat",
    )

    accepted_received = accepted_client.get_received(
        "/chat",
    )

    removed_matching_events = [
        event
        for event in removed_received
        if event["name"] == "message.created"
    ]

    accepted_matching_events = [
        event
        for event in accepted_received
        if event["name"] == "message.created"
    ]

    assert removed_matching_events == []
    assert len(accepted_matching_events) == 1
