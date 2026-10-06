from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.extensions import db
from app.modules.chat.models.chat_outbox_model import ChatOutbox
from app.modules.chat.realtime.chat_socket import user_room
from app.modules.chat.tasks import chat_outbox_task
from app.modules.chat.tasks.chat_outbox_task import (
    process_chat_outbox,
)
from app.modules.chat.workers.chat_outbox_worker import (
    create_outbox_event,
)


def _create_event(
    clinic,
    *,
    conversation_id: int,
):
    return create_outbox_event(
        clinic_id=clinic.id,
        event_type="message.created",
        payload={
            "conversation_id": conversation_id,
            "message_id": 1,
            "sender_id": 1,
            "message_type": "text",
            "priority": "normal",
            "reply_to_message_id": None,
        },
    )


def _get_event(
    event_id: int,
) -> ChatOutbox:
    event = db.session.get(
        ChatOutbox,
        event_id,
    )

    assert event is not None

    return event


@pytest.fixture(autouse=True)
def authorized_outbox_recipient(
    monkeypatch,
    user,
):
    monkeypatch.setattr(
        chat_outbox_task.ChatSecurityService,
        "get_active_conversation_recipient_user_ids",
        lambda clinic_id, conversation_id: [
            user.id,
        ],
    )


def test_chat_successful_emit_with_local_ack_failure_is_retried_safely(
    clinic,
    user,
    monkeypatch,
):
    emitted = []
    ack_calls = {
        "count": 0,
    }

    real_mark_event_processed = (
        chat_outbox_task.mark_event_processed
    )

    def successful_emit(
        event_name,
        payload,
        *,
        room,
        namespace,
    ):
        emitted.append(
            {
                "event_name": event_name,
                "payload": payload,
                "room": room,
                "namespace": namespace,
            }
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
        chat_outbox_task.socketio,
        "emit",
        successful_emit,
    )

    monkeypatch.setattr(
        chat_outbox_task,
        "mark_event_processed",
        fail_first_ack,
    )

    event = _create_event(
        clinic,
        conversation_id=801,
    )
    event_id = event.id

    first_result = process_chat_outbox.run(
        limit=50,
    )

    first_stored = _get_event(
        event_id,
    )

    assert first_result == {
        "claimed": 1,
        "processed": 0,
        "failed": 1,
    }

    assert first_stored.status == "pending"
    assert first_stored.attempts == 1
    assert first_stored.processed_at is None
    assert first_stored.last_error == (
        "local acknowledgement failure"
    )
    assert first_stored.available_at is not None

    assert len(emitted) == 1
    assert emitted[0]["event_name"] == "message.created"
    assert emitted[0]["namespace"] == "/chat"
    assert emitted[0]["room"] == user_room(
        clinic.id,
        user.id,
    )
    assert emitted[0]["payload"]["event_id"] == event_id
    assert emitted[0]["payload"]["clinic_id"] == clinic.id
    assert emitted[0]["payload"]["conversation_id"] == 801

    first_event_id = emitted[0]["payload"]["event_id"]

    first_stored.available_at = (
        datetime.now(timezone.utc)
        - timedelta(seconds=1)
    )

    db.session.flush()

    second_result = process_chat_outbox.run(
        limit=50,
    )

    second_stored = _get_event(
        event_id,
    )

    assert second_result == {
        "claimed": 1,
        "processed": 1,
        "failed": 0,
    }

    assert second_stored.status == "processed"
    assert second_stored.attempts == 2
    assert second_stored.processed_at is not None
    assert second_stored.last_error is None

    assert ack_calls["count"] == 2
    assert len(emitted) == 2

    second_event_id = emitted[1]["payload"]["event_id"]

    assert second_event_id == first_event_id
    assert second_event_id == event_id

    assert emitted[1]["event_name"] == "message.created"
    assert emitted[1]["namespace"] == "/chat"
    assert emitted[1]["room"] == user_room(
        clinic.id,
        user.id,
    )


def test_chat_local_ack_failure_does_not_mark_event_processed(
    clinic,
    monkeypatch,
):
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

    monkeypatch.setattr(
        chat_outbox_task,
        "mark_event_processed",
        lambda **kwargs: (_ for _ in ()).throw(
            RuntimeError("local acknowledgement failure")
        ),
    )

    event = _create_event(
        clinic,
        conversation_id=802,
    )

    result = process_chat_outbox.run(
        limit=50,
    )

    stored = _get_event(
        event.id,
    )

    assert result == {
        "claimed": 1,
        "processed": 0,
        "failed": 1,
    }

    assert len(emitted) == 1
    assert emitted[0]["payload"]["event_id"] == event.id

    assert stored.status == "pending"
    assert stored.attempts == 1
    assert stored.processed_at is None
    assert stored.last_error == (
        "local acknowledgement failure"
    )
