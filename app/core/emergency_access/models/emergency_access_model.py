from __future__ import annotations

from datetime import datetime, timezone

from app.core.enums.emergency_access_enums import (
    EmergencyAccessStatus,
)
from app.extensions import db


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class EmergencyAccessGrant(db.Model):
    __tablename__ = "emergency_access_grants"

    __table_args__ = (
        db.Index(
            "ix_emergency_access_clinic_patient_status",
            "clinic_id",
            "patient_id",
            "status",
        ),
        db.Index(
            "ix_emergency_access_requester_status",
            "requester_user_id",
            "status",
        ),
        db.Index(
            "ix_emergency_access_expires_at",
            "expires_at",
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

    patient_id = db.Column(
        db.Integer,
        db.ForeignKey("patients.id"),
        nullable=False,
        index=True,
    )

    requester_user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=False,
        index=True,
    )

    requester_role = db.Column(
        db.String(50),
        nullable=False,
    )

    reason = db.Column(
        db.String(500),
        nullable=False,
    )

    purpose = db.Column(
        db.String(255),
        nullable=False,
    )

    scope = db.Column(
        db.JSON,
        nullable=False,
    )

    status = db.Column(
        db.Enum(EmergencyAccessStatus),
        nullable=False,
        default=EmergencyAccessStatus.REQUESTED,
        index=True,
    )

    requested_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
        index=True,
    )

    granted_at = db.Column(
        db.DateTime(timezone=True),
        nullable=True,
    )

    expires_at = db.Column(
        db.DateTime(timezone=True),
        nullable=True,
        index=True,
    )

    revoked_at = db.Column(
        db.DateTime(timezone=True),
        nullable=True,
    )

    reviewed_at = db.Column(
        db.DateTime(timezone=True),
        nullable=True,
    )

    reviewed_by_user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=True,
        index=True,
    )

    review_notes = db.Column(
        db.String(1000),
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

    def __repr__(self) -> str:
        return (
            f"<EmergencyAccessGrant "
            f"id={self.id} "
            f"patient_id={self.patient_id} "
            f"requester_user_id={self.requester_user_id} "
            f"status={self.status.value}>"
        )