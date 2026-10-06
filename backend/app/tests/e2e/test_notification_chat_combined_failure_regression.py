from __future__ import annotations

from datetime import datetime, timedelta, timezone

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
    recover_stale_chat_outbox,
)
from app.modules.chat.workers.chat_outbox_worker import (
    create_outbox_event,
)


def _get_chat_event(event_id: int) -> ChatOutbox:
    event = db.session.get(
        ChatOutbox,
        event_id,
    )

    assert event is not None

    return event


class CombinedNotificationProvider:
    def __init__(self):
        self.calls = []
        self.accepted_keys = set()
        self.logical_deliveries = []

    def send(self, **kwargs):
        key = kwargs["idempotency_key"]

        self.calls.append(key)

        if key not in self.accepted_keys:
            self.accepted_keys.add(key)
            self.logical_deliveries.append(
                kwargs["notification"].id
            )

            raise TimeoutError(
                "provider outcome unknown after acceptance"
            )

        return True


class WorkerCrash(BaseException):
    pass


def test_notification_combined_failure_chain_is_recoverable(
    app,
    clinic,
    user,
    make_notification,
    monkeypatch,
):
    with app.app_context():
        notification = make_notification(
            clinic_id=clinic.id,
            user_id=user.id,
            channel=NotificationChannel.PUSH,
            status=NotificationStatus.PENDING,
            retry_count=0,
        )

        db.session.commit()

        provider = CombinedNotificationProvider()

        monkeypatch.setattr(
            notification_service,
            "get_notification_provider",
            lambda channel, *, clinic_id: provider,
        )

        with pytest.raises(
            TimeoutError,
            match="provider outcome unknown after acceptance",
        ):
            notification_service.deliver_notification(
                clinic.id,
                notification.id,
            )

        first_failure = db.session.get(
            type(notification),
            notification.id,
        )

        assert first_failure is not None
        assert first_failure.status is NotificationStatus.FAILED
        assert first_failure.retry_count == 1
        assert first_failure.error_message == (
            "provider outcome unknown after acceptance"
        )

        assert len(provider.calls) == 1
        assert len(provider.logical_deliveries) == 1

        stable_key = provider.calls[0]

        assert stable_key == (
            f"clinic-notification-"
            f"{clinic.id}-{notification.id}"
        )

        real_commit = db.session.commit
        fail_next_commit = {
            "armed": True,
        }

        def fail_once_on_local_ack():
            if fail_next_commit["armed"]:
                fail_next_commit["armed"] = False

                raise RuntimeError(
                    "local acknowledgement failure"
                )

            real_commit()

        monkeypatch.setattr(
            db.session,
            "commit",
            fail_once_on_local_ack,
        )

        with pytest.raises(
            RuntimeError,
            match="local acknowledgement failure",
        ):
            notification_service.deliver_notification(
                clinic.id,
                notification.id,
            )

        monkeypatch.setattr(
            db.session,
            "commit",
            real_commit,
        )

        second_failure = db.session.get(
            type(notification),
            notification.id,
        )

        assert second_failure is not None
        assert second_failure.status is NotificationStatus.FAILED
        assert second_failure.retry_count == 2
        assert second_failure.error_message == (
            "local acknowledgement failure"
        )

        assert len(provider.calls) == 2
        assert len(provider.logical_deliveries) == 1
        assert provider.calls[1] == stable_key

        result = notification_service.deliver_notification(
            clinic.id,
            notification.id,
        )

        final_notification = db.session.get(
            type(notification),
            notification.id,
        )

        assert result is True

        assert final_notification is not None
        assert final_notification.status is (
            NotificationStatus.DELIVERED
        )
        assert final_notification.retry_count == 2
        assert final_notification.delivered_at is not None
        assert final_notification.error_message is None

        assert len(provider.calls) == 3
        assert provider.calls[0] == stable_key
        assert provider.calls[1] == stable_key
        assert provider.calls[2] == stable_key
        assert len(provider.logical_deliveries) == 1


