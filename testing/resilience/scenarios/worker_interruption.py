from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

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


def _create_event(clinic):
    return create_outbox_event(
        clinic_id=clinic.id,
        event_type="message.created",
        payload={
            "conversation_id": 123,
            "message_id": 456,
            "sender_id": 789,
            "message_type": "text",
            "priority": "normal",
            "reply_to_message_id": None,
        },
    )


def test_worker_interruption_recovers_stale_event_for_retry(
    clinic,
    monkeypatch,
):
    calls = {
        "count": 0,
    }

    def interrupt_once(*args, **kwargs):
        calls["count"] += 1

        if calls["count"] == 1:
            raise KeyboardInterrupt(
                "Synthetic worker interruption"
            )

    monkeypatch.setattr(
        chat_outbox_task,
        "_emit_outbox_event",
        interrupt_once,
    )

    event = _create_event(
        clinic,
    )

    with pytest.raises(
        KeyboardInterrupt,
        match="Synthetic worker interruption",
    ):
        process_chat_outbox.run(
            limit=50,
        )

    stored = db.session.get(
        ChatOutbox,
        event.id,
    )

    assert stored is not None
    assert stored.status == "processing"
    assert stored.attempts == 1
    assert stored.processed_at is None
    assert stored.last_error is None

    stale_at = datetime.now(
        timezone.utc,
    ) - timedelta(
        seconds=301,
    )

    stored.updated_at = stale_at
    stored.available_at = stale_at

    db.session.flush()

    recovery_result = recover_stale_chat_outbox.run(
        stale_after_seconds=300,
        limit=50,
    )

    assert recovery_result == {
        "requeued": 1,
    }

    stored = db.session.get(
        ChatOutbox,
        event.id,
    )

    assert stored is not None
    assert stored.status == "pending"
    assert stored.attempts == 1
    assert stored.last_error == (
        "Processing lease expired"
    )

    retry_result = process_chat_outbox.run(
        limit=50,
    )

    stored = db.session.get(
        ChatOutbox,
        event.id,
    )

    assert retry_result == {
        "claimed": 1,
        "processed": 1,
        "failed": 0,
    }

    assert stored is not None
    assert stored.status == "processed"
    assert stored.attempts == 2
    assert stored.processed_at is not None
    assert stored.last_error is None
    assert calls["count"] == 2
