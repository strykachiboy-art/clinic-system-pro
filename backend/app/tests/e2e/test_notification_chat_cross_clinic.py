from __future__ import annotations

import pytest

from app.core.enums.chat_enums import (
    ConversationStatus,
    ConversationType,
    ParticipantRole,
    ParticipantStatus,
)
from app.core.enums.notification_enums import (
    NotificationChannel,
    NotificationStatus,
)
from app.core.auth.user.models.user_model import User
from app.core.notifications.models.notification_models import Notification
from app.core.notifications.services import notification_service
from app.extensions import db
from app.modules.chat.models.conversation_model import Conversation
from app.modules.chat.models.conversation_participant_model import (
    ConversationParticipant,
)
from app.modules.chat.realtime.chat_socket import user_room
from app.modules.chat.services.chat_security_service import (
    ChatSecurityService,
)
from app.modules.chat.tasks import chat_outbox_task
from app.modules.chat.tasks.chat_outbox_task import (
    process_chat_outbox,
)
from app.modules.chat.workers.chat_outbox_worker import (
    create_outbox_event,
)


def test_notification_delivery_rejects_cross_clinic_lookup_before_provider(
    app,
    make_clinic,
    make_user,
    make_notification,
    monkeypatch,
):
    with app.app_context():
        source_clinic = make_clinic(
            name="Notification Source Clinic",
        )
        foreign_clinic = make_clinic(
            name="Notification Foreign Clinic",
        )

        source_user = make_user(
            source_clinic,
        )

        notification = make_notification(
            clinic_id=source_clinic.id,
            user_id=source_user.id,
            channel=NotificationChannel.PUSH,
            status=NotificationStatus.PENDING,
            retry_count=0,
        )

        db.session.commit()

        provider_calls = []

        class Provider:
            def send(self, **kwargs):
                provider_calls.append(kwargs)
                return True

        monkeypatch.setattr(
            notification_service,
            "get_notification_provider",
            lambda channel, *, clinic_id: Provider(),
        )

        result = notification_service.deliver_notification(
            foreign_clinic.id,
            notification.id,
        )

        stored = db.session.get(
            Notification,
            notification.id,
        )

        assert result is False

        assert stored is not None
        assert stored.clinic_id == source_clinic.id
        assert stored.user_id == source_user.id
        assert stored.status is NotificationStatus.PENDING
        assert stored.retry_count == 0
        assert stored.failed_at is None
        assert stored.delivered_at is None
        assert stored.error_message is None

        assert provider_calls == []


def test_chat_recipient_query_excludes_foreign_clinic_participant(
    app,
    make_clinic,
    make_user,
):
    with app.app_context():
        source_clinic = make_clinic(
            name="Chat Source Clinic",
        )
        foreign_clinic = make_clinic(
            name="Chat Foreign Clinic",
        )

        source_user = make_user(
            source_clinic,
        )
        foreign_user = make_user(
            foreign_clinic,
        )

        conversation = Conversation(
            clinic_id=source_clinic.id,
            conversation_type=ConversationType.DIRECT,
            status=ConversationStatus.ACTIVE,
            direct_key=None,
            created_by_id=source_user.id,
        )

        db.session.add(conversation)
        db.session.flush()

        source_participant = ConversationParticipant(
            clinic_id=source_clinic.id,
            conversation_id=conversation.id,
            user_id=source_user.id,
            role=ParticipantRole.MEMBER,
            status=ParticipantStatus.ACCEPTED,
        )

        foreign_participant = ConversationParticipant(
            clinic_id=foreign_clinic.id,
            conversation_id=conversation.id,
            user_id=foreign_user.id,
            role=ParticipantRole.MEMBER,
            status=ParticipantStatus.ACCEPTED,
        )

        db.session.add_all(
            [
                source_participant,
                foreign_participant,
            ]
        )
        db.session.flush()

        recipients = (
            ChatSecurityService
            .get_active_conversation_recipient_user_ids(
                source_clinic.id,
                conversation.id,
            )
        )

        assert recipients == [
            source_user.id,
        ]

        assert foreign_user.id not in recipients


def test_chat_outbox_emits_only_to_source_clinic_recipients(
    app,
    make_clinic,
    make_user,
    monkeypatch,
):
    with app.app_context():
        source_clinic = make_clinic(
            name="Chat Delivery Source Clinic",
        )
        foreign_clinic = make_clinic(
            name="Chat Delivery Foreign Clinic",
        )

        source_user = make_user(
            source_clinic,
        )
        foreign_user = make_user(
            foreign_clinic,
        )

        conversation = Conversation(
            clinic_id=source_clinic.id,
            conversation_type=ConversationType.DIRECT,
            status=ConversationStatus.ACTIVE,
            direct_key=None,
            created_by_id=source_user.id,
        )

        db.session.add(conversation)
        db.session.flush()

        db.session.add_all(
            [
                ConversationParticipant(
                    clinic_id=source_clinic.id,
                    conversation_id=conversation.id,
                    user_id=source_user.id,
                    role=ParticipantRole.MEMBER,
                    status=ParticipantStatus.ACCEPTED,
                ),
                ConversationParticipant(
                    clinic_id=foreign_clinic.id,
                    conversation_id=conversation.id,
                    user_id=foreign_user.id,
                    role=ParticipantRole.MEMBER,
                    status=ParticipantStatus.ACCEPTED,
                ),
            ]
        )

        db.session.flush()

        emitted = []

        monkeypatch.setattr(
            chat_outbox_task.socketio,
            "emit",
            lambda event_name, payload, *, room, namespace: emitted.append(
                {
                    "event_name": event_name,
                    "payload": payload,
                    "room": room,
                    "namespace": namespace,
                }
            ),
        )

        event = create_outbox_event(
            clinic_id=source_clinic.id,
            event_type="message.created",
            payload={
                "conversation_id": conversation.id,
                "message_id": 1,
                "sender_id": source_user.id,
                "message_type": "text",
                "priority": "normal",
                "reply_to_message_id": None,
            },
        )

        result = process_chat_outbox.run(
            limit=50,
        )

        assert result == {
            "claimed": 1,
            "processed": 1,
            "failed": 0,
        }

        assert len(emitted) == 1

        emission = emitted[0]

        assert emission["room"] == user_room(
            source_clinic.id,
            source_user.id,
        )

        assert emission["room"] != user_room(
            foreign_clinic.id,
            foreign_user.id,
        )

        assert emission["payload"]["event_id"] == event.id
        assert emission["payload"]["clinic_id"] == source_clinic.id
        assert emission["namespace"] == "/chat"
