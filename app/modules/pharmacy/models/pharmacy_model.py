from datetime import datetime, timezone

from app.extensions import db
from app.core.enums.pharmacy_enums import (
    DrugCategory,
    DispenseStatus,
)


def _utcnow():
    return datetime.now(timezone.utc)


class Drug(db.Model):
    """
    Pharmacy drug catalog.

    clinic_id:
        NULL -> shared/global catalog definition.
        value -> clinic-specific drug definition.

    Physical inventory is stored in DrugBatch, which always belongs
    to a specific clinic.
    """

    __tablename__ = "drugs"

    __table_args__ = (
        db.CheckConstraint(
            "unit_price IS NULL OR unit_price >= 0",
            name="ck_drugs_unit_price_non_negative",
        ),
    )

    id = db.Column(
        db.Integer,
        primary_key=True,
    )

    clinic_id = db.Column(
        db.Integer,
        db.ForeignKey("clinics.id"),
        nullable=True,
        index=True,
    )

    name = db.Column(
        db.String(150),
        nullable=False,
    )

    generic_name = db.Column(
        db.String(150),
        nullable=True,
    )

    category = db.Column(
        db.Enum(DrugCategory),
        default=DrugCategory.OTHER,
        nullable=False,
        index=True,
    )

    rxnorm_code = db.Column(
        db.String(20),
        nullable=True,
        index=True,
    )

    barcode = db.Column(
        db.String(80),
        unique=True,
        nullable=True,
        index=True,
    )

    manufacturer = db.Column(
        db.String(150),
        nullable=True,
    )

    dosage_form = db.Column(
        db.String(50),
        nullable=True,
    )

    strength = db.Column(
        db.String(50),
        nullable=True,
    )

    unit_price = db.Column(
        db.Numeric(10, 2),
        nullable=True,
    )

    is_controlled = db.Column(
        db.Boolean,
        default=False,
        nullable=False,
    )

    is_active = db.Column(
        db.Boolean,
        default=True,
        nullable=False,
        index=True,
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

    clinic = db.relationship(
        "Clinic",
        back_populates="drugs",
    )

    batches = db.relationship(
        "DrugBatch",
        back_populates="drug",
        cascade="all, delete-orphan",
    )

    prescription_items = db.relationship(
        "PrescriptionItem",
        back_populates="drug",
    )

    def __repr__(self):
        return f"<Drug {self.name} {self.strength or ''}>"


class DrugBatch(db.Model):
    """
    Physical pharmacy inventory batch.

    Every batch belongs to exactly one clinic, even when the Drug
    itself is a shared/global catalog entry.
    """

    __tablename__ = "drug_batches"

    __table_args__ = (
        db.UniqueConstraint(
            "clinic_id",
            "drug_id",
            "batch_number",
            name="uq_drug_batch_clinic_drug_number",
        ),
        db.CheckConstraint(
            "quantity_on_hand >= 0",
            name="ck_drug_batches_quantity_non_negative",
        ),
        db.CheckConstraint(
            "reorder_level >= 0",
            name="ck_drug_batches_reorder_level_non_negative",
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

    drug_id = db.Column(
        db.Integer,
        db.ForeignKey("drugs.id"),
        nullable=False,
        index=True,
    )

    supplier_id = db.Column(
        db.Integer,
        db.ForeignKey("inventory_suppliers.id"),
        nullable=True,
        index=True,
    )

    batch_number = db.Column(
        db.String(80),
        nullable=False,
    )

    quantity_on_hand = db.Column(
        db.Integer,
        default=0,
        nullable=False,
    )

    reorder_level = db.Column(
        db.Integer,
        default=20,
        nullable=False,
    )

    expiry_date = db.Column(
        db.Date,
        nullable=False,
        index=True,
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

    received_at = db.Column(
        db.DateTime,
        default=_utcnow,
        nullable=False,
    )

    clinic = db.relationship(
        "Clinic",
        back_populates="drug_batches",
    )

    drug = db.relationship(
        "Drug",
        back_populates="batches",
    )

    supplier = db.relationship(
        "InventorySupplier",
        back_populates="drug_batches",
    )

    dispense_items = db.relationship(
        "DispenseItem",
        back_populates="batch",
    )

    def __repr__(self):
        return (
            f"<DrugBatch {self.batch_number} - "
            f"Clinic {self.clinic_id} - "
            f"Drug {self.drug_id} "
            f"({self.quantity_on_hand})>"
        )


class DispenseRecord(db.Model):
    """
    Records a pharmacy dispensing transaction against a prescription.

    PENDING:
        No medication has been dispensed yet.

    PARTIALLY_DISPENSED:
        Some requested medication was dispensed, but fulfillment
        remains incomplete.

    DISPENSED:
        Requested prescription quantities were fully fulfilled.

    CANCELLED:
        Transaction was cancelled and any stock deducted by this
        transaction was restored.
    """

    __tablename__ = "dispense_records"

    id = db.Column(
        db.Integer,
        primary_key=True,
    )

    prescription_id = db.Column(
        db.Integer,
        db.ForeignKey("prescriptions.id"),
        nullable=False,
        index=True,
    )

    dispensed_by_id = db.Column(
        db.Integer,
        db.ForeignKey("staff.id"),
        nullable=False,
        index=True,
    )

    status = db.Column(
        db.Enum(DispenseStatus),
        default=DispenseStatus.PENDING,
        nullable=False,
        index=True,
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

    # NULL until medication is actually dispensed.
    dispensed_at = db.Column(
        db.DateTime,
        nullable=True,
    )

    notes = db.Column(
        db.Text,
        nullable=True,
    )

    prescription = db.relationship(
        "Prescription",
        back_populates="dispense_records",
    )

    dispensed_by = db.relationship(
        "Staff",
        back_populates="dispense_records",
    )

    items = db.relationship(
        "DispenseItem",
        back_populates="dispense_record",
        cascade="all, delete-orphan",
    )

    def __repr__(self):
        return (
            f"<DispenseRecord {self.id} - "
            f"Prescription {self.prescription_id} "
            f"({self.status.value})>"
        )


class DispenseItem(db.Model):
    """
    Records the exact quantity dispensed from a specific batch.

    prescription_item_id is nullable to allow exceptional/manual
    pharmacy dispensing, although normal prescription fulfillment
    should always reference a PrescriptionItem.
    """

    __tablename__ = "dispense_items"

    __table_args__ = (
        db.CheckConstraint(
            "quantity_dispensed > 0",
            name="ck_dispense_items_quantity_positive",
        ),
    )

    id = db.Column(
        db.Integer,
        primary_key=True,
    )

    dispense_record_id = db.Column(
        db.Integer,
        db.ForeignKey("dispense_records.id"),
        nullable=False,
        index=True,
    )

    batch_id = db.Column(
        db.Integer,
        db.ForeignKey("drug_batches.id"),
        nullable=False,
        index=True,
    )

    prescription_item_id = db.Column(
        db.Integer,
        db.ForeignKey("prescription_items.id"),
        nullable=True,
        index=True,
    )

    quantity_dispensed = db.Column(
        db.Integer,
        nullable=False,
    )

    dispense_record = db.relationship(
        "DispenseRecord",
        back_populates="items",
    )

    batch = db.relationship(
        "DrugBatch",
        back_populates="dispense_items",
    )

    prescription_item = db.relationship(
        "PrescriptionItem",
        back_populates="dispense_items",
    )

    def __repr__(self):
        return (
            f"<DispenseItem Batch {self.batch_id} "
            f"x{self.quantity_dispensed}>"
        )
