from datetime import datetime, timezone

from sqlalchemy import ForeignKeyConstraint, Index, UniqueConstraint

from app.core.enums.hie_enums import (
    HIEIntegrationStatus,
    HIEOperation,
    HIESubmissionStatus,
)
from app.extensions import db


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class HIEIntegration(db.Model):
    __tablename__ = "hie_integrations"

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

    provider = db.Column(
        db.String(50),
        nullable=False,
        default="malaffi",
        index=True,
    )

    status = db.Column(
        db.Enum(HIEIntegrationStatus),
        nullable=False,
        default=HIEIntegrationStatus.PENDING,
        index=True,
    )

    endpoint_url = db.Column(
        db.String(255),
        nullable=True,
    )

    organization_id = db.Column(
        db.String(100),
        nullable=True,
    )

    facility_id = db.Column(
        db.String(100),
        nullable=True,
    )

    last_sync_at = db.Column(
        db.DateTime(timezone=True),
        nullable=True,
    )

    created_at = db.Column(
        db.DateTime(timezone=True),
        default=_utcnow,
        nullable=False,
    )

    updated_at = db.Column(
        db.DateTime(timezone=True),
        default=_utcnow,
        onupdate=_utcnow,
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint(
            "id",
            "clinic_id",
            name="uq_hie_integrations_id_clinic",
        ),
        Index(
            "ix_hie_integrations_clinic_status_provider",
            "clinic_id",
            "status",
            "provider",
        ),
    )

    clinic = db.relationship(
        "Clinic",
        back_populates="hie_integrations",
    )

    submissions = db.relationship(
        "HIESubmission",
        back_populates="integration",
        foreign_keys=lambda: [
            HIESubmission.integration_id,
            HIESubmission.clinic_id,
        ],
        cascade="all, delete-orphan",
        overlaps="clinic,hie_submissions",
    )

    def __repr__(self) -> str:
        return (
            f"<HIEIntegration "
            f"id={self.id} "
            f"clinic_id={self.clinic_id} "
            f"provider={self.provider} "
            f"status={self.status.value}>"
        )


class HIESubmission(db.Model):
    __tablename__ = "hie_submissions"

    id = db.Column(
        db.Integer,
        primary_key=True,
    )

    integration_id = db.Column(
        db.Integer,
        nullable=False,
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
        nullable=True,
        index=True,
    )

    operation = db.Column(
        db.Enum(HIEOperation),
        nullable=False,
        index=True,
    )

    status = db.Column(
        db.Enum(HIESubmissionStatus),
        nullable=False,
        default=HIESubmissionStatus.PENDING,
        index=True,
    )

    external_reference = db.Column(
        db.String(255),
        nullable=True,
        index=True,
    )

    request_data = db.Column(
        db.JSON,
        nullable=True,
    )

    response_data = db.Column(
        db.JSON,
        nullable=True,
    )

    status_code = db.Column(
        db.Integer,
        nullable=True,
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

    submitted_at = db.Column(
        db.DateTime(timezone=True),
        nullable=True,
    )

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

    __table_args__ = (
        ForeignKeyConstraint(
            ["integration_id", "clinic_id"],
            [
                "hie_integrations.id",
                "hie_integrations.clinic_id",
            ],
            name="fk_hie_submissions_integration_clinic",
        ),
        Index(
            "ix_hie_submissions_clinic_created_id",
            "clinic_id",
            "created_at",
            "id",
        ),
        Index(
            "ix_hie_submissions_clinic_status_created",
            "clinic_id",
            "status",
            "created_at",
        ),
        Index(
            "ix_hie_submissions_clinic_patient_created",
            "clinic_id",
            "patient_id",
            "created_at",
        ),
    )

    integration = db.relationship(
        "HIEIntegration",
        back_populates="submissions",
        foreign_keys=[
            integration_id,
            clinic_id,
        ],
        overlaps="clinic,hie_submissions",
    )

    clinic = db.relationship(
        "Clinic",
        back_populates="hie_submissions",
        foreign_keys=[
            clinic_id,
        ],
        overlaps="integration,submissions",
    )

    patient = db.relationship(
        "Patient",
        back_populates="hie_submissions",
        foreign_keys=[
            patient_id,
        ],
    )

    def __repr__(self) -> str:
        return (
            f"<HIESubmission "
            f"id={self.id} "
            f"operation={self.operation.value} "
            f"status={self.status.value}>"
        )