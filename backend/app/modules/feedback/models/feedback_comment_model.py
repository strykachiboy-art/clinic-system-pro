from datetime import datetime, timezone

from app.extensions import db


def _utcnow():
    return datetime.now(timezone.utc)


class FeedbackComment(db.Model):
    __tablename__ = "feedback_comments"

    __table_args__ = (
        db.Index(
            "ix_feedback_comments_feedback_created_id",
            "feedback_id",
            "created_at",
            "id",
        ),
        db.Index(
            "ix_feedback_comments_author_created_id",
            "author_user_id",
            "created_at",
            "id",
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

    author_user_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "users.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
        index=True,
    )

    body = db.Column(
        db.Text,
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

    feedback = db.relationship(
        "Feedback",
        back_populates="comments",
    )

    author = db.relationship(
        "User",
        foreign_keys=[author_user_id],
    )

    def __repr__(self):
        return (
            f"<FeedbackComment id={self.id} "
            f"feedback_id={self.feedback_id}>"
        )