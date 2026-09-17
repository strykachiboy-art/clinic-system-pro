from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.extensions import db
from app.core.exceptions import (
    ConflictError,
    NotFoundError,
    ValidationError,
)
from app.modules.chat.models.chat_outbox_model import ChatOutbox
from app.modules.chat.workers.chat_outbox_worker import (
    OUTBOX_FAILED,
    OUTBOX_PENDING,
    OUTBOX_PROCESSED,
    OUTBOX_PROCESSING,
    claim_pending_events,
    create_outbox_event,
    get_outbox_event,
    list_outbox_events,
    mark_event_failed,
    mark_event_processed,
    requeue_stale_processing_events,
    retry_failed_event,
)


def _as_utc(
    value: datetime | None,
) -> datetime | None:
    if value is None:
        return None

    if value.tzinfo is None:
        return value.replace(
            tzinfo=timezone.utc,
        )

    return value.astimezone(timezone.utc)


def test_create_outbox_event(
    clinic,
):
    event = create_outbox_event(
        clinic_id=clinic.id,
        event_type="message.created",
        payload={
            "conversation_id": 10,
            "message_id": 20,
        },
    )

    assert event.id is not None
    assert event.clinic_id == clinic.id
    assert event.message_id is None
    assert event.event_type == "message.created"
    assert event.payload == {
        "conversation_id": 10,
        "message_id": 20,
    }
    assert event.status == OUTBOX_PENDING
    assert event.attempts == 0
    assert event.available_at is not None
    assert event.processed_at is None
    assert event.last_error is None


def test_create_outbox_event_supports_message(
    clinic,
    message,
):
    event = create_outbox_event(
        clinic_id=clinic.id,
        event_type="message.created",
        payload={
            "message_id": message.id,
        },
        message_id=message.id,
    )

    assert event.message_id == message.id
    assert event.clinic_id == clinic.id


def test_create_outbox_event_rejects_invalid_clinic(
    app,
):
    with pytest.raises(NotFoundError):
        create_outbox_event(
            clinic_id=999999,
            event_type="message.created",
            payload={},
        )


def test_create_outbox_event_rejects_invalid_message(
    clinic,
):
    with pytest.raises(NotFoundError):
        create_outbox_event(
            clinic_id=clinic.id,
            event_type="message.created",
            payload={},
            message_id=999999,
        )


def test_create_outbox_event_rejects_cross_clinic_message(
    clinic,
    make_clinic,
    message,
):
    other_clinic = make_clinic()

    with pytest.raises(NotFoundError):
        create_outbox_event(
            clinic_id=other_clinic.id,
            event_type="message.created",
            payload={},
            message_id=message.id,
        )


def test_create_outbox_event_rejects_invalid_event_type(
    clinic,
):
    with pytest.raises(ValidationError):
        create_outbox_event(
            clinic_id=clinic.id,
            event_type="   ",
            payload={},
        )


def test_create_outbox_event_rejects_long_event_type(
    clinic,
):
    with pytest.raises(ValidationError):
        create_outbox_event(
            clinic_id=clinic.id,
            event_type="x" * 65,
            payload={},
        )


def test_create_outbox_event_rejects_non_object_payload(
    clinic,
):
    with pytest.raises(ValidationError):
        create_outbox_event(
            clinic_id=clinic.id,
            event_type="message.created",
            payload=[],
        )


def test_create_outbox_event_rejects_non_json_payload(
    clinic,
):
    with pytest.raises(ValidationError):
        create_outbox_event(
            clinic_id=clinic.id,
            event_type="message.created",
            payload={
                "created_at": object(),
            },
        )


def test_create_outbox_event_supports_future_schedule(
    clinic,
):
    available_at = (
        datetime.now(timezone.utc)
        + timedelta(minutes=5)
    )

    event = create_outbox_event(
        clinic_id=clinic.id,
        event_type="message.created",
        payload={},
        available_at=available_at,
    )

    assert event.available_at == available_at


def test_create_outbox_event_rejects_naive_available_at(
    clinic,
):
    with pytest.raises(ValidationError):
        create_outbox_event(
            clinic_id=clinic.id,
            event_type="message.created",
            payload={},
            available_at=datetime.now(),
        )


