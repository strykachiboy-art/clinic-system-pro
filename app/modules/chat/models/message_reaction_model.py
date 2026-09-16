from datetime import datetime, timezone

from app.extensions import db


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class MessageReaction(db.Model):
    __tablename__ = "chat_message_reactions"

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

    user_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "users.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
        index=True,
    )

    reaction = db.Column(
        db.String(32),
        nullable=False,
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
            "chat_message_reactions",
            lazy="dynamic",
        ),
    )

    message = db.relationship(
        "Message",
        back_populates="reactions",
    )

    user = db.relationship(
        "User",
        backref=db.backref(
            "chat_message_reactions",
            lazy="dynamic",
        ),
    )

    __table_args__ = (
        db.UniqueConstraint(
            "message_id",
            "user_id",
            "reaction",
            name="uq_chat_message_reaction_user",
        ),
        db.Index(
            "ix_chat_message_reactions_message_reaction",
            "message_id",
            "reaction",
        ),
        db.Index(
            "ix_chat_message_reactions_clinic_created",
            "clinic_id",
            "created_at",
            "id",
        ),
        db.Index(
            "ix_chat_message_reactions_user_created",
            "user_id",
            "created_at",
            "id",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<MessageReaction "
            f"id={self.id} "
            f"message_id={self.message_id} "
            f"user_id={self.user_id} "
            f"reaction={self.reaction!r}>"
        )