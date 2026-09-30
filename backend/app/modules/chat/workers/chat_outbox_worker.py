from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func

from app.extensions import db
from app.core.exceptions import (
    ConflictError,
    NotFoundError,
    ValidationError,
)
from app.core.utils.decorators import transactional

from app.modules.chat.models.chat_outbox_model import ChatOutbox
from app.modules.chat.models.message_model import Message
from app.modules.clinic.models.clinic_model import Clinic


OUTBOX_PENDING = "pending"
OUTBOX_PROCESSING = "processing"
OUTBOX_PROCESSED = "processed"
OUTBOX_FAILED = "failed"

OUTBOX_STATUSES = {
    OUTBOX_PENDING,
    OUTBOX_PROCESSING,
    OUTBOX_PROCESSED,
    OUTBOX_FAILED,
}

DEFAULT_PAGE = 1
DEFAULT_PER_PAGE = 50
MAX_PER_PAGE = 500

DEFAULT_CLAIM_LIMIT = 50
MAX_CLAIM_LIMIT = 100

DEFAULT_MAX_ATTEMPTS = 5
DEFAULT_STALE_PROCESSING_SECONDS = 300
MAX_ERROR_LENGTH = 4000
MAX_EVENT_TYPE_LENGTH = 64

RETRY_BASE_DELAY_SECONDS = 1
MAX_RETRY_DELAY_SECONDS = 3600


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _validate_positive_id(
    value: Any,
    field_name: str,
) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value <= 0
    ):
        raise ValidationError(
            f"Invalid {field_name}"
        )

    return value


def _validate_pagination(
    page: int,
    per_page: int,
) -> tuple[int, int]:
    if (
        isinstance(page, bool)
        or not isinstance(page, int)
        or page <= 0
    ):
        raise ValidationError(
            "Page must be a positive integer"
        )

    if (
        isinstance(per_page, bool)
        or not isinstance(per_page, int)
        or per_page <= 0
    ):
        raise ValidationError(
            "Per-page must be a positive integer"
        )

    if per_page > MAX_PER_PAGE:
        raise ValidationError(
            f"Per-page cannot exceed {MAX_PER_PAGE}"
        )

    return page, per_page


def _validate_status(
    status: str,
) -> str:
    if not isinstance(status, str):
        raise ValidationError(
            "Outbox status must be a string"
        )

    status = status.strip().lower()

    if status not in OUTBOX_STATUSES:
        raise ValidationError(
            "Invalid outbox status"
        )

    return status


def _normalize_event_type(
    event_type: str,
) -> str:
    if not isinstance(event_type, str):
        raise ValidationError(
            "Event type must be a string"
        )

    event_type = event_type.strip()

    if not event_type:
        raise ValidationError(
            "Event type cannot be empty"
        )

    if len(event_type) > MAX_EVENT_TYPE_LENGTH:
        raise ValidationError(
            f"Event type cannot exceed "
            f"{MAX_EVENT_TYPE_LENGTH} characters"
        )

    return event_type


def _validate_payload(
    payload: dict[str, Any],
) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValidationError(
            "Outbox payload must be an object"
        )

    try:
        json.dumps(payload)
    except (TypeError, ValueError):
        raise ValidationError(
            "Outbox payload must contain JSON-serializable values"
        )

    return payload


def _validate_datetime(
    value: datetime | None,
    field_name: str,
) -> datetime | None:
    if value is None:
        return None

    if not isinstance(value, datetime):
        raise ValidationError(
            f"{field_name} must be a datetime"
        )

    if value.tzinfo is None:
        raise ValidationError(
            f"{field_name} must be timezone-aware"
        )

    return value


def _normalize_error(
    error: str,
) -> str:
    if not isinstance(error, str):
        raise ValidationError(
            "Outbox error must be a string"
        )

    error = error.strip()

    if not error:
        raise ValidationError(
            "Outbox error cannot be empty"
        )

    if len(error) > MAX_ERROR_LENGTH:
        error = error[:MAX_ERROR_LENGTH]

    return error