def test_get_outbox_event(
    clinic,
):
    event = create_outbox_event(
        clinic_id=clinic.id,
        event_type="message.created",
        payload={
            "message_id": 1,
        },
    )

    result = get_outbox_event(
        event_id=event.id,
        clinic_id=clinic.id,
    )

    assert result.id == event.id
    assert result.event_type == "message.created"


def test_get_outbox_event_rejects_wrong_clinic(
    clinic,
):
    event = create_outbox_event(
        clinic_id=clinic.id,
        event_type="message.created",
        payload={},
    )

    with pytest.raises(NotFoundError):
        get_outbox_event(
            event_id=event.id,
            clinic_id=999999,
        )


def test_list_outbox_events(
    clinic,
):
    first = create_outbox_event(
        clinic_id=clinic.id,
        event_type="message.created",
        payload={
            "sequence": 1,
        },
    )

    second = create_outbox_event(
        clinic_id=clinic.id,
        event_type="message.sent",
        payload={
            "sequence": 2,
        },
    )

    result = list_outbox_events(
        clinic_id=clinic.id,
    )

    assert result["total"] == 2
    assert len(result["items"]) == 2
    assert result["page"] == 1
    assert result["per_page"] == 50
    assert result["pages"] == 1
    assert result["has_next"] is False
    assert result["has_previous"] is False
    assert result["items"][0].id == second.id
    assert result["items"][1].id == first.id


def test_list_outbox_events_filters_by_status(
    clinic,
):
    event = create_outbox_event(
        clinic_id=clinic.id,
        event_type="message.created",
        payload={},
    )

    result = list_outbox_events(
        clinic_id=clinic.id,
        status=OUTBOX_PENDING,
    )

    assert result["total"] == 1
    assert result["items"][0].id == event.id

    result = list_outbox_events(
        clinic_id=clinic.id,
        status=OUTBOX_PROCESSED,
    )

    assert result["total"] == 0


def test_list_outbox_events_filters_by_event_type(
    clinic,
):
    matching = create_outbox_event(
        clinic_id=clinic.id,
        event_type="message.created",
        payload={},
    )

    create_outbox_event(
        clinic_id=clinic.id,
        event_type="message.sent",
        payload={},
    )

    result = list_outbox_events(
        clinic_id=clinic.id,
        event_type="message.created",
    )

    assert result["total"] == 1
    assert result["items"][0].id == matching.id


def test_list_outbox_events_filters_by_message(
    clinic,
    message,
):
    matching = create_outbox_event(
        clinic_id=clinic.id,
        event_type="message.created",
        payload={},
        message_id=message.id,
    )

    create_outbox_event(
        clinic_id=clinic.id,
        event_type="message.sent",
        payload={},
    )

    result = list_outbox_events(
        clinic_id=clinic.id,
        message_id=message.id,
    )

    assert result["total"] == 1
    assert result["items"][0].id == matching.id


def test_list_outbox_events_rejects_invalid_status(
    clinic,
):
    with pytest.raises(ValidationError):
        list_outbox_events(
            clinic_id=clinic.id,
            status="unknown",
        )


def test_list_outbox_events_rejects_invalid_message_id(
    clinic,
):
    with pytest.raises(ValidationError):
        list_outbox_events(
            clinic_id=clinic.id,
            message_id=0,
        )


def test_list_outbox_events_pagination_validation(
    clinic,
):
    with pytest.raises(ValidationError):
        list_outbox_events(
            clinic_id=clinic.id,
            page=0,
        )

    with pytest.raises(ValidationError):
        list_outbox_events(
            clinic_id=clinic.id,
            per_page=0,
        )

    with pytest.raises(ValidationError):
        list_outbox_events(
            clinic_id=clinic.id,
            per_page=501,
        )


def test_claim_pending_events(
    clinic,
):
    first = create_outbox_event(
        clinic_id=clinic.id,
        event_type="message.created",
        payload={
            "sequence": 1,
        },
    )

    second = create_outbox_event(
        clinic_id=clinic.id,
        event_type="message.sent",
        payload={
            "sequence": 2,
        },
    )

    events = claim_pending_events(
        limit=2,
    )

    claimed_ids = {
        event.id
        for event in events
    }

    assert claimed_ids == {
        first.id,
        second.id,
    }

    for event in events:
        assert event.status == OUTBOX_PROCESSING
        assert event.attempts == 1


