from datetime import datetime, timezone

from app.extensions import db
from app.core.enums.chat_enums import (
    ParticipantRole,
    ParticipantStatus,
)


def _utcnow():
    return datetime.now(timezone.utc)


class ConversationParticipant(db.Model):
    __tablename__ = "chat_conversation_participants"

    __table_args__ = (
        db.UniqueConstraint(
            "conversation_id",
            "user_id",
            name="uq_chat_conversation_participants_conversation_user",
        ),
        db.Index(
            "ix_chat_participants_conversation_status",
            "conversation_id",
            "status",
            "id",
        ),
        db.Index(
            "ix_chat_participants_user_status",
            "user_id",
            "status",
            "id",
        ),
        db.Index(
            "ix_chat_participants_clinic_user",
            "clinic_id",
            "user_id",
            "status",
            "id",
        ),
    )

    id = db.Column(
        db.Integer,
        primary_key=True,
    )

    clinic_id = db.Column(
        db.Integer,
        db.ForeignKey("clinics.id"),
        nullable=False,
        index=True,
    )

    conversation_id = db.Column(
        db.Integer,
        db.ForeignKey("chat_conversations.id"),
        nullable=False,
        index=True,
    )

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=False,
        index=True,
    )

    role = db.Column(
        db.Enum(ParticipantRole),
        nullable=False,
        default=ParticipantRole.MEMBER,
    )

    status = db.Column(
        db.Enum(ParticipantStatus),
        nullable=False,
        default=ParticipantStatus.PENDING,
        index=True,
    )

    joined_at = db.Column(
        db.DateTime(timezone=True),
        nullable=True,
    )

    left_at = db.Column(
        db.DateTime(timezone=True),
        nullable=True,
    )

    removed_at = db.Column(
        db.DateTime(timezone=True),
        nullable=True,
    )

    last_read_message_id = db.Column(
        db.Integer,
        db.ForeignKey("chat_messages.id"),
        nullable=True,
        index=True,
    )

    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
        index=True,
    )

    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
        onupdate=_utcnow,
        index=True,
    )

    def __repr__(self):
        return (
            f"<ConversationParticipant "
            f"id={self.id} "
            f"conversation_id={self.conversation_id} "
            f"user_id={self.user_id} "
            f"status={self.status.value}>"
        )