from datetime import datetime, timezone

from app.extensions import db
from app.core.enums.feedback_enums import (
    FeedbackCategory,
    FeedbackPriority,
    FeedbackSource,
    FeedbackStatus,
    FeedbackType,
)


def _utcnow():
    return datetime.now(timezone.utc)


class Feedback(db.Model):
    __tablename__ = "feedback"

    __table_args__ = (
        db.CheckConstraint(
            "length(trim(subject)) > 0",
            name="ck_feedback_subject_not_blank",
        ),
        db.CheckConstraint(
            "length(trim(message)) > 0",
            name="ck_feedback_message_not_blank",
        ),
        db.CheckConstraint(
            """
            (
                target_module IS NULL
                AND target_resource_type IS NULL
                AND target_resource_id IS NULL
            )
            OR
            (
                target_module IS NOT NULL
                AND target_resource_type IS NOT NULL
                AND target_resource_id IS NOT NULL
                AND target_resource_id > 0
            )
            """,
            name="ck_feedback_target_fields_consistent",
        ),
        db.Index(
            "ix_feedback_clinic_status_created_id",
            "clinic_id",
            "status",
            "created_at",
            "id",
        ),
        db.Index(
            "ix_feedback_clinic_created_id",
            "clinic_id",
            "created_at",
            "id",
        ),
        db.Index(
            "ix_feedback_clinic_priority_created_id",
            "clinic_id",
            "priority",
            "created_at",
            "id",
        ),
        db.Index(
            "ix_feedback_clinic_type_created_id",
            "clinic_id",
            "feedback_type",
            "created_at",
            "id",
        ),
        db.Index(
            "ix_feedback_clinic_category_created_id",
            "clinic_id",
            "category",
            "created_at",
            "id",
        ),
        db.Index(
            "ix_feedback_assigned_status_created_id",
            "assigned_to_user_id",
            "status",
            "created_at",
            "id",
        ),
        db.Index(
            "ix_feedback_submitted_created_id",
            "submitted_by_user_id",
            "created_at",
            "id",
        ),
        db.Index(
            "ix_feedback_target_resource",
            "target_module",
            "target_resource_id",
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

    submitted_by_user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=False,
        index=True,
    )

    feedback_type = db.Column(
        db.Enum(
            FeedbackType,
            name="feedback_type_enum",
            native_enum=True,
            validate_strings=True,
            values_callable=lambda enum_cls: [
                member.value for member in enum_cls
            ],
        ),
        nullable=False,
        index=True,
    )

    category = db.Column(
        db.Enum(
            FeedbackCategory,
            name="feedback_category_enum",
            native_enum=True,
            validate_strings=True,
            values_callable=lambda enum_cls: [
                member.value for member in enum_cls
            ],
        ),
        nullable=False,
        index=True,
    )

    subject = db.Column(
        db.String(200),
        nullable=False,
    )

    message = db.Column(
        db.Text,
        nullable=False,
    )

    status = db.Column(
        db.Enum(
            FeedbackStatus,
            name="feedback_status_enum",
            native_enum=True,
            validate_strings=True,
            values_callable=lambda enum_cls: [
                member.value for member in enum_cls
            ],
        ),
        nullable=False,
        default=FeedbackStatus.OPEN,
        index=True,
    )

    priority = db.Column(
        db.Enum(
            FeedbackPriority,
            name="feedback_priority_enum",
            native_enum=True,
            validate_strings=True,
            values_callable=lambda enum_cls: [
                member.value for member in enum_cls
            ],
        ),
        nullable=False,
        default=FeedbackPriority.NORMAL,
        index=True,
    )

    source = db.Column(
        db.Enum(
            FeedbackSource,
            name="feedback_source_enum",
            native_enum=True,
            validate_strings=True,
            values_callable=lambda enum_cls: [
                member.value for member in enum_cls
            ],
        ),
        nullable=False,
        index=True,
    )

    target_module = db.Column(
        db.String(100),
        nullable=True,
    )

    target_resource_type = db.Column(
        db.String(100),
        nullable=True,
    )

    target_resource_id = db.Column(
        db.Integer,
        nullable=True,
        index=True,
    )

    assigned_to_user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=True,
        index=True,
    )

    resolution_note = db.Column(
        db.Text,
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

    resolved_at = db.Column(
        db.DateTime(timezone=True),
        nullable=True,
        index=True,
    )

    closed_at = db.Column(
        db.DateTime(timezone=True),
        nullable=True,
        index=True,
    )

    clinic = db.relationship(
        "Clinic",
        back_populates="feedback_items",
    )

    submitted_by = db.relationship(
        "User",
        foreign_keys=[submitted_by_user_id],
    )

    assigned_to = db.relationship(
        "User",
        foreign_keys=[assigned_to_user_id],
    )

    comments = db.relationship(
        "FeedbackComment",
        back_populates="feedback",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="FeedbackComment.created_at",
    )
    
    reactions = db.relationship(
        "FeedbackReaction",
        back_populates="feedback",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def __repr__(self):
        return (
            f"<Feedback id={self.id} "
            f"clinic_id={self.clinic_id} "
            f"status={self.status.value if self.status else None}>"
        )