def test_claim_pending_events_respects_available_at(
    clinic,
):
    future = (
        datetime.now(timezone.utc)
        + timedelta(minutes=10)
    )

    future_event = create_outbox_event(
        clinic_id=clinic.id,
        event_type="future.event",
        payload={},
        available_at=future,
    )

    current_event = create_outbox_event(
        clinic_id=clinic.id,
        event_type="current.event",
        payload={},
    )

    events = claim_pending_events(
        limit=10,
    )

    assert len(events) == 1
    assert events[0].id == current_event.id
    assert future_event.status == OUTBOX_PENDING


def test_claim_pending_events_increments_attempts(
    clinic,
):
    event = create_outbox_event(
        clinic_id=clinic.id,
        event_type="message.created",
        payload={},
    )

    first_claim = claim_pending_events(
        limit=1,
    )

    assert first_claim[0].id == event.id
    assert first_claim[0].attempts == 1
    assert first_claim[0].status == OUTBOX_PROCESSING


def test_claim_pending_events_rejects_invalid_limit(
    app,
):
    with pytest.raises(ValidationError):
        claim_pending_events(
            limit=0,
        )

    with pytest.raises(ValidationError):
        claim_pending_events(
            limit=101,
        )


def test_mark_event_processed(
    clinic,
):
    event = create_outbox_event(
        clinic_id=clinic.id,
        event_type="message.created",
        payload={},
    )

    claim_pending_events(
        limit=1,
    )

    processed_at = datetime.now(
        timezone.utc,
    )

    updated = mark_event_processed(
        event_id=event.id,
        clinic_id=clinic.id,
        processed_at=processed_at,
    )

    assert updated.status == OUTBOX_PROCESSED
    assert _as_utc(updated.processed_at) == processed_at
    assert updated.last_error is None


def test_mark_event_processed_rejects_pending_event(
    clinic,
):
    event = create_outbox_event(
        clinic_id=clinic.id,
        event_type="message.created",
        payload={},
    )

    with pytest.raises(ConflictError):
        mark_event_processed(
            event_id=event.id,
            clinic_id=clinic.id,
        )


def test_mark_event_processed_rejects_already_processed_event(
    clinic,
):
    event = create_outbox_event(
        clinic_id=clinic.id,
        event_type="message.created",
        payload={},
    )

    claim_pending_events(
        limit=1,
    )

    mark_event_processed(
        event_id=event.id,
        clinic_id=clinic.id,
    )

    with pytest.raises(ConflictError):
        mark_event_processed(
            event_id=event.id,
            clinic_id=clinic.id,
        )


def test_mark_event_failed_requeues_when_attempts_remain(
    clinic,
):
    event = create_outbox_event(
        clinic_id=clinic.id,
        event_type="message.created",
        payload={},
    )

    claim_pending_events(
        limit=1,
    )

    failed_at = datetime(
        2026,
        9,
        17,
        12,
        0,
        tzinfo=timezone.utc,
    )

    updated = mark_event_failed(
        event_id=event.id,
        clinic_id=clinic.id,
        error="Temporary delivery failure",
        max_attempts=5,
        failed_at=failed_at,
    )

    assert updated.status == OUTBOX_PENDING
    assert updated.attempts == 1
    assert updated.last_error == (
        "Temporary delivery failure"
    )
    assert updated.processed_at is None
    assert _as_utc(updated.available_at) == (
        failed_at
        + timedelta(seconds=1)
    )


def test_mark_event_failed_uses_exponential_backoff(
    clinic,
):
    event = create_outbox_event(
        clinic_id=clinic.id,
        event_type="message.created",
        payload={},
    )

    first_claim = claim_pending_events(
        limit=1,
    )

    assert first_claim[0].attempts == 1

    first_failed_at = datetime(
        2026,
        9,
        17,
        12,
        0,
        tzinfo=timezone.utc,
    )

    mark_event_failed(
        event_id=event.id,
        clinic_id=clinic.id,
        error="First failure",
        max_attempts=5,
        failed_at=first_failed_at,
    )

    event.available_at = first_failed_at
    db.session.flush()

    claim_pending_events(
        limit=1,
        now=first_failed_at,
    )

    second_failed_at = datetime(
        2026,
        9,
        17,
        12,
        1,
        tzinfo=timezone.utc,
    )

    updated = mark_event_failed(
        event_id=event.id,
        clinic_id=clinic.id,
        error="Second failure",
        max_attempts=5,
        failed_at=second_failed_at,
    )

    assert updated.attempts == 2
    assert updated.status == OUTBOX_PENDING
    assert _as_utc(updated.available_at) == (
        second_failed_at
        + timedelta(seconds=2)
    )


