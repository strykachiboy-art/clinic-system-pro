from __future__ import annotations

from unittest.mock import Mock

from app.core.enums.chat_enums import (
    ConversationStatus,
    ConversationType,
    ParticipantStatus,
)
from app.extensions import db
from app.modules.chat.models.conversation_participant_model import (
    ConversationParticipant,
)
from app.modules.chat.services import (
    conversation_service,
    message_service,
)
from app.modules.chat.services.conversation_service import (
    add_participant,
    create_conversation,
    leave_conversation,
    update_conversation,
    update_conversation_status,
    update_participant,
)
from app.modules.chat.services.message_service import (
    create_message,
    delete_message,
    edit_message,
)


def test_chat_conversation_audit_writers_include_clinic_id(
    clinic,
    user,
    make_user,
    monkeypatch,
):
    audit = Mock()

    monkeypatch.setattr(
        conversation_service,
        "create_audit_log",
        audit,
    )

    participant_user = make_user(
        clinic=clinic,
    )

    conversation = create_conversation(
        clinic_id=clinic.id,
        created_by_id=user.id,
        conversation_type=ConversationType.GROUP,
        title="Gate 10 audit conversation",
        participant_user_ids=[
            participant_user.id,
        ],
    )

    update_conversation(
        conversation_id=conversation.id,
        clinic_id=clinic.id,
        title="Gate 10 updated conversation",
    )

    update_conversation_status(
        conversation_id=conversation.id,
        clinic_id=clinic.id,
        new_status=ConversationStatus.ARCHIVED,
    )

    added_user = make_user(
        clinic=clinic,
    )

    added_participant = add_participant(
        conversation_id=conversation.id,
        clinic_id=clinic.id,
        actor_id=user.id,
        user_id=added_user.id,
    )

    assert added_participant.status is ParticipantStatus.PENDING

    update_participant(
        participant_id=added_participant.id,
        clinic_id=clinic.id,
        status=ParticipantStatus.ACCEPTED,
    )

    leave_conversation(
        conversation_id=conversation.id,
        clinic_id=clinic.id,
        user_id=added_user.id,
    )

    add_participant(
        conversation_id=conversation.id,
        clinic_id=clinic.id,
        actor_id=user.id,
        user_id=added_user.id,
    )

    calls = audit.call_args_list

    assert len(calls) == 7

    assert all(
        call.kwargs["clinic_id"] == clinic.id
        for call in calls
    )

    assert [call.kwargs["entity_type"] for call in calls] == [
        "Conversation",
        "Conversation",
        "Conversation",
        "ConversationParticipant",
        "ConversationParticipant",
        "ConversationParticipant",
        "ConversationParticipant",
    ]

    assert db.session.get(
        ConversationParticipant,
        added_participant.id,
    ) is not None


def test_chat_message_audit_writers_include_clinic_id(
    clinic,
    user,
    make_user,
    monkeypatch,
):
    audit = Mock()

    monkeypatch.setattr(
        message_service,
        "create_audit_log",
        audit,
    )

    participant_user = make_user(
        clinic=clinic,
    )

    conversation = create_conversation(
        clinic_id=clinic.id,
        created_by_id=user.id,
        conversation_type=ConversationType.GROUP,
        participant_user_ids=[
            participant_user.id,
        ],
    )

    message = create_message(
        clinic_id=clinic.id,
        conversation_id=conversation.id,
        sender_id=user.id,
        content="Gate 10 original message",
    )

    edit_message(
        message_id=message.id,
        clinic_id=clinic.id,
        user_id=user.id,
        content="Gate 10 edited message",
    )

    delete_message(
        message_id=message.id,
        clinic_id=clinic.id,
        user_id=user.id,
    )

    calls = audit.call_args_list

    assert len(calls) == 3

    assert [call.kwargs["entity_type"] for call in calls] == [
        "Message",
        "Message",
        "Message",
    ]

    assert [call.kwargs["clinic_id"] for call in calls] == [
        clinic.id,
        clinic.id,
        clinic.id,
    ]