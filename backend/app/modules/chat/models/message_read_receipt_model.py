from datetime import datetime, timezone

from app.extensions import db
from app.core.enums.chat_enums import ReadReceiptStatus


def _utcnow():
    return datetime.now(timezone.utc)


class MessageReadReceipt(db.Model):
    __tablename__ = "chat_message_read_receipts"

    __table_args__ = (
        db.UniqueConstraint(
            "message_id",
            "user_id",
            name="uq_chat_message_read_receipts_message_user",
        ),
        db.Index(
            "ix_chat_message_read_receipts_message_status",
            "message_id",
            "status",
        ),
        db.Index(
            "ix_chat_message_read_receipts_user_status",
            "user_id",
            "status",
        ),
        db.Index(
            "ix_chat_message_read_receipts_clinic_created",
            "clinic_id",
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

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    status = db.Column(
        db.Enum(
            ReadReceiptStatus,
            name="chat_read_receipt_status_enum",
            native_enum=True,
            validate_strings=True,
            values_callable=lambda enum_cls: [
                member.value for member in enum_cls
            ],
        ),
        nullable=False,
        default=ReadReceiptStatus.DELIVERED,
        index=True,
    )

    delivered_at = db.Column(
        db.DateTime(timezone=True),
        nullable=True,
    )

    read_at = db.Column(
        db.DateTime(timezone=True),
        nullable=True,
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

    message = db.relationship(
        "Message",
        back_populates="read_receipts",
    )

    user = db.relationship(
        "User",
        foreign_keys=[user_id],
        lazy="joined",
    )

    def __repr__(self):
        return (
            f"<MessageReadReceipt "
            f"id={self.id} "
            f"message_id={self.message_id} "
            f"user_id={self.user_id} "
            f"status={self.status.value}>"
        )