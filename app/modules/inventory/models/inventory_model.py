from datetime import datetime, timezone
from app.extensions import db
from app.core.enums.inventory_enums import InventoryCategory, StockMovementType

def _utcnow():
    return datetime.now(timezone.utc)

class InventoryItem(db.Model):
    __tablename__ = "inventory_items"

    id = db.Column(db.Integer, primary_key=True)
    clinic_id = db.Column(db.Integer, db.ForeignKey("clinics.id"), nullable=False)

    name = db.Column(db.String(150), nullable=False)
    category = db.Column(db.Enum(InventoryCategory), default=InventoryCategory.MEDICAL_SUPPLY, nullable=False)
    sku = db.Column(db.String(80), unique=True, nullable=True)
    barcode = db.Column(db.String(80), unique=True, nullable=True)

    unit = db.Column(db.String(30), nullable=True)              
    quantity_on_hand = db.Column(db.Integer, default=0, nullable=False)
    reorder_level = db.Column(db.Integer, default=10, nullable=False)            

    unit_cost = db.Column(db.Numeric(10, 2), nullable=True)
    expiry_date = db.Column(db.Date, nullable=True)              

    supplier_id = db.Column(db.Integer, db.ForeignKey("inventory_suppliers.id"), nullable=True)

    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=_utcnow)
    updated_at = db.Column(db.DateTime, default=_utcnow, onupdate=_utcnow)

    clinic = db.relationship("Clinic", back_populates="inventory_items")
    supplier = db.relationship("InventorySupplier", back_populates="items")
    movements = db.relationship("StockMovement", back_populates="item", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<InventoryItem {self.name} ({self.quantity_on_hand} {self.unit})>"


class InventorySupplier(db.Model):
    __tablename__ = "inventory_suppliers"

    id = db.Column(db.Integer, primary_key=True)
    clinic_id = db.Column(db.Integer, db.ForeignKey("clinics.id"), nullable=True)  # null = shared across branches

    name = db.Column(db.String(150), nullable=False)
    contact_person = db.Column(db.String(120), nullable=True)
    phone = db.Column(db.String(30), nullable=True)
    email = db.Column(db.String(120), nullable=True)
    address = db.Column(db.String(255), nullable=True)

    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=_utcnow)
    updated_at = db.Column(db.DateTime, default=_utcnow, onupdate=_utcnow)

    items = db.relationship("InventoryItem", back_populates="supplier")
    drug_batches = db.relationship("DrugBatch", back_populates="supplier")

    def __repr__(self):
        return f"<InventorySupplier {self.name}>"


class StockMovement(db.Model):
    __tablename__ = "stock_movements"

    id = db.Column(db.Integer, primary_key=True)
    item_id = db.Column(db.Integer, db.ForeignKey("inventory_items.id"), nullable=False)

    movement_type = db.Column(db.Enum(StockMovementType), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)          
    reason = db.Column(db.String(255), nullable=True)

    performed_by_id = db.Column(db.Integer, db.ForeignKey("staff.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=_utcnow)

    item = db.relationship("InventoryItem", back_populates="movements")
    performed_by = db.relationship("Staff", back_populates="stock_movements")

    def __repr__(self):
        return f"<StockMovement {self.movement_type.value} {self.quantity} on Item {self.item_id}>"