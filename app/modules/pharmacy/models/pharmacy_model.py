from datetime import datetime, timezone
from app.extensions import db
from app.core.enums.pharmacy_enums import DrugCategory, DispenseStatus

def _utcnow():
    return datetime.now(timezone.utc)

class Drug(db.Model):
    """Pharmacy catalog — separate from generic InventoryItem since drugs need clinical fields."""
    __tablename__ = "drugs"

    id = db.Column(db.Integer, primary_key=True)
    clinic_id = db.Column(db.Integer, db.ForeignKey("clinics.id"), nullable=True)  # null = shared catalog

    name = db.Column(db.String(150), nullable=False)
    generic_name = db.Column(db.String(150), nullable=True)
    category = db.Column(db.Enum(DrugCategory), default=DrugCategory.OTHER, nullable=False)

    barcode = db.Column(db.String(80), unique=True, nullable=True)
    manufacturer = db.Column(db.String(150), nullable=True)
    dosage_form = db.Column(db.String(50), nullable=True)         
    strength = db.Column(db.String(50), nullable=True)            

    unit_price = db.Column(db.Numeric(10, 2), nullable=True)
    is_controlled = db.Column(db.Boolean, default=False)

    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=_utcnow)
    updated_at = db.Column(db.DateTime, default=_utcnow, onupdate=_utcnow)

    batches = db.relationship("DrugBatch", back_populates="drug", cascade="all, delete-orphan")
    prescription_items = db.relationship("PrescriptionItem", back_populates="drug")

    def __repr__(self):
        return f"<Drug {self.name} {self.strength or ''}>"


class DrugBatch(db.Model):
    __tablename__ = "drug_batches"

    id = db.Column(db.Integer, primary_key=True)
    drug_id = db.Column(db.Integer, db.ForeignKey("drugs.id"), nullable=False)
    supplier_id = db.Column(db.Integer, db.ForeignKey("inventory_suppliers.id"), nullable=True)

    batch_number = db.Column(db.String(80), nullable=False)
    quantity_on_hand = db.Column(db.Integer, default=0, nullable=False)
    reorder_level = db.Column(db.Integer, default=20, nullable=False)

    expiry_date = db.Column(db.Date, nullable=False)
    created_at = db.Column(db.DateTime, default=_utcnow)
    updated_at = db.Column(db.DateTime, default=_utcnow, onupdate=_utcnow)
    received_at = db.Column(db.DateTime, default=_utcnow)

    drug = db.relationship("Drug", back_populates="batches")
    supplier = db.relationship("InventorySupplier", back_populates="drug_batches")

    __table_args__ = (
        db.UniqueConstraint("drug_id", "batch_number", name="uq_drug_batch_number"),
    )

    def __repr__(self):
        return f"<DrugBatch {self.batch_number} - {self.drug_id} ({self.quantity_on_hand})>"


class DispenseRecord(db.Model):
    """Tracks what was actually handed out against a prescription."""
    __tablename__ = "dispense_records"

    id = db.Column(db.Integer, primary_key=True)
    prescription_id = db.Column(db.Integer, db.ForeignKey("prescriptions.id"), nullable=False)
    dispensed_by_id = db.Column(db.Integer, db.ForeignKey("staff.id"), nullable=False)

    status = db.Column(db.Enum(DispenseStatus), default=DispenseStatus.PENDING, nullable=False)
    created_at = db.Column(db.DateTime, default=_utcnow)
    updated_at = db.Column(db.DateTime, default=_utcnow, onupdate=_utcnow)
    dispensed_at = db.Column(db.DateTime, default=_utcnow)
    notes = db.Column(db.Text, nullable=True)

    prescription = db.relationship("Prescription", back_populates="dispense_records")
    dispensed_by = db.relationship("Staff", back_populates="dispense_records")
    items = db.relationship("DispenseItem", back_populates="dispense_record", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<DispenseRecord {self.id} - Prescription {self.prescription_id} ({self.status.value})>"
    
    

class DispenseItem(db.Model):
    __tablename__ = "dispense_items"

    id = db.Column(db.Integer, primary_key=True)
    dispense_record_id = db.Column(db.Integer, db.ForeignKey("dispense_records.id"), nullable=False)
    batch_id = db.Column(db.Integer, db.ForeignKey("drug_batches.id"), nullable=False)

    prescription_item_id = db.Column(db.Integer, db.ForeignKey("prescription_items.id"), nullable=True)

    quantity_dispensed = db.Column(db.Integer, nullable=False)

    dispense_record = db.relationship("DispenseRecord", back_populates="items")
    batch = db.relationship("DrugBatch")
    prescription_item = db.relationship("PrescriptionItem")

    def __repr__(self):
        return f"<DispenseItem Batch {self.batch_id} x{self.quantity_dispensed}>"