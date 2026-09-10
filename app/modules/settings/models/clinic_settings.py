from __future__ import annotations

from datetime import datetime, timezone

from app.extensions import db


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ClinicSettings(db.Model):
    """
    Clinic-specific application settings.

    This model stores configurable preferences that are not core
    identity/operational fields of the Clinic model.

    One Clinic has exactly one ClinicSettings record.
    """

    __tablename__ = "clinic_settings"

    __table_args__ = (
        db.CheckConstraint(
            "version >= 1",
            name="ck_clinic_settings_version_positive",
        ),
    )

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
        unique=True,
        index=True,
    )

    # ---------------------------------------------------------
    # General application preferences
    # ---------------------------------------------------------

    language = db.Column(
        db.String(20),
        nullable=False,
        default="en",
    )

    date_format = db.Column(
        db.String(30),
        nullable=False,
        default="YYYY-MM-DD",
    )

    time_format = db.Column(
        db.String(10),
        nullable=False,
        default="24h",
    )

    # ---------------------------------------------------------
    # Notification preferences
    # ---------------------------------------------------------

    notification_preferences = db.Column(
        db.JSON,
        nullable=False,
        default=dict,
    )

    # ---------------------------------------------------------
    # Feature configuration / feature flags
    # ---------------------------------------------------------

    feature_flags = db.Column(
        db.JSON,
        nullable=False,
        default=dict,
    )

    # ---------------------------------------------------------
    # Operational preferences
    # ---------------------------------------------------------

    operational_preferences = db.Column(
        db.JSON,
        nullable=False,
        default=dict,
    )

    # ---------------------------------------------------------
    # Security preferences
    # ---------------------------------------------------------

    security_preferences = db.Column(
        db.JSON,
        nullable=False,
        default=dict,
    )

    # ---------------------------------------------------------
    # System preferences
    # ---------------------------------------------------------

    system_preferences = db.Column(
        db.JSON,
        nullable=False,
        default=dict,
    )

    # ---------------------------------------------------------
    # Lifecycle / concurrency
    # ---------------------------------------------------------

    is_enabled = db.Column(
        db.Boolean,
        nullable=False,
        default=True,
    )

    version = db.Column(
        db.Integer,
        nullable=False,
        default=1,
    )

    created_at = db.Column(
        db.DateTime,
        nullable=False,
        default=_utcnow,
    )

    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=_utcnow,
        onupdate=_utcnow,
    )

    # ---------------------------------------------------------
    # Relationships
    # ---------------------------------------------------------

    clinic = db.relationship(
        "Clinic",
        back_populates="settings",
    )

    def __repr__(self) -> str:
        return (
            f"<ClinicSettings "
            f"clinic_id={self.clinic_id} "
            f"version={self.version}>"
        )