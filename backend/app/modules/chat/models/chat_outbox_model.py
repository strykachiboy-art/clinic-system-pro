from datetime import datetime, timezone

from app.extensions import db


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ChatOutbox(db.Model):
    __tablename__ = "chat_outbox"

    id = db.Column(
        db.BigInteger().with_variant(
            db.Integer,
            "sqlite",
        ),
        primary_key=True,
        autoincrement=True,
    )

    clinic_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "clinics.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    message_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "chat_messages.id",
            ondelete="CASCADE",
        ),
        nullable=True,
        index=True,
    )

    event_type = db.Column(
        db.String(64),
        nullable=False,
    )

    payload = db.Column(
        db.JSON,
        nullable=False,
    )

    status = db.Column(
        db.String(32),
        nullable=False,
        default="pending",
        index=True,
    )

    attempts = db.Column(
        db.Integer,
        nullable=False,
        default=0,
    )

    available_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
        index=True,
    )

    processed_at = db.Column(
        db.DateTime(timezone=True),
        nullable=True,
    )

    last_error = db.Column(
        db.Text,
        nullable=True,
    )

    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
    )

    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
        onupdate=_utcnow,
    )

    clinic = db.relationship(
        "Clinic",
        backref=db.backref(
            "chat_outbox_events",
            lazy="dynamic",
        ),
    )

    message = db.relationship(
        "Message",
        backref=db.backref(
            "outbox_events",
            lazy="dynamic",
        ),
    )

    __table_args__ = (
        db.Index(
            "ix_chat_outbox_pending_available",
            "status",
            "available_at",
            "id",
        ),
        db.Index(
            "ix_chat_outbox_clinic_created",
            "clinic_id",
            "created_at",
            "id",
        ),
        db.Index(
            "ix_chat_outbox_message_created",
            "message_id",
            "created_at",
            "id",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<ChatOutbox "
            f"id={self.id} "
            f"event_type={self.event_type!r} "
            f"status={self.status!r}>"
        )