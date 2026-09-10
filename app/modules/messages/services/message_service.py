from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import aliased

from app.extensions import db

from app.core.audit.services.audit_service import (
    create_audit_log,
)
from app.core.enums.audit_enums import AuditAction
from app.core.enums.message_enums import (
    MessagePriority,
    MessageStatus,
    MessageType,
)
from app.core.exceptions import (
    ConflictError,
    NotFoundError,
    ValidationError,
)
from app.core.utils.decorators import transactional

from app.core.auth.user.models.user_model import User
from app.modules.messages.models.message_model import Message
from app.modules.clinic.services.clinic_service import (
    get_clinic,
)


DEFAULT_PAGE = 1
DEFAULT_PER_PAGE = 50
MAX_PER_PAGE = 500


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _validate_positive_id(
    value,
    field_name,
) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value <= 0
    ):
        raise ValidationError(
            f"{field_name} must be a positive integer"
        )

    return value


def _validate_pagination(
    page,
    per_page,
) -> tuple[int, int]:
    if (
        isinstance(page, bool)
        or not isinstance(page, int)
        or page < 1
    ):
        raise ValidationError(
            "page must be a positive integer"
        )

    if (
        isinstance(per_page, bool)
        or not isinstance(per_page, int)
        or per_page < 1
    ):
        raise ValidationError(
            "per_page must be a positive integer"
        )

    if per_page > MAX_PER_PAGE:
        raise ValidationError(
            f"per_page cannot exceed {MAX_PER_PAGE}"
        )

    return page, per_page


def _paginate(
    statement,
    page,
    per_page,
):
    page, per_page = _validate_pagination(
        page,
        per_page,
    )

    return db.paginate(
        statement,
        page=page,
        per_page=per_page,
        error_out=False,
    )


def _normalize_required_string(
    value,
    field_name,
    max_length=None,
):
    if not isinstance(value, str):
        raise ValidationError(
            f"{field_name} must be a string"
        )

    value = value.strip()

    if not value:
        raise ValidationError(
            f"{field_name} is required"
        )

    if (
        max_length is not None
        and len(value) > max_length
    ):
        raise ValidationError(
            f"{field_name} cannot exceed "
            f"{max_length} characters"
        )

    return value


def _normalize_optional_string(
    value,
    field_name,
    max_length=None,
):
    if value is None:
        return None

    if not isinstance(value, str):
        raise ValidationError(
            f"{field_name} must be a string"
        )

    value = value.strip()

    if not value:
        return None

    if (
        max_length is not None
        and len(value) > max_length
    ):
        raise ValidationError(
            f"{field_name} cannot exceed "
            f"{max_length} characters"
        )

    return value


def _normalize_message_type(
    message_type,
):
    if isinstance(message_type, MessageType):
        return message_type

    try:
        return MessageType(message_type)
    except (
        ValueError,
        TypeError,
    ):
        raise ValidationError(
            "Invalid message type"
        )


def _normalize_message_priority(
    priority,
):
    if isinstance(priority, MessagePriority):
        return priority

    try:
        return MessagePriority(priority)
    except (
        ValueError,
        TypeError,
    ):
        raise ValidationError(
            "Invalid message priority"
        )


def _normalize_message_status(
    status,
):
    if isinstance(status, MessageStatus):
        return status

    try:
        return MessageStatus(status)
    except (
        ValueError,
        TypeError,
    ):
        raise ValidationError(
            "Invalid message status"
        )


def _get_user(
    user_id,
    *,
    clinic_id=None,
    field_name="User ID",
):
    user_id = _validate_positive_id(
        user_id,
        field_name,
    )

    conditions = [
        User.id == user_id,
    ]

    if clinic_id is not None:
        clinic_id = _validate_positive_id(
            clinic_id,
            "Clinic ID",
        )
        conditions.append(
            User.clinic_id == clinic_id
        )

    statement = select(User).where(
        *conditions
    )

    user = db.session.execute(
        statement
    ).scalar_one_or_none()

    if user is None:
        raise NotFoundError(
            f"User {user_id} not found"
        )

    return user


