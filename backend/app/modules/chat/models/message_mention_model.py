from datetime import datetime, timezone

from app.extensions import db
from app.core.enums.chat_enums import MentionType


def _utcnow():
    return datetime.now(timezone.utc)


class MessageMention(db.Model):
    __tablename__ = "chat_message_mentions"

    __table_args__ = (
        db.CheckConstraint(
            """
            (
                mention_type IN ('user', 'staff')
                AND mentioned_user_id IS NOT NULL
                AND mentioned_patient_id IS NULL
                AND mentioned_conversation_id IS NULL
            )
            OR
            (
                mention_type = 'patient'
                AND mentioned_user_id IS NULL
                AND mentioned_patient_id IS NOT NULL
                AND mentioned_conversation_id IS NULL
            )
            OR
            (
                mention_type = 'group'
                AND mentioned_user_id IS NULL
                AND mentioned_patient_id IS NULL
                AND mentioned_conversation_id IS NOT NULL
            )
            """,
            name="ck_chat_message_mentions_target",
        ),
        db.UniqueConstraint(
            "message_id",
            "mention_type",
            "mentioned_user_id",
            "mentioned_patient_id",
            "mentioned_conversation_id",
            name="uq_chat_message_mentions_target",
        ),
        db.Index(
            "ix_chat_message_mentions_message",
            "message_id",
            "id",
        ),
        db.Index(
            "ix_chat_message_mentions_user",
            "mentioned_user_id",
            "created_at",
            "id",
        ),
        db.Index(
            "ix_chat_message_mentions_patient",
            "mentioned_patient_id",
            "created_at",
            "id",
        ),
        db.Index(
            "ix_chat_message_mentions_conversation",
            "mentioned_conversation_id",
            "created_at",
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

    message_id = db.Column(
        db.Integer,
        db.ForeignKey("chat_messages.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    mention_type = db.Column(
        db.Enum(
            MentionType,
            name="chat_mention_type_enum",
            native_enum=True,
            validate_strings=True,
            values_callable=lambda enum_cls: [
                member.value for member in enum_cls
            ],
        ),
        nullable=False,
        index=True,
    )

    mentioned_user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=True,
        index=True,
    )

    mentioned_patient_id = db.Column(
        db.Integer,
        db.ForeignKey("patients.id"),
        nullable=True,
        index=True,
    )

    mentioned_conversation_id = db.Column(
        db.Integer,
        db.ForeignKey("chat_conversations.id"),
        nullable=True,
        index=True,
    )

    position_start = db.Column(
        db.Integer,
        nullable=True,
    )

    position_end = db.Column(
        db.Integer,
        nullable=True,
    )

    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
        index=True,
    )

    message = db.relationship(
        "Message",
        back_populates="mentions",
    )

    mentioned_user = db.relationship(
        "User",
        foreign_keys=[mentioned_user_id],
    )

    mentioned_patient = db.relationship(
        "Patient",
        foreign_keys=[mentioned_patient_id],
    )

    mentioned_conversation = db.relationship(
        "Conversation",
        foreign_keys=[mentioned_conversation_id],
    )

    def __repr__(self):
        return (
            f"<MessageMention "
            f"id={self.id} "
            f"message_id={self.message_id} "
            f"type={self.mention_type.value}>"
        )