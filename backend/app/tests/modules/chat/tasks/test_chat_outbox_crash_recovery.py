from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.extensions import db
from app.modules.chat.models.chat_outbox_model import ChatOutbox
from app.modules.chat.realtime.chat_socket import user_room
from app.modules.chat.tasks import chat_outbox_task
from app.modules.chat.tasks.chat_outbox_task import (
    process_chat_outbox,
    recover_stale_chat_outbox,
)
from app.modules.chat.workers.chat_outbox_worker import (
    create_outbox_event,
)


class WorkerCrash(BaseException):
    pass


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


def test_chat_worker_crash_leaves_processing_event_for_stale_recovery(
    clinic,
    monkeypatch,
):
    def crash_emit(
        *args,
        **kwargs,
    ):
        raise WorkerCrash(
            "simulated worker crash"
        )

    monkeypatch.setattr(
        chat_outbox_task,
        "_emit_outbox_event",
        crash_emit,
    )

    event = _create_event(
        clinic,
        conversation_id=901,
    )
    event_id = event.id

    with pytest.raises(
        WorkerCrash,
        match="simulated worker crash",
    ):
        process_chat_outbox.run(
            limit=50,
        )

    crashed_event = _get_event(
        event_id,
    )

    assert crashed_event.status == "processing"
    assert crashed_event.attempts == 1
    assert crashed_event.processed_at is None
    assert crashed_event.last_error is None

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

    recovered_event = _get_event(
        event_id,
    )

    assert recovery_result == {
        "requeued": 1,
    }

    assert recovered_event.status == "pending"
    assert recovered_event.attempts == 1
    assert recovered_event.processed_at is None
    assert recovered_event.available_at is not None
    assert recovered_event.last_error == (
        "Processing lease expired"
    )


def test_recovered_chat_event_is_reprocessed_successfully(
    clinic,
    user,
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

    event = _create_event(
        clinic,
        conversation_id=902,
    )
    event_id = event.id

    event.status = "processing"
    event.attempts = 1
    event.updated_at = (
        datetime.now(timezone.utc)
        - timedelta(minutes=10)
    )
    event.available_at = (
        datetime.now(timezone.utc)
        - timedelta(minutes=10)
    )

    db.session.flush()

    recovery_result = recover_stale_chat_outbox.run(
        stale_after_seconds=300,
        limit=50,
    )

    assert recovery_result == {
        "requeued": 1,
    }

    recovered_event = _get_event(
        event_id,
    )

    assert recovered_event.status == "pending"
    assert recovered_event.attempts == 1
    assert recovered_event.last_error == (
        "Processing lease expired"
    )

    recovered_event.available_at = (
        datetime.now(timezone.utc)
        - timedelta(seconds=1)
    )

    db.session.flush()

    process_result = process_chat_outbox.run(
        limit=50,
    )

    processed_event = _get_event(
        event_id,
    )

    assert process_result == {
        "claimed": 1,
        "processed": 1,
        "failed": 0,
    }

    assert processed_event.status == "processed"
    assert processed_event.attempts == 2
    assert processed_event.processed_at is not None
    assert processed_event.last_error is None

    assert len(emitted) == 1

    emission = emitted[0]

    assert emission["event_name"] == "message.created"
    assert emission["namespace"] == "/chat"
    assert emission["room"] == user_room(
        clinic.id,
        user.id,
    )
    assert emission["payload"]["event_id"] == event_id
    assert emission["payload"]["clinic_id"] == clinic.id
    assert emission["payload"]["conversation_id"] == 902
