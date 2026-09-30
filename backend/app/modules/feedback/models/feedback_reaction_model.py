from datetime import datetime, timezone

from app.extensions import db
from app.core.enums.feedback_reaction_enums import FeedbackReactionType


def _utcnow():
    return datetime.now(timezone.utc)


class FeedbackReaction(db.Model):
    __tablename__ = "feedback_reactions"

    __table_args__ = (
        db.UniqueConstraint(
            "feedback_id",
            "user_id",
            name="uq_feedback_reactions_feedback_user",
        ),
        db.Index(
            "ix_feedback_reactions_feedback_type",
            "feedback_id",
            "reaction_type",
        ),
        db.Index(
            "ix_feedback_reactions_user_created",
            "user_id",
            "created_at",
        ),
    )

    id = db.Column(
        db.Integer,
        primary_key=True,
    )

    feedback_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "feedback.id",
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

    reaction_type = db.Column(
        db.Enum(
            FeedbackReactionType,
            name="feedback_reaction_type_enum",
            native_enum=True,
            validate_strings=True,
            values_callable=lambda enum_cls: [
                member.value for member in enum_cls
            ],
        ),
        nullable=False,
        index=True,
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

    feedback = db.relationship(
        "Feedback",
        back_populates="reactions",
    )

    user = db.relationship(
        "User",
        foreign_keys=[user_id],
    )

    def __repr__(self):
        return (
            f"<FeedbackReaction id={self.id} "
            f"feedback_id={self.feedback_id} "
            f"user_id={self.user_id} "
            f"type={self.reaction_type.value}>"
        )