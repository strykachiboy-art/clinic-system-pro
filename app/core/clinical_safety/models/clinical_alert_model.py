from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, Index

from app.core.enums.clinical_safety_enums import (
    ClinicalAlertStatus,
    ClinicalRuleAction,
    ClinicalRuleSeverity,
)
from app.extensions import db


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ClinicalAlert(db.Model):
    __tablename__ = "clinical_alerts"

    __table_args__ = (
        CheckConstraint(
            "rule_version > 0",
            name="ck_clinical_alerts_rule_version_positive",
        ),
        CheckConstraint(
            "source_id IS NULL OR source_id > 0",
            name="ck_clinical_alerts_source_id_positive",
        ),
        Index(
            "ix_clinical_alerts_clinic_patient_status",
            "clinic_id",
            "patient_id",
            "status",
            "generated_at",
            "id",
        ),
        Index(
            "ix_clinical_alerts_rule_version",
            "rule_id",
            "rule_version",
            "generated_at",
            "id",
        ),
        Index(
            "ix_clinical_alerts_source",
            "source_type",
            "source_id",
            "generated_at",
            "id",
        ),
        Index(
            "ix_clinical_alerts_clinic_status_generated",
            "clinic_id",
            "status",
            "generated_at",
            "id",
        ),
        Index(
            "ix_clinical_alerts_deduplication_key",
            "deduplication_key",
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

    rule_id = db.Column(
        db.Integer,
        db.ForeignKey("clinical_rules.id"),
        nullable=False,
        index=True,
    )

    rule_version = db.Column(
        db.Integer,
        nullable=False,
    )

    severity = db.Column(
        db.Enum(ClinicalRuleSeverity),
        nullable=False,
        index=True,
    )

    action = db.Column(
        db.Enum(ClinicalRuleAction),
        nullable=False,
        index=True,
    )

    status = db.Column(
        db.Enum(ClinicalAlertStatus),
        nullable=False,
        default=ClinicalAlertStatus.OPEN,
        index=True,
    )

    title = db.Column(
        db.String(255),
        nullable=False,
    )

    message = db.Column(
        db.Text,
        nullable=False,
    )

    context = db.Column(
        db.JSON,
        nullable=False,
        default=dict,
    )

    source_type = db.Column(
        db.String(100),
        nullable=False,
        index=True,
    )

    source_id = db.Column(
        db.Integer,
        nullable=True,
        index=True,
    )

    deduplication_key = db.Column(
        db.String(255),
        nullable=True,
    )

    generated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
        index=True,
    )

    resolved_at = db.Column(
        db.DateTime(timezone=True),
        nullable=True,
        index=True,
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

    def __repr__(self) -> str:
        return (
            f"<ClinicalAlert {self.id} "
            f"Patient {self.patient_id} "
            f"({self.severity.value})>"
        )