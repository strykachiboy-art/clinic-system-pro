from datetime import datetime, timezone

from app.extensions import db
from app.core.enums.chat_enums import MessagePriority, MessageStatus


def _utcnow():
    return datetime.now(timezone.utc)


class Message(db.Model):
    __tablename__ = "chat_messages"

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
        db.ForeignKey("chat_conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    sender_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    content = db.Column(
        db.Text,
        nullable=True,
    )

    status = db.Column(
        db.Enum(
            MessageStatus,
            name="chat_message_status_enum",
            native_enum=True,
            validate_strings=True,
        ),
        nullable=False,
        default=MessageStatus.PENDING,
        index=True,
    )

    priority = db.Column(
        db.Enum(
            MessagePriority,
            name="chat_message_priority_enum",
            native_enum=True,
            validate_strings=True,
        ),
        nullable=False,
        default=MessagePriority.NORMAL,
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
    )

    edited_at = db.Column(
        db.DateTime(timezone=True),
        nullable=True,
    )

    deleted_at = db.Column(
        db.DateTime(timezone=True),
        nullable=True,
    )

    conversation = db.relationship(
        "Conversation",
        back_populates="messages",
    )

    sender = db.relationship(
        "User",
        foreign_keys=[sender_id],
        lazy="joined",
    )

    attachments = db.relationship(
        "MessageAttachment",
        back_populates="message",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    mentions = db.relationship(
        "MessageMention",
        back_populates="message",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    pins = db.relationship(
        "MessagePin",
        back_populates="message",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    read_receipts = db.relationship(
        "MessageReadReceipt",
        back_populates="message",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __table_args__ = (
        db.Index(
            "ix_chat_messages_conversation_created_id",
            "conversation_id",
            "created_at",
            "id",
        ),
        db.Index(
            "ix_chat_messages_clinic_created_id",
            "clinic_id",
            "created_at",
            "id",
        ),
    )

    def __repr__(self):
        return (
            f"<Message "
            f"id={self.id} "
            f"conversation_id={self.conversation_id} "
            f"sender_id={self.sender_id} "
            f"status={self.status.value}>"
        )