def test_mark_event_failed_becomes_terminal_after_max_attempts(
    clinic,
):
    event = create_outbox_event(
        clinic_id=clinic.id,
        event_type="message.created",
        payload={},
    )

    claim_pending_events(
        limit=1,
    )

    updated = mark_event_failed(
        event_id=event.id,
        clinic_id=clinic.id,
        error="Permanent failure",
        max_attempts=1,
    )

    assert updated.status == OUTBOX_FAILED
    assert updated.attempts == 1
    assert updated.last_error == "Permanent failure"
    assert updated.processed_at is None


def test_mark_event_failed_rejects_pending_event(
    clinic,
):
    event = create_outbox_event(
        clinic_id=clinic.id,
        event_type="message.created",
        payload={},
    )

    with pytest.raises(ConflictError):
        mark_event_failed(
            event_id=event.id,
            clinic_id=clinic.id,
            error="Failure",
        )


def test_mark_event_failed_rejects_empty_error(
    clinic,
):
    event = create_outbox_event(
        clinic_id=clinic.id,
        event_type="message.created",
        payload={},
    )

    claim_pending_events(
        limit=1,
    )

    with pytest.raises(ValidationError):
        mark_event_failed(
            event_id=event.id,
            clinic_id=clinic.id,
            error="   ",
        )


def test_mark_event_failed_truncates_long_error(
    clinic,
):
    event = create_outbox_event(
        clinic_id=clinic.id,
        event_type="message.created",
        payload={},
    )

    claim_pending_events(
        limit=1,
    )

    updated = mark_event_failed(
        event_id=event.id,
        clinic_id=clinic.id,
        error="x" * 5000,
        max_attempts=1,
    )

    assert updated.status == OUTBOX_FAILED
    assert len(updated.last_error) == 4000


def test_retry_failed_event(
    clinic,
):
    event = create_outbox_event(
        clinic_id=clinic.id,
        event_type="message.created",
        payload={},
    )

    claim_pending_events(
        limit=1,
    )

    mark_event_failed(
        event_id=event.id,
        clinic_id=clinic.id,
        error="Permanent failure",
        max_attempts=1,
    )

    available_at = datetime(
        2026,
        9,
        17,
        13,
        0,
        tzinfo=timezone.utc,
    )

    retried = retry_failed_event(
        event_id=event.id,
        clinic_id=clinic.id,
        available_at=available_at,
    )

    assert retried.status == OUTBOX_PENDING
    assert _as_utc(retried.available_at) == available_at
    assert retried.last_error is None
    assert retried.processed_at is None
    assert retried.attempts == 1


def test_retry_failed_event_rejects_non_failed_event(
    clinic,
):
    event = create_outbox_event(
        clinic_id=clinic.id,
        event_type="message.created",
        payload={},
    )

    with pytest.raises(ConflictError):
        retry_failed_event(
            event_id=event.id,
            clinic_id=clinic.id,
        )


def test_requeue_stale_processing_events(
    clinic,
):
    event = create_outbox_event(
        clinic_id=clinic.id,
        event_type="message.created",
        payload={},
    )

    claim_pending_events(
        limit=1,
    )

    stale_now = datetime(
        2026,
        9,
        17,
        13,
        0,
        tzinfo=timezone.utc,
    )

    event.updated_at = (
        stale_now
        - timedelta(minutes=10)
    )

    db.session.flush()

    requeued = requeue_stale_processing_events(
        stale_after_seconds=300,
        now=stale_now,
        clinic_id=clinic.id,
    )

    assert len(requeued) == 1
    assert requeued[0].id == event.id
    assert requeued[0].status == OUTBOX_PENDING
    assert _as_utc(requeued[0].available_at) == stale_now
    assert requeued[0].last_error == (
        "Processing lease expired"
    )


