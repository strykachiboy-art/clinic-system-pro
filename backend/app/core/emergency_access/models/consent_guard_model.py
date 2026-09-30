from __future__ import annotations

from datetime import datetime, timezone

from app.core.enums.emergency_access_enums import (
    ConsentGuardDecision,
)
from app.extensions import db


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ConsentGuardEvaluation(db.Model):
    __tablename__ = "consent_guard_evaluations"

    __table_args__ = (
        db.Index(
            "ix_consent_guard_clinic_patient",
            "clinic_id",
            "patient_id",
        ),
        db.Index(
            "ix_consent_guard_requester_created",
            "requester_user_id",
            "created_at",
        ),
        db.Index(
            "ix_consent_guard_emergency_access",
            "emergency_access_id",
        ),
    )

    id = db.Column(
        db.Integer,
        primary_key=True,
    )

    emergency_access_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "emergency_access_grants.id",
        ),
        nullable=True,
        index=True,
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

    recipient_role = db.Column(
        db.String(50),
        nullable=False,
    )

    purpose = db.Column(
        db.String(255),
        nullable=False,
    )

    decision = db.Column(
        db.Enum(ConsentGuardDecision),
        nullable=False,
        index=True,
    )

    consent_reference = db.Column(
        db.String(255),
        nullable=True,
    )

    policy_context = db.Column(
        db.JSON,
        nullable=True,
    )

    emergency_exception = db.Column(
        db.Boolean,
        nullable=False,
        default=False,
    )

    effective_from = db.Column(
        db.DateTime(timezone=True),
        nullable=True,
    )

    effective_until = db.Column(
        db.DateTime(timezone=True),
        nullable=True,
    )

    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
        index=True,
    )

    def __repr__(self) -> str:
        return (
            f"<ConsentGuardEvaluation "
            f"id={self.id} "
            f"patient_id={self.patient_id} "
            f"decision={self.decision.value}>"
        )