from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import exists, func

from app.extensions import db
from app.core.enums.chat_enums import (
    MessageStatus,
    MessageType,
    ParticipantStatus,
)
from app.core.exceptions import (
    NotFoundError,
    ValidationError,
)
from app.modules.chat.models.conversation_model import Conversation
from app.modules.chat.models.conversation_participant_model import (
    ConversationParticipant,
)
from app.modules.chat.models.message_model import Message
from app.modules.chat.services.chat_security_service import (
    ChatSecurityService,
)


DEFAULT_PAGE = 1
DEFAULT_PER_PAGE = 50
MAX_PER_PAGE = 500
MAX_SEARCH_LENGTH = 200


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


def _normalize_enum(
    value: Any,
    enum_class,
    field_name: str,
):
    if isinstance(value, enum_class):
        return value

    try:
        return enum_class(value)
    except (TypeError, ValueError):
        raise ValidationError(
            f"Invalid {field_name}"
        )


def _normalize_search_query(
    query: str,
) -> str:
    if not isinstance(query, str):
        raise ValidationError(
            "Search query must be a string"
        )

    query = query.strip()

    if not query:
        raise ValidationError(
            "Search query cannot be empty"
        )

    if len(query) > MAX_SEARCH_LENGTH:
        raise ValidationError(
            f"Search query cannot exceed "
            f"{MAX_SEARCH_LENGTH} characters"
        )

    return query


def _validate_datetime_range(
    start_at: datetime | None,
    end_at: datetime | None,
) -> None:
    if start_at is not None and not isinstance(
        start_at,
        datetime,
    ):
        raise ValidationError(
            "Start date must be a datetime"
        )

    if end_at is not None and not isinstance(
        end_at,
        datetime,
    ):
        raise ValidationError(
            "End date must be a datetime"
        )

    if (
        start_at is not None
        and end_at is not None
        and start_at > end_at
    ):
        raise ValidationError(
            "Start date cannot be after end date"
        )


def _ensure_user_can_search_clinic(
    user_id: int,
    clinic_id: int,
) -> None:
    user_id = _validate_positive_id(
        user_id,
        "User ID",
    )

    clinic_id = _validate_positive_id(
        clinic_id,
        "Clinic ID",
    )

    user = ChatSecurityService.get_active_user(
        user_id,
    )

    ChatSecurityService.ensure_staff_clinic_consistency(
        user,
    )

    ChatSecurityService.ensure_same_clinic(
        user,
        clinic_id,
    )


def _build_participant_exists_query(
    user_id: int,
) -> Any:
    return exists(
        db.select(ConversationParticipant.id)
        .where(
            ConversationParticipant.conversation_id
            == Message.conversation_id,
            ConversationParticipant.user_id
            == user_id,
            ConversationParticipant.clinic_id
            == Message.clinic_id,
            ConversationParticipant.status
            == ParticipantStatus.ACCEPTED,
        )
    )


def search_messages(
    clinic_id: int,
    user_id: int,
    query: str,
    page: int = DEFAULT_PAGE,
    per_page: int = DEFAULT_PER_PAGE,
    conversation_id: int | None = None,
    sender_id: int | None = None,
    message_type: MessageType | None = None,
    status: MessageStatus | None = None,
    start_at: datetime | None = None,
    end_at: datetime | None = None,
):
    clinic_id = _validate_positive_id(
        clinic_id,
        "Clinic ID",
    )

    user_id = _validate_positive_id(
        user_id,
        "User ID",
    )

    if conversation_id is not None:
        conversation_id = _validate_positive_id(
            conversation_id,
            "Conversation ID",
        )

    if sender_id is not None:
        sender_id = _validate_positive_id(
            sender_id,
            "Sender ID",
        )

    page, per_page = _validate_pagination(
        page,
        per_page,
    )

    query = _normalize_search_query(
        query,
    )

    _validate_datetime_range(
        start_at,
        end_at,
    )

    _ensure_user_can_search_clinic(
        user_id,
        clinic_id,
    )

    if conversation_id is not None:
        conversation = (
            ChatSecurityService
            .ensure_user_can_access_conversation(
                user_id,
                conversation_id,
            )
        )

        if conversation.clinic_id != clinic_id:
            raise NotFoundError(
                "Conversation not found"
            )

    message_type = (
        _normalize_enum(
            message_type,
            MessageType,
            "message type",
        )
        if message_type is not None
        else None
    )

    status = (
        _normalize_enum(
            status,
            MessageStatus,
            "message status",
        )
        if status is not None
        else None
    )

    statement = db.select(
        Message
    ).join(
        Conversation,
        Conversation.id == Message.conversation_id,
    ).where(
        Message.clinic_id == clinic_id,
        Conversation.clinic_id == clinic_id,
        Message.content.is_not(None),
        Message.status != MessageStatus.DELETED,
    )

    count_statement = db.select(
        func.count(Message.id)
    ).join(
        Conversation,
        Conversation.id == Message.conversation_id,
    ).where(
        Message.clinic_id == clinic_id,
        Conversation.clinic_id == clinic_id,
        Message.content.is_not(None),
        Message.status != MessageStatus.DELETED,
    )

    statement = statement.where(
        _build_participant_exists_query(
            user_id,
        )
    )

    count_statement = count_statement.where(
        _build_participant_exists_query(
            user_id,
        )
    )

    like = f"%{query}%"

    content_condition = Message.content.ilike(
        like,
    )

    statement = statement.where(
        content_condition,
    )

    count_statement = count_statement.where(
        content_condition,
    )

    if conversation_id is not None:
        statement = statement.where(
            Message.conversation_id
            == conversation_id,
        )
        count_statement = count_statement.where(
            Message.conversation_id
            == conversation_id,
        )

    if sender_id is not None:
        statement = statement.where(
            Message.sender_id == sender_id,
        )
        count_statement = count_statement.where(
            Message.sender_id == sender_id,
        )

    if message_type is not None:
        statement = statement.where(
            Message.message_type == message_type,
        )
        count_statement = count_statement.where(
            Message.message_type == message_type,
        )

    if status is not None:
        statement = statement.where(
            Message.status == status,
        )
        count_statement = count_statement.where(
            Message.status == status,
        )

    if start_at is not None:
        statement = statement.where(
            Message.created_at >= start_at,
        )
        count_statement = count_statement.where(
            Message.created_at >= start_at,
        )

    if end_at is not None:
        statement = statement.where(
            Message.created_at <= end_at,
        )
        count_statement = count_statement.where(
            Message.created_at <= end_at,
        )

    total = db.session.execute(
        count_statement,
    ).scalar_one()

    offset = (page - 1) * per_page

    items = db.session.execute(
        statement
        .order_by(
            Message.created_at.desc(),
            Message.id.desc(),
        )
        .offset(offset)
        .limit(per_page),
    ).scalars().unique().all()

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