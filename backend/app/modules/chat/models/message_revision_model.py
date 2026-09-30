from datetime import datetime, timezone

from app.extensions import db


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class MessageRevision(db.Model):
    __tablename__ = "chat_message_revisions"

    id = db.Column(
        db.Integer,
        primary_key=True,
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
        nullable=False,
        index=True,
    )

    edited_by_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "users.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
        index=True,
    )

    revision_number = db.Column(
        db.Integer,
        nullable=False,
    )

    previous_content = db.Column(
        db.Text,
        nullable=True,
    )

    previous_message_type = db.Column(
        db.String(32),
        nullable=False,
    )

    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
    )

    clinic = db.relationship(
        "Clinic",
        backref=db.backref(
            "chat_message_revisions",
            lazy="dynamic",
        ),
    )

    message = db.relationship(
        "Message",
        back_populates="revisions",
    )

    edited_by = db.relationship(
        "User",
        backref=db.backref(
            "chat_message_revisions",
            lazy="dynamic",
        ),
    )

    __table_args__ = (
        db.UniqueConstraint(
            "message_id",
            "revision_number",
            name="uq_chat_message_revision_number",
        ),
        db.Index(
            "ix_chat_message_revisions_message_created",
            "message_id",
            "created_at",
            "id",
        ),
        db.Index(
            "ix_chat_message_revisions_clinic_created",
            "clinic_id",
            "created_at",
            "id",
        ),
        db.Index(
            "ix_chat_message_revisions_editor_created",
            "edited_by_id",
            "created_at",
            "id",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<MessageRevision "
            f"id={self.id} "
            f"message_id={self.message_id} "
            f"revision_number={self.revision_number}>"
        )