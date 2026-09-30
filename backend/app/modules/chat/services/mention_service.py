from __future__ import annotations

from datetime import datetime, timezone

from app.extensions import db
from app.core.audit.services.audit_service import create_audit_log
from app.core.enums.audit_enums import AuditAction
from app.core.enums.chat_enums import MentionType, ParticipantStatus
from app.core.exceptions import (
    ConflictError,
    NotFoundError,
    ValidationError,
)
from app.core.utils.decorators import transactional

from app.core.auth.user.models.user_model import User
from app.modules.patient.models.patient_model import Patient
from app.modules.chat.models.conversation_model import Conversation
from app.modules.chat.models.conversation_participant_model import (
    ConversationParticipant,
)
from app.modules.chat.models.message_model import Message
from app.modules.chat.models.message_mention_model import MessageMention


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_PAGE_SIZE = 500
MAX_MENTIONS_PER_MESSAGE = 100


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _validate_positive_id(
    value: int,
    field_name: str,
) -> None:
    if not isinstance(value, int) or value < 1:
        raise ValidationError(
            f"{field_name} must be greater than or equal to 1"
        )


def _validate_pagination(
    page: int,
    per_page: int,
) -> None:
    if page < 1:
        raise ValidationError(
            "Page must be greater than or equal to 1"
        )

    if per_page < 1:
        raise ValidationError(
            "per_page must be greater than or equal to 1"
        )

    if per_page > MAX_PAGE_SIZE:
        raise ValidationError(
            f"per_page cannot exceed {MAX_PAGE_SIZE}"
        )


def _normalize_mention_type(
    mention_type: MentionType,
) -> MentionType:
    if isinstance(mention_type, MentionType):
        return mention_type

    try:
        return MentionType(mention_type)
    except (TypeError, ValueError) as exc:
        raise ValidationError(
            f"Invalid mention type: {mention_type}"
        ) from exc


def _get_message(
    message_id: int,
    clinic_id: int,
) -> Message:
    _validate_positive_id(
        message_id,
        "Message ID",
    )

    message = db.session.scalar(
        db.select(Message).where(
            Message.id == message_id,
            Message.clinic_id == clinic_id,
        )
    )

    if message is None:
        raise NotFoundError(
            f"Message {message_id} not found"
        )

    return message


def _get_mention(
    mention_id: int,
    clinic_id: int,
) -> MessageMention:
    _validate_positive_id(
        mention_id,
        "Mention ID",
    )

    mention = db.session.scalar(
        db.select(MessageMention).where(
            MessageMention.id == mention_id,
            MessageMention.clinic_id == clinic_id,
        )
    )

    if mention is None:
        raise NotFoundError(
            f"Message mention {mention_id} not found"
        )

    return mention


def _get_user(
    user_id: int,
    clinic_id: int,
) -> User:
    _validate_positive_id(
        user_id,
        "User ID",
    )

    user = db.session.get(
        User,
        user_id,
    )

    if user is None:
        raise NotFoundError(
            f"User {user_id} not found"
        )

    if getattr(user, "clinic_id", None) != clinic_id:
        raise NotFoundError(
            f"User {user_id} not found"
        )

    return user


def _get_patient(
    patient_id: int,
    clinic_id: int,
) -> Patient:
    _validate_positive_id(
        patient_id,
        "Patient ID",
    )

    patient = db.session.get(
        Patient,
        patient_id,
    )

    if patient is None:
        raise NotFoundError(
            f"Patient {patient_id} not found"
        )

    if patient.clinic_id != clinic_id:
        raise NotFoundError(
            f"Patient {patient_id} not found"
        )

    return patient


def _get_conversation(
    conversation_id: int,
    clinic_id: int,
) -> Conversation:
    _validate_positive_id(
        conversation_id,
        "Conversation ID",
    )

    conversation = db.session.get(
        Conversation,
        conversation_id,
    )

    if conversation is None:
        raise NotFoundError(
            f"Conversation {conversation_id} not found"
        )

    if conversation.clinic_id != clinic_id:
        raise NotFoundError(
            f"Conversation {conversation_id} not found"
        )

    return conversation


def _ensure_actor_is_participant(
    message: Message,
    actor_user_id: int,
) -> ConversationParticipant:
    participant = db.session.scalar(
        db.select(ConversationParticipant).where(
            ConversationParticipant.clinic_id == message.clinic_id,
            ConversationParticipant.conversation_id
            == message.conversation_id,
            ConversationParticipant.user_id == actor_user_id,
            ConversationParticipant.status
            == ParticipantStatus.ACCEPTED,
        )
    )

    if participant is None:
        raise ValidationError(
            "Actor is not an accepted participant in this conversation"
        )

    return participant