def _validate_message_participants(
    clinic_id,
    sender_id,
    recipient_id,
):
    clinic_id = _validate_positive_id(
        clinic_id,
        "Clinic ID",
    )

    sender_id = _validate_positive_id(
        sender_id,
        "Sender ID",
    )

    recipient_id = _validate_positive_id(
        recipient_id,
        "Recipient ID",
    )

    clinic = get_clinic(clinic_id)

    sender = _get_user(
        sender_id,
        clinic_id=clinic_id,
        field_name="Sender ID",
    )

    recipient = _get_user(
        recipient_id,
        clinic_id=clinic_id,
        field_name="Recipient ID",
    )

    if not sender.is_active:
        raise ValidationError(
            f"Sender {sender_id} is inactive"
        )

    if not recipient.is_active:
        raise ValidationError(
            f"Recipient {recipient_id} is inactive"
        )

    if sender.id == recipient.id:
        raise ValidationError(
            "A user cannot send a message to themselves"
        )

    return clinic, sender, recipient


def _get_message(
    message_id,
    *,
    clinic_id=None,
    lock=False,
):
    message_id = _validate_positive_id(
        message_id,
        "Message ID",
    )

    conditions = [
        Message.id == message_id,
    ]

    if clinic_id is not None:
        clinic_id = _validate_positive_id(
            clinic_id,
            "Clinic ID",
        )
        conditions.append(
            Message.clinic_id == clinic_id
        )

    statement = select(Message).where(
        *conditions
    )

    if lock:
        statement = statement.with_for_update()

    message = db.session.execute(
        statement
    ).scalar_one_or_none()

    if message is None:
        raise NotFoundError(
            f"Message {message_id} not found"
        )

    return message


def _get_parent_message(
    parent_message_id,
    clinic_id,
):
    if parent_message_id is None:
        return None

    parent = _get_message(
        parent_message_id,
        clinic_id=clinic_id,
    )

    if parent.deleted_at is not None:
        raise ConflictError(
            "Cannot reply to a deleted message"
        )

    return parent


def _ensure_message_access(
    message,
    user_id,
):
    user_id = _validate_positive_id(
        user_id,
        "User ID",
    )

    if user_id not in (
        message.sender_id,
        message.recipient_id,
    ):
        raise NotFoundError(
            f"Message {message.id} not found"
        )


def _ensure_not_deleted(
    message,
):
    if message.deleted_at is not None:
        raise ConflictError(
            f"Message {message.id} has been deleted"
        )


@transactional
def create_message(
    clinic_id,
    sender_id,
    recipient_id,
    subject,
    body,
    message_type=MessageType.DIRECT,
    priority=MessagePriority.NORMAL,
    parent_message_id=None,
):
    (
        clinic,
        sender,
        recipient,
    ) = _validate_message_participants(
        clinic_id=clinic_id,
        sender_id=sender_id,
        recipient_id=recipient_id,
    )

    subject = _normalize_required_string(
        subject,
        "Subject",
        max_length=255,
    )

    body = _normalize_required_string(
        body,
        "Message body",
    )

    message_type = _normalize_message_type(
        message_type
    )

    priority = _normalize_message_priority(
        priority
    )

    parent = _get_parent_message(
        parent_message_id,
        clinic.id,
    )

    if parent is not None:
        if parent.recipient_id != sender.id:
            raise ValidationError(
                "You can only reply to a message "
                "addressed to you"
            )

        if parent.sender_id != recipient.id:
            raise ValidationError(
                "Reply recipient must be the original sender"
            )

    message = Message(
        clinic_id=clinic.id,
        sender_id=sender.id,
        recipient_id=recipient.id,
        subject=subject,
        body=body,
        message_type=message_type,
        status=MessageStatus.SENT,
        priority=priority,
        parent_message_id=(
            parent.id
            if parent is not None
            else None
        ),
        sent_at=_utcnow(),
    )

    db.session.add(message)
    db.session.flush()

    create_audit_log(
        action=AuditAction.CREATE,
        entity_type="Message",
        entity_id=message.id,
        description=(
            f"Message sent from user "
            f"{sender.id} to user {recipient.id}"
        ),
        new_value={
            "clinic_id": clinic.id,
            "sender_id": sender.id,
            "recipient_id": recipient.id,
            "subject": subject,
            "message_type": message_type.value,
            "priority": priority.value,
            "status": message.status.value,
            "parent_message_id": (
                message.parent_message_id
            ),
        },
    )

    return message