def _validate_max_attempts(
    max_attempts: int,
) -> int:
    if (
        isinstance(max_attempts, bool)
        or not isinstance(max_attempts, int)
        or max_attempts <= 0
    ):
        raise ValidationError(
            "Max attempts must be a positive integer"
        )

    return max_attempts


def _validate_claim_limit(
    limit: int,
) -> int:
    if (
        isinstance(limit, bool)
        or not isinstance(limit, int)
        or limit <= 0
    ):
        raise ValidationError(
            "Claim limit must be a positive integer"
        )

    if limit > MAX_CLAIM_LIMIT:
        raise ValidationError(
            f"Claim limit cannot exceed {MAX_CLAIM_LIMIT}"
        )

    return limit


def _get_clinic(
    clinic_id: int,
) -> Clinic:
    _validate_positive_id(
        clinic_id,
        "Clinic ID",
    )

    clinic = db.session.get(
        Clinic,
        clinic_id,
    )

    if clinic is None:
        raise NotFoundError(
            f"Clinic {clinic_id} not found"
        )

    return clinic


def _get_message(
    message_id: int,
    clinic_id: int,
) -> Message:
    _validate_positive_id(
        message_id,
        "Message ID",
    )

    message = db.session.execute(
        db.select(Message).where(
            Message.id == message_id,
            Message.clinic_id == clinic_id,
        )
    ).scalar_one_or_none()

    if message is None:
        raise NotFoundError(
            f"Message {message_id} not found"
        )

    return message


def _get_outbox_event(
    event_id: int,
    clinic_id: int,
    *,
    lock: bool = False,
) -> ChatOutbox:
    _validate_positive_id(
        event_id,
        "Outbox event ID",
    )

    _validate_positive_id(
        clinic_id,
        "Clinic ID",
    )

    statement = db.select(
        ChatOutbox
    ).where(
        ChatOutbox.id == event_id,
        ChatOutbox.clinic_id == clinic_id,
    )

    if lock:
        statement = statement.with_for_update()

    event = db.session.execute(
        statement,
    ).scalar_one_or_none()

    if event is None:
        raise NotFoundError(
            f"Outbox event {event_id} not found"
        )

    return event


def _retry_delay_seconds(
    attempts: int,
) -> int:
    exponent = max(
        attempts - 1,
        0,
    )

    delay = (
        RETRY_BASE_DELAY_SECONDS
        * (2 ** exponent)
    )

    return min(
        delay,
        MAX_RETRY_DELAY_SECONDS,
    )


def create_outbox_event(
    clinic_id: int,
    event_type: str,
    payload: dict[str, Any],
    message_id: int | None = None,
    available_at: datetime | None = None,
    *,
    clinic_obj: Clinic | None = None,
    message_obj: Message | None = None,
) -> ChatOutbox:
    _validate_positive_id(
        clinic_id,
        "Clinic ID",
    )

    if clinic_obj is None:
        _get_clinic(
            clinic_id,
        )
    elif clinic_obj.id != clinic_id:
        raise NotFoundError(
            f"Clinic {clinic_id} not found"
        )

    event_type = _normalize_event_type(
        event_type,
    )

    payload = _validate_payload(
        payload,
    )

    if message_id is not None:
        message_id = _validate_positive_id(
            message_id,
            "Message ID",
        )

        if message_obj is None:
            _get_message(
                message_id,
                clinic_id,
            )
        elif (
            message_obj.id != message_id
            or message_obj.clinic_id != clinic_id
        ):
            raise NotFoundError(
                f"Message {message_id} not found"
            )
    elif message_obj is not None:
        raise ValidationError(
            "Message object requires a message ID"
        )

    available_at = _validate_datetime(
        available_at,
        "Available at",
    )

    event = ChatOutbox(
        clinic_id=clinic_id,
        message_id=message_id,
        event_type=event_type,
        payload=payload,
        status=OUTBOX_PENDING,
        attempts=0,
        available_at=(
            available_at
            if available_at is not None
            else _utcnow()
        ),
        processed_at=None,
        last_error=None,
    )

    db.session.add(
        event,
    )

    db.session.flush()

    return event