def _validate_target(
    *,
    mention_type: MentionType,
    mentioned_user_id: int | None,
    mentioned_patient_id: int | None,
    mentioned_conversation_id: int | None,
    clinic_id: int,
) -> None:
    targets = (
        mentioned_user_id,
        mentioned_patient_id,
        mentioned_conversation_id,
    )

    if sum(target is not None for target in targets) != 1:
        raise ValidationError(
            "Exactly one mention target must be provided"
        )

    if mention_type in (
        MentionType.USER,
        MentionType.STAFF,
    ):
        if mentioned_user_id is None:
            raise ValidationError(
                "USER and STAFF mentions require mentioned_user_id"
            )

        _get_user(
            mentioned_user_id,
            clinic_id,
        )

        return

    if mention_type == MentionType.PATIENT:
        if mentioned_patient_id is None:
            raise ValidationError(
                "PATIENT mentions require mentioned_patient_id"
            )

        _get_patient(
            mentioned_patient_id,
            clinic_id,
        )

        return

    if mention_type == MentionType.GROUP:
        if mentioned_conversation_id is None:
            raise ValidationError(
                "GROUP mentions require mentioned_conversation_id"
            )

        _get_conversation(
            mentioned_conversation_id,
            clinic_id,
        )

        return

    raise ValidationError(
        f"Unsupported mention type: {mention_type}"
    )


def _validate_positions(
    *,
    position_start: int | None,
    position_end: int | None,
) -> None:
    if position_start is not None and position_start < 0:
        raise ValidationError(
            "position_start cannot be negative"
        )

    if position_end is not None and position_end < 0:
        raise ValidationError(
            "position_end cannot be negative"
        )

    if (
        position_start is not None
        and position_end is not None
        and position_end < position_start
    ):
        raise ValidationError(
            "position_end must be greater than or equal to "
            "position_start"
        )


def _mention_exists(
    *,
    message_id: int,
    mention_type: MentionType,
    mentioned_user_id: int | None,
    mentioned_patient_id: int | None,
    mentioned_conversation_id: int | None,
) -> bool:
    query = db.select(MessageMention.id).where(
        MessageMention.message_id == message_id,
        MessageMention.mention_type == mention_type,
    )

    if mentioned_user_id is not None:
        query = query.where(
            MessageMention.mentioned_user_id == mentioned_user_id
        )

    if mentioned_patient_id is not None:
        query = query.where(
            MessageMention.mentioned_patient_id == mentioned_patient_id
        )

    if mentioned_conversation_id is not None:
        query = query.where(
            MessageMention.mentioned_conversation_id
            == mentioned_conversation_id
        )

    return db.session.scalar(query) is not None


# ---------------------------------------------------------------------------
# Get Mention
# ---------------------------------------------------------------------------


def get_mention(
    mention_id: int,
    clinic_id: int,
) -> MessageMention:
    _validate_positive_id(
        clinic_id,
        "Clinic ID",
    )

    return _get_mention(
        mention_id,
        clinic_id,
    )


# ---------------------------------------------------------------------------
# List Mentions For Message
# ---------------------------------------------------------------------------


def list_message_mentions(
    message_id: int,
    clinic_id: int,
    page: int = 1,
    per_page: int = 50,
) -> dict:
    _validate_positive_id(
        clinic_id,
        "Clinic ID",
    )

    _validate_pagination(
        page,
        per_page,
    )

    message = _get_message(
        message_id,
        clinic_id,
    )

    stmt = (
        db.select(MessageMention)
        .where(
            MessageMention.message_id == message.id,
            MessageMention.clinic_id == clinic_id,
        )
        .order_by(
            MessageMention.position_start.asc().nulls_last(),
            MessageMention.id.asc(),
        )
    )

    total = db.session.scalar(
        db.select(db.func.count())
        .select_from(
            db.select(MessageMention.id)
            .where(
                MessageMention.message_id == message.id,
                MessageMention.clinic_id == clinic_id,
            )
            .subquery()
        )
    ) or 0

    items = db.session.scalars(
        stmt.offset(
            (page - 1) * per_page
        ).limit(
            per_page
        )
    ).all()

    pages = (
        (total + per_page - 1) // per_page
        if total
        else 0
    )

    return {
        "data": items,
        "page": page,
        "per_page": per_page,
        "total": total,
        "pages": pages,
        "has_next": page < pages,
        "has_previous": page > 1 and total > 0,
    }


