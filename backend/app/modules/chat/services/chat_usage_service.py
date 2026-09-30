from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Literal

from app.extensions import db
from app.core.exceptions import (
    ConflictError,
    NotFoundError,
    ValidationError,
)
from app.core.utils.decorators import transactional

from app.modules.chat.models.chat_usage_model import ChatUsage


UsageType = Literal[
    "direct",
    "group",
    "department",
    "team",
]


_USAGE_FIELD_MAP: dict[UsageType, str] = {
    "direct": "direct_created",
    "group": "group_created",
    "department": "department_created",
    "team": "team_created",
}


def _utc_today() -> date:
    return datetime.now(
        timezone.utc
    ).date()


def _validate_positive_id(
    value,
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


def _normalize_usage_type(
    usage_type: str,
) -> UsageType:
    if not isinstance(
        usage_type,
        str,
    ):
        raise ValidationError(
            "Usage type must be a string"
        )

    usage_type = usage_type.strip().lower()

    if usage_type not in _USAGE_FIELD_MAP:
        raise ValidationError(
            "Invalid usage type"
        )

    return usage_type  # type: ignore[return-value]


def _get_usage(
    *,
    clinic_id: int,
    user_id: int,
    usage_date: date,
    lock: bool = False,
) -> ChatUsage | None:
    query = db.select(
        ChatUsage
    ).where(
        ChatUsage.clinic_id == clinic_id,
        ChatUsage.user_id == user_id,
        ChatUsage.usage_date == usage_date,
    )

    if lock:
        query = query.with_for_update()

    return db.session.execute(
        query
    ).scalar_one_or_none()


def _get_or_create_usage(
    *,
    clinic_id: int,
    user_id: int,
    usage_date: date,
) -> ChatUsage:
    usage = _get_usage(
        clinic_id=clinic_id,
        user_id=user_id,
        usage_date=usage_date,
        lock=True,
    )

    if usage is not None:
        return usage

    usage = ChatUsage(
        clinic_id=clinic_id,
        user_id=user_id,
        usage_date=usage_date,
    )

    db.session.add(
        usage
    )

    try:
        db.session.flush()
    except Exception:
        db.session.rollback()

        usage = _get_usage(
            clinic_id=clinic_id,
            user_id=user_id,
            usage_date=usage_date,
            lock=True,
        )

        if usage is None:
            raise

    return usage


def get_chat_usage(
    *,
    clinic_id: int,
    user_id: int,
    usage_date: date | None = None,
) -> ChatUsage | None:
    _validate_positive_id(
        clinic_id,
        "Clinic ID",
    )

    _validate_positive_id(
        user_id,
        "User ID",
    )

    usage_date = (
        usage_date
        if usage_date is not None
        else _utc_today()
    )

    if not isinstance(
        usage_date,
        date,
    ):
        raise ValidationError(
            "Usage date must be a valid date"
        )

    return _get_usage(
        clinic_id=clinic_id,
        user_id=user_id,
        usage_date=usage_date,
    )


def get_or_create_today_usage(
    *,
    clinic_id: int,
    user_id: int,
) -> ChatUsage:
    _validate_positive_id(
        clinic_id,
        "Clinic ID",
    )

    _validate_positive_id(
        user_id,
        "User ID",
    )

    return _get_or_create_usage(
        clinic_id=clinic_id,
        user_id=user_id,
        usage_date=_utc_today(),
    )


def get_usage_count(
    *,
    clinic_id: int,
    user_id: int,
    usage_type: UsageType,
    usage_date: date | None = None,
) -> int:
    usage_type = _normalize_usage_type(
        usage_type
    )

    usage = get_chat_usage(
        clinic_id=clinic_id,
        user_id=user_id,
        usage_date=usage_date,
    )

    if usage is None:
        return 0

    field_name = _USAGE_FIELD_MAP[
        usage_type
    ]

    return int(
        getattr(
            usage,
            field_name,
        )
    )


@transactional
def ensure_can_create(
    *,
    clinic_id: int,
    user_id: int,
    usage_type: UsageType,
    daily_limit: int,
) -> ChatUsage:
    _validate_positive_id(
        clinic_id,
        "Clinic ID",
    )

    _validate_positive_id(
        user_id,
        "User ID",
    )

    usage_type = _normalize_usage_type(
        usage_type
    )

    if (
        isinstance(daily_limit, bool)
        or not isinstance(daily_limit, int)
        or daily_limit < 0
    ):
        raise ValidationError(
            "Daily limit must be a non-negative integer"
        )

    usage = _get_or_create_usage(
        clinic_id=clinic_id,
        user_id=user_id,
        usage_date=_utc_today(),
    )

    field_name = _USAGE_FIELD_MAP[
        usage_type
    ]

    current_count = int(
        getattr(
            usage,
            field_name,
        )
    )

    if current_count >= daily_limit:
        raise ConflictError(
            f"Daily {usage_type} conversation creation limit "
            f"of {daily_limit} has been reached"
        )

    return usage


@transactional
def increment_usage(
    *,
    clinic_id: int,
    user_id: int,
    usage_type: UsageType,
) -> ChatUsage:
    _validate_positive_id(
        clinic_id,
        "Clinic ID",
    )

    _validate_positive_id(
        user_id,
        "User ID",
    )

    usage_type = _normalize_usage_type(
        usage_type
    )

    usage = _get_or_create_usage(
        clinic_id=clinic_id,
        user_id=user_id,
        usage_date=_utc_today(),
    )

    field_name = _USAGE_FIELD_MAP[
        usage_type
    ]

    current_count = int(
        getattr(
            usage,
            field_name,
        )
    )

    setattr(
        usage,
        field_name,
        current_count + 1,
    )

    return usage


@transactional
def consume_creation_quota(
    *,
    clinic_id: int,
    user_id: int,
    usage_type: UsageType,
    daily_limit: int,
) -> ChatUsage:
    _validate_positive_id(
        clinic_id,
        "Clinic ID",
    )

    _validate_positive_id(
        user_id,
        "User ID",
    )

    usage_type = _normalize_usage_type(
        usage_type
    )

    if (
        isinstance(daily_limit, bool)
        or not isinstance(daily_limit, int)
        or daily_limit < 0
    ):
        raise ValidationError(
            "Daily limit must be a non-negative integer"
        )

    usage = _get_or_create_usage(
        clinic_id=clinic_id,
        user_id=user_id,
        usage_date=_utc_today(),
    )

    field_name = _USAGE_FIELD_MAP[
        usage_type
    ]

    current_count = int(
        getattr(
            usage,
            field_name,
        )
    )

    if current_count >= daily_limit:
        raise ConflictError(
            f"Daily {usage_type} conversation creation limit "
            f"of {daily_limit} has been reached"
        )

    setattr(
        usage,
        field_name,
        current_count + 1,
    )

    return usage