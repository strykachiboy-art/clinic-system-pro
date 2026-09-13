from datetime import datetime, timezone

from app.extensions import db
from app.core.enums.chat_enums import PinStatus


def _utcnow():
    return datetime.now(timezone.utc)


class MessagePin(db.Model):
    __tablename__ = "chat_message_pins"

    __table_args__ = (
        db.Index(
            "ix_chat_message_pins_message_status",
            "message_id",
            "status",
        ),
        db.Index(
            "ix_chat_message_pins_status_expires",
            "status",
            "expires_at",
            "id",
        ),
        db.Index(
            "ix_chat_message_pins_clinic_created",
            "clinic_id",
            "pinned_at",
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

    pinned_by_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    status = db.Column(
        db.Enum(
            PinStatus,
            name="chat_pin_status_enum",
            native_enum=True,
            validate_strings=True,
        ),
        nullable=False,
        default=PinStatus.PINNED,
        index=True,
    )

    pinned_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
        index=True,
    )

    expires_at = db.Column(
        db.DateTime(timezone=True),
        nullable=True,
        index=True,
    )

    unpinned_at = db.Column(
        db.DateTime(timezone=True),
        nullable=True,
    )

    message = db.relationship(
        "Message",
        back_populates="pins",
    )

    pinned_by = db.relationship(
        "User",
        foreign_keys=[pinned_by_id],
        lazy="joined",
    )

    def __repr__(self):
        return (
            f"<MessagePin "
            f"id={self.id} "
            f"message_id={self.message_id} "
            f"status={self.status.value}>"
        )