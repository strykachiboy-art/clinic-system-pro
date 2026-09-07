from __future__ import annotations

from datetime import datetime, timezone

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


# ============================================================================
# UTILITIES
# ============================================================================


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _validate_positive_id(
    value,
    field_name,
):
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value <= 0
    ):
        raise ValidationError(
            f"{field_name} must be a positive integer"
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


# ============================================================================
# USER / CLINIC HELPERS
# ============================================================================


def _get_user(
    user_id,
    *,
    clinic_id=None,
    field_name="User ID",
):
    _validate_positive_id(
        user_id,
        field_name,
    )

    query = User.query.filter(
        User.id == user_id,
    )

    if clinic_id is not None:
        query = query.filter(
            User.clinic_id == clinic_id,
        )

    user = query.first()

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
    """
    Ensure the sender and recipient both belong to
    the same clinic.

    This is the primary tenant-isolation boundary
    for messages.
    """

    _validate_positive_id(
        clinic_id,
        "Clinic ID",
    )

    _validate_positive_id(
        sender_id,
        "Sender ID",
    )

    _validate_positive_id(
        recipient_id,
        "Recipient ID",
    )

    clinic = get_clinic(
        clinic_id,
    )

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


# ============================================================================
# MESSAGE HELPERS
# ============================================================================


def _get_message(
    message_id,
    *,
    clinic_id=None,
    lock=False,
):
    _validate_positive_id(
        message_id,
        "Message ID",
    )

    query = Message.query.filter(
        Message.id == message_id,
    )

    if clinic_id is not None:
        query = query.filter(
            Message.clinic_id == clinic_id,
        )

    if lock:
        query = query.with_for_update()

    message = query.first()

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


# ============================================================================
# CREATE MESSAGE
# ============================================================================


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
    """
    Create and send a message.

    The sender is supplied by the authenticated route layer.

    clinic_id and sender_id must never be accepted directly
    from an untrusted request body.
    """

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


# ============================================================================
# UPDATE MESSAGE
# ============================================================================


@transactional
def update_message(
    message_id,
    user_id,
    clinic_id,
    **fields,
):
    """
    Update editable message content.

    Sender, recipient, clinic and thread relationships
    cannot be modified.
    """

    message = _get_message(
        message_id,
        clinic_id=clinic_id,
        lock=True,
    )

    _ensure_message_access(
        message,
        user_id,
    )

    _ensure_not_deleted(
        message,
    )

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


# ============================================================================
# INBOX
# ============================================================================


def get_inbox(
    user_id,
    clinic_id,
    *,
    unread_only=False,
):
    """
    Return messages received by a clinic-owned user.
    """

    _get_user(
        user_id,
        clinic_id=clinic_id,
    )

    query = Message.query.filter(
        Message.clinic_id == clinic_id,
        Message.recipient_id == user_id,
        Message.deleted_at.is_(None),
    )

    if unread_only:
        query = query.filter(
            Message.read_at.is_(None),
        )

    return (
        query
        .order_by(
            Message.created_at.desc(),
            Message.id.desc(),
        )
        .all()
    )


# ============================================================================
# SENT MESSAGES
# ============================================================================


def get_sent_messages(
    user_id,
    clinic_id,
):
    """
    Return messages sent by a clinic-owned user.
    """

    _get_user(
        user_id,
        clinic_id=clinic_id,
    )

    return (
        Message.query
        .filter(
            Message.clinic_id == clinic_id,
            Message.sender_id == user_id,
            Message.deleted_at.is_(None),
        )
        .order_by(
            Message.created_at.desc(),
            Message.id.desc(),
        )
        .all()
    )


# ============================================================================
# GET SINGLE MESSAGE
# ============================================================================


def get_message_for_user(
    message_id,
    user_id,
    clinic_id,
):
    """
    Retrieve a message only when the authenticated
    user is either sender or recipient.
    """

    message = _get_message(
        message_id,
        clinic_id=clinic_id,
    )

    _ensure_message_access(
        message,
        user_id,
    )

    _ensure_not_deleted(
        message,
    )

    return message


# ============================================================================
# MARK READ
# ============================================================================


@transactional
def mark_message_read(
    message_id,
    user_id,
    clinic_id,
):
    """
    Mark a received message as read.

    Only the recipient may perform this operation.
    """

    message = _get_message(
        message_id,
        clinic_id=clinic_id,
        lock=True,
    )

    _ensure_not_deleted(
        message,
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


# ============================================================================
# ARCHIVE
# ============================================================================


@transactional
def archive_message(
    message_id,
    user_id,
    clinic_id,
):
    """
    Archive a message for the participating user.

    The current schema has one status field, so this is a
    shared message state rather than a per-user mailbox state.
    """

    message = _get_message(
        message_id,
        clinic_id=clinic_id,
        lock=True,
    )

    _ensure_message_access(
        message,
        user_id,
    )

    _ensure_not_deleted(
        message,
    )

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


# ============================================================================
# SOFT DELETE
# ============================================================================


@transactional
def delete_message(
    message_id,
    user_id,
    clinic_id,
):
    """
    Soft-delete a message.

    The database record is retained for audit/history.
    """

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


# ============================================================================
# THREAD
# ============================================================================


def get_message_thread(
    message_id,
    user_id,
    clinic_id,
):
    """
    Return the complete message thread containing
    the specified message.

    The thread is reconstructed from the parent chain
    and replies.
    """

    message = get_message_for_user(
        message_id,
        user_id,
        clinic_id,
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

    thread = (
        Message.query
        .filter(
            Message.clinic_id == clinic_id,
            Message.deleted_at.is_(None),
        )
        .order_by(
            Message.created_at.asc(),
            Message.id.asc(),
        )
        .all()
    )

    return [
        item
        for item in thread
        if _belongs_to_thread(
            item,
            root.id,
        )
    ]


def _belongs_to_thread(
    message,
    root_id,
):
    current = message
    visited = set()

    while current is not None:
        if current.id in visited:
            return False

        visited.add(current.id)

        if current.id == root_id:
            return True

        if current.parent_message_id is None:
            return False

        current = current.parent_message

    return False