# ---------------------------------------------------------------------------
# List Mentions For User
# ---------------------------------------------------------------------------


def list_user_mentions(
    user_id: int,
    clinic_id: int,
    page: int = 1,
    per_page: int = 50,
) -> dict:
    _validate_positive_id(
        clinic_id,
        "Clinic ID",
    )

    _validate_positive_id(
        user_id,
        "User ID",
    )

    _validate_pagination(
        page,
        per_page,
    )

    _get_user(
        user_id,
        clinic_id,
    )

    stmt = (
        db.select(MessageMention)
        .where(
            MessageMention.clinic_id == clinic_id,
            MessageMention.mentioned_user_id == user_id,
        )
        .order_by(
            MessageMention.created_at.desc(),
            MessageMention.id.desc(),
        )
    )

    total = db.session.scalar(
        db.select(db.func.count())
        .select_from(
            db.select(MessageMention.id)
            .where(
                MessageMention.clinic_id == clinic_id,
                MessageMention.mentioned_user_id == user_id,
            )
            .subquery()
        )
    ) or 0

    items = db.session.scalars(
        stmt.offset(
            (page - 1) * per_page
        ).limit(
            per_page
        )
    ).all()

    pages = (
        (total + per_page - 1) // per_page
        if total
        else 0
    )

    return {
        "data": items,
        "page": page,
        "per_page": per_page,
        "total": total,
        "pages": pages,
        "has_next": page < pages,
        "has_previous": page > 1 and total > 0,
    }


# ---------------------------------------------------------------------------
# Create Mention
# ---------------------------------------------------------------------------


@transactional
def create_mention(
    *,
    message_id: int,
    clinic_id: int,
    actor_user_id: int,
    mention_type: MentionType,
    mentioned_user_id: int | None = None,
    mentioned_patient_id: int | None = None,
    mentioned_conversation_id: int | None = None,
    position_start: int | None = None,
    position_end: int | None = None,
) -> MessageMention:
    _validate_positive_id(
        clinic_id,
        "Clinic ID",
    )

    _validate_positive_id(
        actor_user_id,
        "Actor user ID",
    )

    message = _get_message(
        message_id,
        clinic_id,
    )

    _ensure_actor_is_participant(
        message,
        actor_user_id,
    )

    mention_type = _normalize_mention_type(
        mention_type,
    )

    _validate_positions(
        position_start=position_start,
        position_end=position_end,
    )

    _validate_target(
        mention_type=mention_type,
        mentioned_user_id=mentioned_user_id,
        mentioned_patient_id=mentioned_patient_id,
        mentioned_conversation_id=mentioned_conversation_id,
        clinic_id=clinic_id,
    )

    if _mention_exists(
        message_id=message.id,
        mention_type=mention_type,
        mentioned_user_id=mentioned_user_id,
        mentioned_patient_id=mentioned_patient_id,
        mentioned_conversation_id=mentioned_conversation_id,
    ):
        raise ConflictError(
            "This mention already exists for the message"
        )

    mention = MessageMention(
        clinic_id=clinic_id,
        message_id=message.id,
        mention_type=mention_type,
        mentioned_user_id=mentioned_user_id,
        mentioned_patient_id=mentioned_patient_id,
        mentioned_conversation_id=mentioned_conversation_id,
        position_start=position_start,
        position_end=position_end,
    )

    db.session.add(mention)
    db.session.flush()

    create_audit_log(
        action=AuditAction.CREATE,
        entity_type="MessageMention",
        entity_id=mention.id,
        description=(
            f"Mention created on message {message.id}"
        ),
        new_value={
            "clinic_id": clinic_id,
            "message_id": message.id,
            "mention_type": mention_type.value,
            "mentioned_user_id": mentioned_user_id,
            "mentioned_patient_id": mentioned_patient_id,
            "mentioned_conversation_id": (
                mentioned_conversation_id
            ),
            "position_start": position_start,
            "position_end": position_end,
        },
    )

    return mention


# ---------------------------------------------------------------------------
# Bulk Create Mentions
# ---------------------------------------------------------------------------