def get_outbox_event(
    event_id: int,
    clinic_id: int,
) -> ChatOutbox:
    _get_clinic(
        clinic_id,
    )

    return _get_outbox_event(
        event_id,
        clinic_id,
    )


def list_outbox_events(
    clinic_id: int,
    page: int = DEFAULT_PAGE,
    per_page: int = DEFAULT_PER_PAGE,
    status: str | None = None,
    event_type: str | None = None,
    message_id: int | None = None,
):
    _get_clinic(
        clinic_id,
    )

    page, per_page = _validate_pagination(
        page,
        per_page,
    )

    if status is not None:
        status = _validate_status(
            status,
        )

    if event_type is not None:
        event_type = _normalize_event_type(
            event_type,
        )

    if message_id is not None:
        _validate_positive_id(
            message_id,
            "Message ID",
        )

    query = db.select(
        ChatOutbox
    ).where(
        ChatOutbox.clinic_id == clinic_id,
    )

    count_query = db.select(
        func.count(
            ChatOutbox.id,
        )
    ).where(
        ChatOutbox.clinic_id == clinic_id,
    )

    if status is not None:
        query = query.where(
            ChatOutbox.status == status,
        )
        count_query = count_query.where(
            ChatOutbox.status == status,
        )

    if event_type is not None:
        query = query.where(
            ChatOutbox.event_type == event_type,
        )
        count_query = count_query.where(
            ChatOutbox.event_type == event_type,
        )

    if message_id is not None:
        query = query.where(
            ChatOutbox.message_id == message_id,
        )
        count_query = count_query.where(
            ChatOutbox.message_id == message_id,
        )

    total = db.session.execute(
        count_query,
    ).scalar_one()

    offset = (
        page - 1
    ) * per_page

    items = db.session.execute(
        query
        .order_by(
            ChatOutbox.created_at.desc(),
            ChatOutbox.id.desc(),
        )
        .offset(offset)
        .limit(per_page),
    ).scalars().all()

    pages = (
        (total + per_page - 1) // per_page
        if total
        else 0
    )

    return {
        "items": items,
        "page": page,
        "per_page": per_page,
        "total": total,
        "pages": pages,
        "has_next": page < pages,
        "has_previous": (
            page > 1 and total > 0
        ),
    }


@transactional
def claim_pending_events(
    limit: int = DEFAULT_CLAIM_LIMIT,
    now: datetime | None = None,
) -> list[ChatOutbox]:
    limit = _validate_claim_limit(
        limit,
    )

    now = (
        _validate_datetime(
            now,
            "Now",
        )
        if now is not None
        else _utcnow()
    )

    statement = (
        db.select(ChatOutbox)
        .where(
            ChatOutbox.status == OUTBOX_PENDING,
            ChatOutbox.available_at <= now,
        )
        .order_by(
            ChatOutbox.available_at.asc(),
            ChatOutbox.id.asc(),
        )
        .limit(limit)
        .with_for_update(
            skip_locked=True,
        )
    )

    events = db.session.execute(
        statement,
    ).scalars().all()

    for event in events:
        event.status = OUTBOX_PROCESSING
        event.attempts += 1
        event.updated_at = now

    db.session.flush()

    return events