@transactional
def update_message(
    message_id,
    user_id,
    clinic_id,
    **fields,
):
    message = _get_message(
        message_id,
        clinic_id=clinic_id,
        lock=True,
    )

    _ensure_message_access(
        message,
        user_id,
    )

    _ensure_not_deleted(message)

    if message.status != MessageStatus.SENT:
        raise ConflictError(
            "Only sent messages can be updated"
        )

    allowed_fields = {
        "subject",
        "body",
        "priority",
    }

    unknown_fields = (
        set(fields) - allowed_fields
    )

    if unknown_fields:
        raise ValidationError(
            "Unsupported message fields: "
            + ", ".join(
                sorted(unknown_fields)
            )
        )

    if not fields:
        return message

    if "subject" in fields:
        fields["subject"] = (
            _normalize_required_string(
                fields["subject"],
                "Subject",
                max_length=255,
            )
        )

    if "body" in fields:
        fields["body"] = (
            _normalize_required_string(
                fields["body"],
                "Message body",
            )
        )

    if "priority" in fields:
        fields["priority"] = (
            _normalize_message_priority(
                fields["priority"]
            )
        )

    old_value = {}
    new_value = {}

    for key, new_value_raw in fields.items():
        current_value = getattr(
            message,
            key,
        )

        if current_value == new_value_raw:
            continue

        if key == "body":
            old_value[key] = "[changed]"
            new_value[key] = "[changed]"
        else:
            old_value[key] = (
                current_value.value
                if hasattr(current_value, "value")
                else current_value
            )
            new_value[key] = (
                new_value_raw.value
                if hasattr(new_value_raw, "value")
                else new_value_raw
            )

        setattr(
            message,
            key,
            new_value_raw,
        )

    if new_value:
        create_audit_log(
            action=AuditAction.UPDATE,
            entity_type="Message",
            entity_id=message.id,
            description="Message updated",
            old_value=old_value,
            new_value=new_value,
        )

    return message


def get_inbox(
    user_id,
    clinic_id,
    *,
    unread_only=False,
    page=DEFAULT_PAGE,
    per_page=DEFAULT_PER_PAGE,
):
    user_id = _validate_positive_id(
        user_id,
        "User ID",
    )

    clinic_id = _validate_positive_id(
        clinic_id,
        "Clinic ID",
    )

    page, per_page = _validate_pagination(
        page,
        per_page,
    )

    _get_user(
        user_id,
        clinic_id=clinic_id,
    )

    conditions = [
        Message.clinic_id == clinic_id,
        Message.recipient_id == user_id,
        Message.deleted_at.is_(None),
    ]

    if unread_only:
        conditions.append(
            Message.read_at.is_(None)
        )

    statement = (
        select(Message)
        .where(*conditions)
        .order_by(
            Message.created_at.desc(),
            Message.id.desc(),
        )
    )

    return _paginate(
        statement,
        page,
        per_page,
    )


def get_sent_messages(
    user_id,
    clinic_id,
    *,
    page=DEFAULT_PAGE,
    per_page=DEFAULT_PER_PAGE,
):
    user_id = _validate_positive_id(
        user_id,
        "User ID",
    )

    clinic_id = _validate_positive_id(
        clinic_id,
        "Clinic ID",
    )

    page, per_page = _validate_pagination(
        page,
        per_page,
    )

    _get_user(
        user_id,
        clinic_id=clinic_id,
    )

    statement = (
        select(Message)
        .where(
            Message.clinic_id == clinic_id,
            Message.sender_id == user_id,
            Message.deleted_at.is_(None),
        )
        .order_by(
            Message.created_at.desc(),
            Message.id.desc(),
        )
    )

    return _paginate(
        statement,
        page,
        per_page,
    )


def get_message_for_user(
    message_id,
    user_id,
    clinic_id,
):
    message = _get_message(
        message_id,
        clinic_id=clinic_id,
    )

    _ensure_message_access(
        message,
        user_id,
    )

    _ensure_not_deleted(message)

    return message


