from __future__ import annotations

from datetime import datetime, timezone

from app.core.enums.notification_enums import (
    NotificationChannel,
    NotificationPriority,
    NotificationStatus,
    NotificationType,
)
from app.extensions import db


def _utcnow() -> datetime:
    """
    Return the current UTC time as a timezone-aware datetime.
    """
    return datetime.now(timezone.utc)


class Notification(db.Model):
    __tablename__ = "notifications"

    id = db.Column(
        db.Integer,
        primary_key=True,
    )

    # ==================================================================
    # TENANCY
    # ==================================================================

    clinic_id = db.Column(
        db.Integer,
        db.ForeignKey("clinics.id"),
        nullable=False,
        index=True,
    )

    # ==================================================================
    # RECIPIENT
    # ==================================================================

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=False,
        index=True,
    )

    # ==================================================================
    # NOTIFICATION CONTENT
    # ==================================================================

    title = db.Column(
        db.String(255),
        nullable=False,
    )

    message = db.Column(
        db.Text,
        nullable=False,
    )

    # ==================================================================
    # CLASSIFICATION
    # ==================================================================

    notification_type = db.Column(
        db.Enum(NotificationType),
        nullable=False,
        index=True,
    )

    priority = db.Column(
        db.Enum(NotificationPriority),
        nullable=False,
        default=NotificationPriority.NORMAL,
        index=True,
    )

    channel = db.Column(
        db.Enum(NotificationChannel),
        nullable=False,
        default=NotificationChannel.IN_APP,
        index=True,
    )

    status = db.Column(
        db.Enum(NotificationStatus),
        nullable=False,
        default=NotificationStatus.PENDING,
        index=True,
    )

    # ==================================================================
    # OPTIONAL SOURCE REFERENCE
    # ==================================================================

    reference_type = db.Column(
        db.String(50),
        nullable=True,
        index=True,
    )

    reference_id = db.Column(
        db.Integer,
        nullable=True,
        index=True,
    )

    # ==================================================================
    # READ STATE
    # ==================================================================

    is_read = db.Column(
        db.Boolean,
        nullable=False,
        default=False,
        index=True,
    )

    read_at = db.Column(
        db.DateTime(timezone=True),
        nullable=True,
        index=True,
    )

    # ==================================================================
    # DELIVERY STATE
    # ==================================================================

    sent_at = db.Column(
        db.DateTime(timezone=True),
        nullable=True,
        index=True,
    )

    delivered_at = db.Column(
        db.DateTime(timezone=True),
        nullable=True,
        index=True,
    )

    failed_at = db.Column(
        db.DateTime(timezone=True),
        nullable=True,
        index=True,
    )

    error_message = db.Column(
        db.Text,
        nullable=True,
    )

    retry_count = db.Column(
        db.Integer,
        nullable=False,
        default=0,
    )

    # ==================================================================
    # AUDIT TIMESTAMPS
    # ==================================================================

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

    # ==================================================================
    # RELATIONSHIPS
    # ==================================================================

    clinic = db.relationship(
        "Clinic",
        back_populates="notifications",
    )

    user = db.relationship(
        "User",
        back_populates="notifications",
    )

    # ==================================================================
    # REPRESENTATION
    # ==================================================================

    def __repr__(self) -> str:
        return (
            f"<Notification "
            f"id={self.id} "
            f"clinic_id={self.clinic_id} "
            f"user_id={self.user_id} "
            f"type={self.notification_type.value} "
            f"status={self.status.value}>"
        )