def test_requeue_stale_processing_events_ignores_fresh_events(
    clinic,
):
    event = create_outbox_event(
        clinic_id=clinic.id,
        event_type="message.created",
        payload={},
    )

    claim_pending_events(
        limit=1,
    )

    now = datetime.now(
        timezone.utc,
    )

    requeued = requeue_stale_processing_events(
        stale_after_seconds=300,
        now=now,
        clinic_id=clinic.id,
    )

    assert requeued == []
    assert event.status == OUTBOX_PROCESSING


def test_requeue_stale_processing_events_can_filter_clinic(
    clinic,
    make_clinic,
):
    other_clinic = make_clinic()

    first = create_outbox_event(
        clinic_id=clinic.id,
        event_type="message.created",
        payload={},
    )

    second = create_outbox_event(
        clinic_id=other_clinic.id,
        event_type="message.created",
        payload={},
    )

    claim_pending_events(
        limit=2,
    )

    now = datetime.now(
        timezone.utc,
    )

    stale_time = (
        now
        - timedelta(minutes=10)
    )

    first.updated_at = stale_time
    second.updated_at = stale_time

    db.session.flush()

    requeued = requeue_stale_processing_events(
        stale_after_seconds=300,
        now=now,
        clinic_id=clinic.id,
    )

    assert len(requeued) == 1
    assert requeued[0].id == first.id

    db.session.refresh(second)

    assert second.status == OUTBOX_PROCESSING


def test_requeue_stale_processing_events_rejects_invalid_timeout(
    app,
):
    with pytest.raises(ValidationError):
        requeue_stale_processing_events(
            stale_after_seconds=0,
        )


def test_requeue_stale_processing_events_rejects_invalid_limit(
    app,
):
    with pytest.raises(ValidationError):
        requeue_stale_processing_events(
            limit=0,
        )

    with pytest.raises(ValidationError):
        requeue_stale_processing_events(
            limit=101,
        )


def test_outbox_events_are_clinic_scoped(
    clinic,
    make_clinic,
):
    other_clinic = make_clinic()

    first = create_outbox_event(
        clinic_id=clinic.id,
        event_type="message.created",
        payload={},
    )

    second = create_outbox_event(
        clinic_id=other_clinic.id,
        event_type="message.created",
        payload={},
    )

    first_result = list_outbox_events(
        clinic_id=clinic.id,
    )

    second_result = list_outbox_events(
        clinic_id=other_clinic.id,
    )

    assert first_result["total"] == 1
    assert first_result["items"][0].id == first.id

    assert second_result["total"] == 1
    assert second_result["items"][0].id == second.id


def test_processed_event_is_not_claimed_again(
    clinic,
):
    event = create_outbox_event(
        clinic_id=clinic.id,
        event_type="message.created",
        payload={},
    )

    claim_pending_events(
        limit=1,
    )

    mark_event_processed(
        event_id=event.id,
        clinic_id=clinic.id,
    )

    events = claim_pending_events(
        limit=1,
    )

    assert events == []


def test_failed_event_after_max_attempts_is_not_claimed(
    clinic,
):
    event = create_outbox_event(
        clinic_id=clinic.id,
        event_type="message.created",
        payload={},
    )

    claim_pending_events(
        limit=1,
    )

    mark_event_failed(
        event_id=event.id,
        clinic_id=clinic.id,
        error="Permanent failure",
        max_attempts=1,
    )

    events = claim_pending_events(
        limit=1,
    )

    assert events == []


def test_retry_failed_event_can_be_claimed_again(
    clinic,
):
    event = create_outbox_event(
        clinic_id=clinic.id,
        event_type="message.created",
        payload={},
    )

    claim_pending_events(
        limit=1,
    )

    mark_event_failed(
        event_id=event.id,
        clinic_id=clinic.id,
        error="Permanent failure",
        max_attempts=1,
    )

    retry_failed_event(
        event_id=event.id,
        clinic_id=clinic.id,
    )

    events = claim_pending_events(
        limit=1,
    )

    assert len(events) == 1
    assert events[0].id == event.id
    assert events[0].status == OUTBOX_PROCESSING
    assert events[0].attempts == 2