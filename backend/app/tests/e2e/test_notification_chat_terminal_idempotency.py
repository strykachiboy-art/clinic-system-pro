from __future__ import annotations

import pytest

from app.core.enums.notification_enums import (
    NotificationChannel,
    NotificationStatus,
)
from app.core.notifications.services import notification_service
from app.extensions import db
from app.modules.chat.models.chat_outbox_model import ChatOutbox
from app.modules.chat.tasks import chat_outbox_task
from app.modules.chat.tasks.chat_outbox_task import (
    process_chat_outbox,
)
from app.modules.chat.workers.chat_outbox_worker import (
    create_outbox_event,
)


@pytest.mark.parametrize(
    "terminal_status",
    [
        NotificationStatus.DELIVERED,
        NotificationStatus.READ,
    ],
)
def test_notification_terminal_delivery_is_idempotent(
    app,
    clinic,
    user,
    make_notification,
    monkeypatch,
    terminal_status,
):
    with app.app_context():
        notification = make_notification(
            clinic_id=clinic.id,
            user_id=user.id,
            channel=NotificationChannel.PUSH,
            status=terminal_status,
            retry_count=2,
        )
        notification_id = notification.id

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
            clinic.id,
            notification_id,
        )

        stored = db.session.get(
            type(notification),
            notification_id,
        )

        assert result is True

        assert stored is not None
        assert stored.status is terminal_status
        assert stored.retry_count == 2

        assert provider_calls == []


def test_processed_chat_outbox_event_is_terminal_and_not_emitted_again(
    app,
    clinic,
    user,
    monkeypatch,
):
    with app.app_context():
        emitted = []

        monkeypatch.setattr(
            chat_outbox_task.ChatSecurityService,
            "get_active_conversation_recipient_user_ids",
            lambda clinic_id, conversation_id: [
                user.id,
            ],
        )

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
            clinic_id=clinic.id,
            event_type="message.created",
            payload={
                "conversation_id": 1001,
                "message_id": 1,
                "sender_id": user.id,
                "message_type": "text",
                "priority": "normal",
                "reply_to_message_id": None,
            },
        )

        event_id = event.id

        first_result = process_chat_outbox.run(
            limit=50,
        )

        first_stored = db.session.get(
            ChatOutbox,
            event_id,
        )

        assert first_result == {
            "claimed": 1,
            "processed": 1,
            "failed": 0,
        }

        assert first_stored is not None
        assert first_stored.status == "processed"
        assert first_stored.attempts == 1
        assert first_stored.processed_at is not None
        assert first_stored.last_error is None

        assert len(emitted) == 1
        assert emitted[0]["payload"]["event_id"] == event_id

        second_result = process_chat_outbox.run(
            limit=50,
        )

        second_stored = db.session.get(
            ChatOutbox,
            event_id,
        )

        assert second_result == {
            "claimed": 0,
            "processed": 0,
            "failed": 0,
        }

        assert second_stored is not None
        assert second_stored.status == "processed"
        assert second_stored.attempts == 1
        assert second_stored.processed_at is not None
        assert second_stored.last_error is None

        assert len(emitted) == 1
        assert emitted[0]["payload"]["event_id"] == event_id
