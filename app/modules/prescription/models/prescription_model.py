from datetime import datetime, timezone

from app.extensions import db
from app.core.enums.prescription_enums import (
    PrescriptionStatus,
    DrugInteractionSeverity,
)


def _utcnow():
    return datetime.now(timezone.utc)


class Prescription(db.Model):
    __tablename__ = "prescriptions"

    id = db.Column(db.Integer, primary_key=True)

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
        db.DateTime,
        default=_utcnow,
        nullable=False,
    )

    expires_at = db.Column(
        db.DateTime,
        nullable=True,
    )

    created_at = db.Column(
        db.DateTime,
        default=_utcnow,
        nullable=False,
    )

    updated_at = db.Column(
        db.DateTime,
        default=_utcnow,
        onupdate=_utcnow,
        nullable=False,
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
    )

    dispense_records = db.relationship(
        "DispenseRecord",
        back_populates="prescription",
    )

    def __repr__(self):
        return (
            f"<Prescription {self.id} - "
            f"Patient {self.patient_id} "
            f"({self.status.value})>"
        )


class PrescriptionItem(db.Model):
    __tablename__ = "prescription_items"

    id = db.Column(db.Integer, primary_key=True)

    prescription_id = db.Column(
        db.Integer,
        db.ForeignKey("prescriptions.id"),
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
        db.String(100),
        nullable=True,
    )

    frequency = db.Column(
        db.String(100),
        nullable=True,
    )

    duration = db.Column(
        db.String(100),
        nullable=True,
    )

    quantity = db.Column(
        db.Integer,
        nullable=True,
    )

    instructions = db.Column(
        db.Text,
        nullable=True,
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

    __table_args__ = (
        db.CheckConstraint(
            "quantity IS NULL OR quantity > 0",
            name="ck_prescription_item_quantity_positive",
        ),
    )

    def __repr__(self):
        return (
            f"<PrescriptionItem Drug {self.drug_id} "
            f"- Rx {self.prescription_id}>"
        )


class DrugInteraction(db.Model):
    __tablename__ = "drug_interactions"

    id = db.Column(db.Integer, primary_key=True)

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

    __table_args__ = (
        db.CheckConstraint(
            "drug_a_id <> drug_b_id",
            name="ck_drug_interaction_distinct_drugs",
        ),
    )

    def __repr__(self):
        return (
            f"<DrugInteraction {self.drug_a_id} "
            f"x {self.drug_b_id} "
            f"({self.severity.value})>"
        )