@transactional
def mark_event_processed(
    event_id: int,
    clinic_id: int,
    processed_at: datetime | None = None,
) -> ChatOutbox:
    processed_at = (
        _validate_datetime(
            processed_at,
            "Processed at",
        )
        if processed_at is not None
        else _utcnow()
    )

    event = _get_outbox_event(
        event_id,
        clinic_id,
        lock=True,
    )

    if event.status != OUTBOX_PROCESSING:
        raise ConflictError(
            "Only processing outbox events can be marked processed"
        )

    event.status = OUTBOX_PROCESSED
    event.processed_at = processed_at
    event.last_error = None
    event.updated_at = processed_at

    db.session.flush()

    return event


@transactional
def mark_event_failed(
    event_id: int,
    clinic_id: int,
    error: str,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    failed_at: datetime | None = None,
) -> ChatOutbox:
    max_attempts = _validate_max_attempts(
        max_attempts,
    )

    failed_at = (
        _validate_datetime(
            failed_at,
            "Failed at",
        )
        if failed_at is not None
        else _utcnow()
    )

    error = _normalize_error(
        error,
    )

    event = _get_outbox_event(
        event_id,
        clinic_id,
        lock=True,
    )

    if event.status != OUTBOX_PROCESSING:
        raise ConflictError(
            "Only processing outbox events can be marked failed"
        )

    event.last_error = error
    event.updated_at = failed_at

    if event.attempts >= max_attempts:
        event.status = OUTBOX_FAILED
        event.processed_at = None
    else:
        event.status = OUTBOX_PENDING
        event.available_at = (
            failed_at
            + timedelta(
                seconds=_retry_delay_seconds(
                    event.attempts,
                )
            )
        )
        event.processed_at = None

    db.session.flush()

    return event


@transactional
def retry_failed_event(
    event_id: int,
    clinic_id: int,
    available_at: datetime | None = None,
) -> ChatOutbox:
    available_at = (
        _validate_datetime(
            available_at,
            "Available at",
        )
        if available_at is not None
        else _utcnow()
    )

    event = _get_outbox_event(
        event_id,
        clinic_id,
        lock=True,
    )

    if event.status != OUTBOX_FAILED:
        raise ConflictError(
            "Only failed outbox events can be retried"
        )

    event.status = OUTBOX_PENDING
    event.available_at = available_at
    event.processed_at = None
    event.last_error = None
    event.updated_at = _utcnow()

    db.session.flush()

    return event


@transactional
def requeue_stale_processing_events(
    stale_after_seconds: int = DEFAULT_STALE_PROCESSING_SECONDS,
    now: datetime | None = None,
    clinic_id: int | None = None,
    limit: int = DEFAULT_CLAIM_LIMIT,
) -> list[ChatOutbox]:
    if (
        isinstance(stale_after_seconds, bool)
        or not isinstance(stale_after_seconds, int)
        or stale_after_seconds <= 0
    ):
        raise ValidationError(
            "Stale processing timeout must be a positive integer"
        )

    limit = _validate_claim_limit(
        limit,
    )

    now = (
        _validate_datetime(
            now,
            "Now",
        )
        if now is not None
        else _utcnow()
    )

    if clinic_id is not None:
        _get_clinic(
            clinic_id,
        )

    cutoff = (
        now
        - timedelta(
            seconds=stale_after_seconds,
        )
    )

    filters = [
        ChatOutbox.status == OUTBOX_PROCESSING,
        ChatOutbox.updated_at <= cutoff,
    ]

    if clinic_id is not None:
        filters.append(
            ChatOutbox.clinic_id == clinic_id,
        )

    statement = (
        db.select(ChatOutbox)
        .where(*filters)
        .order_by(
            ChatOutbox.updated_at.asc(),
            ChatOutbox.id.asc(),
        )
        .limit(limit)
        .with_for_update(
            skip_locked=True,
        )
    )

    events = db.session.execute(
        statement,
    ).scalars().all()

    for event in events:
        event.status = OUTBOX_PENDING
        event.available_at = now
        event.last_error = (
            "Processing lease expired"
        )
        event.updated_at = now

    db.session.flush()

    return events