@transactional
def mark_message_read(
    message_id,
    user_id,
    clinic_id,
):
    message = _get_message(
        message_id,
        clinic_id=clinic_id,
        lock=True,
    )

    _ensure_not_deleted(message)

    user_id = _validate_positive_id(
        user_id,
        "User ID",
    )

    if message.recipient_id != user_id:
        raise NotFoundError(
            f"Message {message.id} not found"
        )

    if message.read_at is not None:
        return message

    message.read_at = _utcnow()

    create_audit_log(
        action=AuditAction.UPDATE,
        entity_type="Message",
        entity_id=message.id,
        description="Message marked as read",
        old_value={
            "read_at": None,
        },
        new_value={
            "read_at": message.read_at.isoformat(),
        },
    )

    return message


@transactional
def archive_message(
    message_id,
    user_id,
    clinic_id,
):
    message = _get_message(
        message_id,
        clinic_id=clinic_id,
        lock=True,
    )

    _ensure_message_access(
        message,
        user_id,
    )

    _ensure_not_deleted(message)

    if message.status == MessageStatus.ARCHIVED:
        return message

    if message.status != MessageStatus.SENT:
        raise ConflictError(
            "Only sent messages can be archived"
        )

    old_status = message.status.value

    message.status = MessageStatus.ARCHIVED

    create_audit_log(
        action=AuditAction.STATUS_CHANGE,
        entity_type="Message",
        entity_id=message.id,
        description="Message archived",
        old_value={
            "status": old_status,
        },
        new_value={
            "status": message.status.value,
        },
    )

    return message


@transactional
def delete_message(
    message_id,
    user_id,
    clinic_id,
):
    message = _get_message(
        message_id,
        clinic_id=clinic_id,
        lock=True,
    )

    _ensure_message_access(
        message,
        user_id,
    )

    if message.deleted_at is not None:
        return message

    message.deleted_at = _utcnow()

    create_audit_log(
        action=AuditAction.UPDATE,
        entity_type="Message",
        entity_id=message.id,
        description="Message soft deleted",
        old_value={
            "deleted_at": None,
        },
        new_value={
            "deleted_at": message.deleted_at.isoformat(),
        },
    )

    return message


def get_message_thread(
    message_id,
    user_id,
    clinic_id,
    *,
    page=DEFAULT_PAGE,
    per_page=DEFAULT_PER_PAGE,
):
    page, per_page = _validate_pagination(
        page,
        per_page,
    )

    message = get_message_for_user(
        message_id,
        user_id,
        clinic_id,
    )

    clinic_id = _validate_positive_id(
        clinic_id,
        "Clinic ID",
    )

    root = message

    visited = set()

    while root.parent_message_id is not None:
        if root.id in visited:
            raise ConflictError(
                "Message thread contains a circular reference"
            )

        visited.add(root.id)

        root = _get_message(
            root.parent_message_id,
            clinic_id=clinic_id,
        )

    thread_ids = _build_thread_cte(
        root.id,
        clinic_id,
    )

    statement = (
        select(Message)
        .where(
            Message.id.in_(
                select(thread_ids.c.id)
            ),
            Message.clinic_id == clinic_id,
            Message.deleted_at.is_(None),
        )
        .order_by(
            Message.created_at.asc(),
            Message.id.asc(),
        )
    )

    return _paginate(
        statement,
        page,
        per_page,
    )


def _build_thread_cte(
    root_id,
    clinic_id,
):
    root_id = _validate_positive_id(
        root_id,
        "Root Message ID",
    )

    clinic_id = _validate_positive_id(
        clinic_id,
        "Clinic ID",
    )

    thread_ids = (
        select(
            Message.id.label("id")
        )
        .where(
            Message.id == root_id,
            Message.clinic_id == clinic_id,
        )
        .cte(
            "message_thread",
            recursive=True,
        )
    )

    child = aliased(Message)

    thread_ids = thread_ids.union_all(
        select(
            child.id
        ).where(
            child.parent_message_id
            == thread_ids.c.id,
            child.clinic_id == clinic_id,
            child.deleted_at.is_(None),
        )
    )

    return thread_ids