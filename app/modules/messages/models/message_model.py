from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    CheckConstraint,
    Index,
)

from app.core.enums.message_enums import (
    MessagePriority,
    MessageStatus,
    MessageType,
)
from app.extensions import db


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Message(db.Model):
    __tablename__ = "messages"

    __table_args__ = (
        CheckConstraint(
            "sender_id <> recipient_id",
            name="ck_messages_sender_recipient_different",
        ),
        Index(
            "ix_messages_clinic_recipient_deleted_created",
            "clinic_id",
            "recipient_id",
            "deleted_at",
            "created_at",
            "id",
        ),
        Index(
            "ix_messages_clinic_sender_deleted_created",
            "clinic_id",
            "sender_id",
            "deleted_at",
            "created_at",
            "id",
        ),
        Index(
            "ix_messages_clinic_parent_deleted_created",
            "clinic_id",
            "parent_message_id",
            "deleted_at",
            "created_at",
            "id",
        ),
        Index(
            "ix_messages_clinic_status_created",
            "clinic_id",
            "status",
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

    sender_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=False,
        index=True,
    )

    recipient_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=False,
        index=True,
    )

    subject = db.Column(
        db.String(255),
        nullable=False,
    )

    body = db.Column(
        db.Text,
        nullable=False,
    )

    message_type = db.Column(
        db.Enum(MessageType),
        nullable=False,
        default=MessageType.DIRECT,
        index=True,
    )

    status = db.Column(
        db.Enum(MessageStatus),
        nullable=False,
        default=MessageStatus.SENT,
        index=True,
    )

    priority = db.Column(
        db.Enum(MessagePriority),
        nullable=False,
        default=MessagePriority.NORMAL,
        index=True,
    )

    parent_message_id = db.Column(
        db.Integer,
        db.ForeignKey("messages.id"),
        nullable=True,
        index=True,
    )

    sent_at = db.Column(
        db.DateTime(timezone=True),
        nullable=True,
        index=True,
    )

    read_at = db.Column(
        db.DateTime(timezone=True),
        nullable=True,
        index=True,
    )

    deleted_at = db.Column(
        db.DateTime(timezone=True),
        nullable=True,
        index=True,
    )

    created_at = db.Column(
        db.DateTime(timezone=True),
        default=_utcnow,
        nullable=False,
        index=True,
    )

    updated_at = db.Column(
        db.DateTime(timezone=True),
        default=_utcnow,
        onupdate=_utcnow,
        nullable=False,
    )

    clinic = db.relationship(
        "Clinic",
        back_populates="messages",
    )

    sender = db.relationship(
        "User",
        foreign_keys=[sender_id],
        back_populates="sent_messages",
    )

    recipient = db.relationship(
        "User",
        foreign_keys=[recipient_id],
        back_populates="received_messages",
    )

    parent_message = db.relationship(
        "Message",
        remote_side=[id],
        foreign_keys=[parent_message_id],
        back_populates="replies",
    )

    replies = db.relationship(
        "Message",
        foreign_keys=[parent_message_id],
        back_populates="parent_message",
        cascade="save-update, merge",
    )

    def __repr__(self) -> str:
        return (
            f"<Message "
            f"id={self.id} "
            f"clinic_id={self.clinic_id} "
            f"sender_id={self.sender_id} "
            f"recipient_id={self.recipient_id} "
            f"status={self.status.value}>"
        )