@transactional
def create_mentions(
    *,
    message_id: int,
    clinic_id: int,
    actor_user_id: int,
    mentions: list[dict],
) -> list[MessageMention]:
    _validate_positive_id(
        clinic_id,
        "Clinic ID",
    )

    _validate_positive_id(
        actor_user_id,
        "Actor user ID",
    )

    message = _get_message(
        message_id,
        clinic_id,
    )

    _ensure_actor_is_participant(
        message,
        actor_user_id,
    )

    if len(mentions) > MAX_MENTIONS_PER_MESSAGE:
        raise ValidationError(
            "A message cannot contain more than "
            f"{MAX_MENTIONS_PER_MESSAGE} mentions"
        )

    created_mentions: list[MessageMention] = []
    seen_targets: set[tuple] = set()

    for payload in mentions:
        mention_type = _normalize_mention_type(
            payload.get("mention_type")
        )

        mentioned_user_id = payload.get(
            "mentioned_user_id"
        )

        mentioned_patient_id = payload.get(
            "mentioned_patient_id"
        )

        mentioned_conversation_id = payload.get(
            "mentioned_conversation_id"
        )

        position_start = payload.get(
            "position_start"
        )

        position_end = payload.get(
            "position_end"
        )

        _validate_positions(
            position_start=position_start,
            position_end=position_end,
        )

        _validate_target(
            mention_type=mention_type,
            mentioned_user_id=mentioned_user_id,
            mentioned_patient_id=mentioned_patient_id,
            mentioned_conversation_id=mentioned_conversation_id,
            clinic_id=clinic_id,
        )

        target_key = (
            mention_type.value,
            mentioned_user_id,
            mentioned_patient_id,
            mentioned_conversation_id,
        )

        if target_key in seen_targets:
            raise ConflictError(
                "Duplicate mention target in request"
            )

        seen_targets.add(
            target_key
        )

        if _mention_exists(
            message_id=message.id,
            mention_type=mention_type,
            mentioned_user_id=mentioned_user_id,
            mentioned_patient_id=mentioned_patient_id,
            mentioned_conversation_id=mentioned_conversation_id,
        ):
            raise ConflictError(
                "A mention already exists for this message"
            )

        mention = MessageMention(
            clinic_id=clinic_id,
            message_id=message.id,
            mention_type=mention_type,
            mentioned_user_id=mentioned_user_id,
            mentioned_patient_id=mentioned_patient_id,
            mentioned_conversation_id=(
                mentioned_conversation_id
            ),
            position_start=position_start,
            position_end=position_end,
        )

        db.session.add(mention)
        created_mentions.append(
            mention
        )

    db.session.flush()

    for mention in created_mentions:
        create_audit_log(
            action=AuditAction.CREATE,
            entity_type="MessageMention",
            entity_id=mention.id,
            description=(
                f"Mention created on message {message.id}"
            ),
            new_value={
                "clinic_id": mention.clinic_id,
                "message_id": mention.message_id,
                "mention_type": mention.mention_type.value,
                "mentioned_user_id": (
                    mention.mentioned_user_id
                ),
                "mentioned_patient_id": (
                    mention.mentioned_patient_id
                ),
                "mentioned_conversation_id": (
                    mention.mentioned_conversation_id
                ),
            },
        )

    return created_mentions


# ---------------------------------------------------------------------------
# Delete Mention
# ---------------------------------------------------------------------------


@transactional
def delete_mention(
    *,
    mention_id: int,
    clinic_id: int,
    actor_user_id: int,
) -> None:
    _validate_positive_id(
        clinic_id,
        "Clinic ID",
    )

    _validate_positive_id(
        actor_user_id,
        "Actor user ID",
    )

    mention = _get_mention(
        mention_id,
        clinic_id,
    )

    message = _get_message(
        mention.message_id,
        clinic_id,
    )

    _ensure_actor_is_participant(
        message,
        actor_user_id,
    )

    create_audit_log(
        action=AuditAction.DELETE,
        entity_type="MessageMention",
        entity_id=mention.id,
        description=(
            f"Mention {mention.id} removed from "
            f"message {message.id}"
        ),
        old_value={
            "clinic_id": mention.clinic_id,
            "message_id": mention.message_id,
            "mention_type": mention.mention_type.value,
            "mentioned_user_id": (
                mention.mentioned_user_id
            ),
            "mentioned_patient_id": (
                mention.mentioned_patient_id
            ),
            "mentioned_conversation_id": (
                mention.mentioned_conversation_id
            ),
        },
    )

    db.session.delete(
        mention
    )