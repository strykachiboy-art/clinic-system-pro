from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.extensions import db
from app.modules.chat.models.chat_outbox_model import ChatOutbox
from app.modules.chat.tasks import chat_outbox_task
from app.modules.chat.tasks.chat_outbox_task import (
    process_chat_outbox,
)
from app.modules.chat.workers.chat_outbox_worker import (
    create_outbox_event,
)
from app.modules.chat.realtime.chat_socket import user_room


def _create_event(
    clinic,
    *,
    conversation_id: int = 1,
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


@pytest.mark.parametrize(
    ("failure", "expected_error"),
    [
        (
            TimeoutError("Socket.IO provider timeout"),
            "Socket.IO provider timeout",
        ),
        (
            ConnectionError("Socket.IO connection failed"),
            "Socket.IO connection failed",
        ),
        (
            RuntimeError("Socket.IO unavailable"),
            "Socket.IO unavailable",
        ),
    ],
)
def test_chat_outbox_socketio_failure_matrix_is_retryable(
    clinic,
    monkeypatch,
    failure,
    expected_error,
):
    def failing_emit(
        *args,
        **kwargs,
    ):
        raise failure

    monkeypatch.setattr(
        chat_outbox_task.socketio,
        "emit",
        failing_emit,
    )

    event = _create_event(
        clinic,
        conversation_id=700,
    )
    event_id = event.id

    result = process_chat_outbox.run(
        limit=50,
    )

    stored = _get_event(
        event_id,
    )

    assert result == {
        "claimed": 1,
        "processed": 0,
        "failed": 1,
    }

    assert stored.status == "pending"
    assert stored.attempts == 1
    assert stored.processed_at is None
    assert stored.last_error == expected_error
    assert stored.available_at is not None

    assert (
        stored.available_at.replace(
            tzinfo=(
                stored.available_at.tzinfo
                or timezone.utc
            ),
        )
        >= datetime.now(timezone.utc)
    ) or (
        stored.available_at.replace(
            tzinfo=(
                stored.available_at.tzinfo
                or timezone.utc
            ),
        )
        > datetime.now(timezone.utc) - timedelta(
            seconds=5,
        )
    )


def test_chat_outbox_socketio_retry_preserves_event_identity(
    clinic,
    monkeypatch,
    user,
):
    emitted = []
    calls = {
        "count": 0,
    }

    def fail_once_then_capture(
        event_name,
        payload,
        *,
        room,
        namespace,
    ):
        calls["count"] += 1

        if calls["count"] == 1:
            raise TimeoutError(
                "Socket.IO outcome unknown"
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
        fail_once_then_capture,
    )

    event = _create_event(
        clinic,
        conversation_id=701,
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
        "Socket.IO outcome unknown"
    )

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

    assert calls["count"] == 2
    assert len(emitted) == 1

    emission = emitted[0]

    assert emission["event_name"] == "message.created"
    assert emission["namespace"] == "/chat"
    assert emission["room"] == user_room(
        clinic.id,
        user.id,
    )

    assert emission["payload"]["event_id"] == event_id
    assert emission["payload"]["event_id"] == second_stored.id
    assert emission["payload"]["clinic_id"] == clinic.id
    assert emission["payload"]["event_type"] == (
        "message.created"
    )
    assert emission["payload"]["conversation_id"] == 701