def test_chat_combined_failure_chain_recovers_to_terminal_state(
    app,
    clinic,
    user,
    monkeypatch,
):
    with app.app_context():
        emitted = []
        emit_calls = {
            "count": 0,
        }
        ack_calls = {
            "count": 0,
        }

        real_mark_event_processed = (
            chat_outbox_task.mark_event_processed
        )
        real_emit_outbox_event = (
            chat_outbox_task._emit_outbox_event
        )

        monkeypatch.setattr(
            chat_outbox_task.ChatSecurityService,
            "get_active_conversation_recipient_user_ids",
            lambda clinic_id, conversation_id: [
                user.id,
            ],
        )

        def fail_once_then_emit(
            event_name,
            payload,
            *,
            room,
            namespace,
        ):
            emit_calls["count"] += 1

            if emit_calls["count"] == 1:
                raise TimeoutError(
                    "Socket.IO provider timeout"
                )

            emitted.append(
                {
                    "event_name": event_name,
                    "payload": payload,
                    "room": room,
                    "namespace": namespace,
                }
            )

        monkeypatch.setattr(
            chat_outbox_task.socketio,
            "emit",
            fail_once_then_emit,
        )

        def fail_first_ack(
            *,
            event_id,
            clinic_id,
            processed_at,
        ):
            ack_calls["count"] += 1

            if ack_calls["count"] == 1:
                raise RuntimeError(
                    "local acknowledgement failure"
                )

            return real_mark_event_processed(
                event_id=event_id,
                clinic_id=clinic_id,
                processed_at=processed_at,
            )

        monkeypatch.setattr(
            chat_outbox_task,
            "mark_event_processed",
            fail_first_ack,
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

        first_failure = _get_chat_event(
            event_id,
        )

        assert first_result == {
            "claimed": 1,
            "processed": 0,
            "failed": 1,
        }

        assert first_failure.status == "pending"
        assert first_failure.attempts == 1
        assert first_failure.processed_at is None
        assert first_failure.last_error == (
            "Socket.IO provider timeout"
        )

        first_failure.available_at = (
            datetime.now(timezone.utc)
            - timedelta(seconds=1)
        )

        db.session.flush()

        second_result = process_chat_outbox.run(
            limit=50,
        )

        second_failure = _get_chat_event(
            event_id,
        )

        assert second_result == {
            "claimed": 1,
            "processed": 0,
            "failed": 1,
        }

        assert second_failure.status == "pending"
        assert second_failure.attempts == 2
        assert second_failure.processed_at is None
        assert second_failure.last_error == (
            "local acknowledgement failure"
        )

        assert len(emitted) == 1
        assert emitted[0]["payload"]["event_id"] == event_id

        second_failure.available_at = (
            datetime.now(timezone.utc)
            - timedelta(seconds=1)
        )

        db.session.flush()

        def crash_outbox_event(event):
            raise WorkerCrash(
                "simulated worker crash"
            )

        monkeypatch.setattr(
            chat_outbox_task,
            "_emit_outbox_event",
            crash_outbox_event,
        )

        with pytest.raises(
            WorkerCrash,
            match="simulated worker crash",
        ):
            process_chat_outbox.run(
                limit=50,
            )

        crashed_event = _get_chat_event(
            event_id,
        )

        assert crashed_event.status == "processing"
        assert crashed_event.attempts == 3
        assert crashed_event.processed_at is None

        crashed_event.updated_at = (
            datetime.now(timezone.utc)
            - timedelta(minutes=10)
        )
        crashed_event.available_at = (
            datetime.now(timezone.utc)
            - timedelta(minutes=10)
        )

        db.session.flush()

        recovery_result = recover_stale_chat_outbox.run(
            stale_after_seconds=300,
            limit=50,
        )

        recovered_event = _get_chat_event(
            event_id,
        )

        assert recovery_result == {
            "requeued": 1,
        }

        assert recovered_event.status == "pending"
        assert recovered_event.attempts == 3
        assert recovered_event.last_error == (
            "Processing lease expired"
        )

        recovered_event.available_at = (
            datetime.now(timezone.utc)
            - timedelta(seconds=1)
        )

        db.session.flush()

        monkeypatch.setattr(
            chat_outbox_task,
            "_emit_outbox_event",
            real_emit_outbox_event,
        )

        final_result = process_chat_outbox.run(
            limit=50,
        )

        final_event = _get_chat_event(
            event_id,
        )

        assert final_result == {
            "claimed": 1,
            "processed": 1,
            "failed": 0,
        }

        assert final_event.status == "processed"
        assert final_event.attempts == 4
        assert final_event.processed_at is not None
        assert final_event.last_error is None

        assert len(emitted) == 2
        assert emitted[0]["payload"]["event_id"] == event_id
        assert emitted[1]["payload"]["event_id"] == event_id

        terminal_result = process_chat_outbox.run(
            limit=50,
        )

        terminal_event = _get_chat_event(
            event_id,
        )

        assert terminal_result == {
            "claimed": 0,
            "processed": 0,
            "failed": 0,
        }

        assert terminal_event.status == "processed"
        assert terminal_event.attempts == 4
        assert terminal_event.processed_at is not None
        assert terminal_event.last_error is None

        assert len(emitted) == 2
        assert emit_calls["count"] == 3
        assert ack_calls["count"] == 2