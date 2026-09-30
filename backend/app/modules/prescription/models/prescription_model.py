from __future__ import annotations

from datetime import datetime, timezone

from app.core.enums.prescription_enums import (
    DrugInteractionSeverity,
    PrescriptionStatus,
)
from app.extensions import db


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Prescription(db.Model):
    __tablename__ = "prescriptions"

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

    consultation_id = db.Column(
        db.Integer,
        db.ForeignKey("consultations.id"),
        nullable=True,
        index=True,
    )

    prescribed_by_id = db.Column(
        db.Integer,
        db.ForeignKey("staff.id"),
        nullable=False,
        index=True,
    )

    status = db.Column(
        db.Enum(PrescriptionStatus),
        default=PrescriptionStatus.ACTIVE,
        nullable=False,
        index=True,
    )

    notes = db.Column(
        db.Text,
        nullable=True,
    )

    issued_at = db.Column(
        db.DateTime(timezone=True),
        default=_utcnow,
        nullable=False,
        index=True,
    )

    expires_at = db.Column(
        db.DateTime(timezone=True),
        nullable=True,
        index=True,
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

    # -----------------------------------------------------------------
    # Table-level indexes
    # -----------------------------------------------------------------

    __table_args__ = (
        db.Index(
            "ix_prescriptions_clinic_patient_issued",
            "clinic_id",
            "patient_id",
            "issued_at",
            "id",
        ),
        db.Index(
            "ix_prescriptions_clinic_patient_status_issued",
            "clinic_id",
            "patient_id",
            "status",
            "issued_at",
            "id",
        ),
        db.Index(
            "ix_prescriptions_expiration_status",
            "status",
            "expires_at",
        ),
        db.Index(
            "ix_prescriptions_clinic_status_issued",
            "clinic_id",
            "status",
            "issued_at",
            "id",
        ),
    )

    # -----------------------------------------------------------------
    # Relationships
    # -----------------------------------------------------------------

    clinic = db.relationship(
        "Clinic",
        back_populates="prescriptions",
    )

    patient = db.relationship(
        "Patient",
        back_populates="prescriptions",
    )

    consultation = db.relationship(
        "Consultation",
        back_populates="prescriptions",
    )

    prescribed_by = db.relationship(
        "Staff",
        back_populates="prescriptions",
    )

    items = db.relationship(
        "PrescriptionItem",
        back_populates="prescription",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    dispense_records = db.relationship(
        "DispenseRecord",
        back_populates="prescription",
    )

    def __repr__(self) -> str:
        return (
            f"<Prescription {self.id} - "
            f"Patient {self.patient_id} "
            f"({self.status.value})>"
        )


class PrescriptionItem(db.Model):
    __tablename__ = "prescription_items"

    id = db.Column(
        db.Integer,
        primary_key=True,
    )

    prescription_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "prescriptions.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    drug_id = db.Column(
        db.Integer,
        db.ForeignKey("drugs.id"),
        nullable=False,
        index=True,
    )

    dosage = db.Column(
        db.String(255),
        nullable=True,
    )

    frequency = db.Column(
        db.String(255),
        nullable=True,
    )

    duration = db.Column(
        db.String(255),
        nullable=True,
    )

    quantity = db.Column(
        db.Integer,
        nullable=True,
    )

    instructions = db.Column(
        db.String(1000),
        nullable=True,
    )

    __table_args__ = (
        db.CheckConstraint(
            "quantity IS NULL OR quantity > 0",
            name="ck_prescription_item_quantity_positive",
        ),
        db.Index(
            "ix_prescription_items_prescription_drug",
            "prescription_id",
            "drug_id",
        ),
    )

    # -----------------------------------------------------------------
    # Relationships
    # -----------------------------------------------------------------

    prescription = db.relationship(
        "Prescription",
        back_populates="items",
    )

    drug = db.relationship(
        "Drug",
        back_populates="prescription_items",
    )

    dispense_items = db.relationship(
        "DispenseItem",
        back_populates="prescription_item",
    )

    def __repr__(self) -> str:
        return (
            f"<PrescriptionItem Drug {self.drug_id} "
            f"- Rx {self.prescription_id}>"
        )


class DrugInteraction(db.Model):
    __tablename__ = "drug_interactions"

    id = db.Column(
        db.Integer,
        primary_key=True,
    )

    drug_a_id = db.Column(
        db.Integer,
        db.ForeignKey("drugs.id"),
        nullable=False,
        index=True,
    )

    drug_b_id = db.Column(
        db.Integer,
        db.ForeignKey("drugs.id"),
        nullable=False,
        index=True,
    )

    severity = db.Column(
        db.Enum(DrugInteractionSeverity),
        nullable=False,
        index=True,
    )

    description = db.Column(
        db.Text,
        nullable=True,
    )

    __table_args__ = (
        db.CheckConstraint(
            "drug_a_id <> drug_b_id",
            name="ck_drug_interaction_distinct_drugs",
        ),
        db.CheckConstraint(
            "drug_a_id < drug_b_id",
            name="ck_drug_interaction_canonical_order",
        ),
        db.UniqueConstraint(
            "drug_a_id",
            "drug_b_id",
            name="uq_drug_interaction_pair",
        ),
    )

    # -----------------------------------------------------------------
    # Relationships
    # -----------------------------------------------------------------

    drug_a = db.relationship(
        "Drug",
        foreign_keys=[drug_a_id],
    )

    drug_b = db.relationship(
        "Drug",
        foreign_keys=[drug_b_id],
    )

    def __repr__(self) -> str:
        return (
            f"<DrugInteraction {self.drug_a_id} "
            f"x {self.drug_b_id} "
            f"({self.severity.value})>"
        )